from __future__ import annotations

import base64
import queue
import threading
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Iterator

import numpy as np
from PIL import Image

from ..data.bird_names import BirdNamesLoader
from ..media.image_io import ImageLoader, LoadedImage
from ..runtime.config import RuntimeConfig
from .cache import PredictionCache
from .corrections import ManualCorrectionStore
from .pipeline import BirdOnnxPipeline, PipelineInput, PipelineResult
from .preprocess import BirdBox, BirdImagePreprocessor, ClassifierCropJob
from .providers import RuntimeProbe, RuntimeResolution
from .result_filter import PredictionResultFilter


@dataclass
class PreparedPrediction:
    source_path: Path
    latitude: float | None
    longitude: float | None
    datetime_text: str | None
    include_preview: bool
    model_fingerprint: str
    location_fingerprint: str
    loaded: LoadedImage | None = None


@dataclass
class StreamingImageContext:
    index: int
    prepared: PreparedPrediction
    loaded: LoadedImage
    remaining_crops: int = 0
    width: int = 0
    height: int = 0
    closed: bool = False


@dataclass(frozen=True)
class StreamingCropJob:
    context: StreamingImageContext
    box: BirdBox
    crop_index: int


@dataclass(frozen=True)
class StreamingClassifyJob:
    index: int
    prepared: PreparedPrediction
    box: BirdBox
    crop_index: int
    tensor: np.ndarray
    metadata: tuple[float | None, float | None, str | None]


@dataclass(frozen=True)
class StreamingDetectedEvent:
    index: int
    prepared: PreparedPrediction
    expected_crops: int
    provider: list[str]
    width: int
    height: int


@dataclass(frozen=True)
class StreamingClassifiedEvent:
    index: int
    box: BirdBox
    crop_index: int
    classification: list[dict[str, Any]]


@dataclass(frozen=True)
class StreamingFailedEvent:
    index: int
    error: Exception


@dataclass
class PendingStreamingResult:
    prepared: PreparedPrediction
    expected_crops: int
    received_crops: int
    provider: list[str]
    width: int
    height: int
    birds_by_crop: dict[int, dict[str, Any]]


PredictionResultFactory = Callable[[PreparedPrediction, PipelineResult, int, int, float], dict[str, Any]]


class StreamingPredictionRunner:
    def __init__(self, config: RuntimeConfig, pipeline: Any, pending: list[tuple[int, PreparedPrediction]], accepted_classification_threshold: float, result_factory: PredictionResultFactory):
        self.config = config
        self.pipeline = pipeline
        self.pending = pending
        self.accepted_classification_threshold = accepted_classification_threshold
        self.result_factory = result_factory
        self.detector_batch_size = max(1, int(getattr(config, "detector_batch_size", 1)))
        self.classifier_batch_size = max(1, int(getattr(config, "classifier_batch_size", 1)))
        self.crop_worker_count = BirdImagePreprocessor._worker_count(max(1, self.classifier_batch_size))
        self.detect_sentinel = object()
        self.crop_sentinel = object()
        self.classify_sentinel = object()
        self.done_sentinel = object()
        self.to_detect: queue.Queue[Any] = queue.Queue(maxsize=self.detector_batch_size * 2)
        self.to_crop: queue.Queue[Any] = queue.Queue(maxsize=max(self.detector_batch_size * 4, self.classifier_batch_size))
        self.to_classify: queue.Queue[Any] = queue.Queue(maxsize=self.classifier_batch_size * 2)
        self.to_finalize: queue.Queue[Any] = queue.Queue()
        self.context_lock = threading.Lock()
        self.error_event = threading.Event()


    def run(self) -> Iterator[tuple[int, dict[str, Any]]]:
        threads = self._threads()
        for thread in threads:
            thread.start()

        pending_results: dict[int, PendingStreamingResult] = {}
        completed_count = 0
        try:
            while completed_count < len(self.pending):
                event = self.to_finalize.get()
                if event is self.done_sentinel:
                    if completed_count < len(self.pending):
                        raise RuntimeError("Streaming prediction pipeline stopped before all images completed.")

                    break

                if isinstance(event, StreamingFailedEvent):
                    raise event.error

                if isinstance(event, StreamingDetectedEvent):
                    pending_results[event.index] = PendingStreamingResult(event.prepared, event.expected_crops, 0, event.provider, event.width, event.height, {})
                    if event.expected_crops == 0:
                        completed_count += 1
                        yield event.index, self.result_factory(event.prepared, PipelineResult(event.provider, []), event.width, event.height, self.accepted_classification_threshold)

                    continue

                if isinstance(event, StreamingClassifiedEvent):
                    pending_result = pending_results[event.index]
                    pending_result.received_crops += 1
                    if event.classification:
                        pending_result.birds_by_crop[event.crop_index] = {"box": event.box.box, "box_confidence": event.box.score, "classification": event.classification}

                    if pending_result.received_crops >= pending_result.expected_crops:
                        birds = [pending_result.birds_by_crop[index] for index in sorted(pending_result.birds_by_crop)]
                        completed_count += 1
                        yield event.index, self.result_factory(pending_result.prepared, PipelineResult(pending_result.provider, birds), pending_result.width, pending_result.height, self.accepted_classification_threshold)
        finally:
            for thread in threads:
                thread.join(timeout=0.1)


    def _threads(self) -> list[threading.Thread]:
        return [
            threading.Thread(target=self._producer, daemon=True),
            threading.Thread(target=self._detector_worker, daemon=True),
            threading.Thread(target=self._classifier_worker, daemon=True),
            *[threading.Thread(target=self._crop_worker, daemon=True) for _worker_index in range(self.crop_worker_count)],
        ]


    def _close_context(self, context: StreamingImageContext) -> None:
        with self.context_lock:
            if context.closed:
                return

            context.closed = True

        ImageLoader.cleanup(context.loaded)


    def _report_pipeline_failure(self, exc: Exception) -> None:
        if self.error_event.is_set():
            return

        self.error_event.set()
        self.to_finalize.put(StreamingFailedEvent(-1, exc))
        self.to_finalize.put(self.done_sentinel)


    def _producer(self) -> None:
        try:
            for index, prepared in self.pending:
                if self.error_event.is_set():
                    return

                loaded = ImageLoader.load(prepared.source_path)
                context = StreamingImageContext(index=index, prepared=prepared, loaded=loaded, width=loaded.image.width, height=loaded.image.height)
                self.to_detect.put(context)

            self.to_detect.put(self.detect_sentinel)
        except Exception as exc:
            self._report_pipeline_failure(exc)


    def _run_detector_batch(self, contexts: list[StreamingImageContext]) -> None:
        if not contexts:
            return

        boxes_by_image = self.pipeline._detect_birds_many([context.loaded.image for context in contexts])
        provider = self.pipeline._active_providers()
        for context, boxes in zip(contexts, boxes_by_image):
            context.remaining_crops = len(boxes)
            self.to_finalize.put(StreamingDetectedEvent(context.index, context.prepared, len(boxes), provider, context.width, context.height))
            if not boxes:
                self._close_context(context)
                continue

            for crop_index, box in enumerate(boxes):
                self.to_crop.put(StreamingCropJob(context, box, crop_index))


    def _detector_worker(self) -> None:
        batch: list[StreamingImageContext] = []
        try:
            while True:
                try:
                    item = self.to_detect.get(timeout=0.05)
                except queue.Empty:
                    if self.error_event.is_set():
                        return

                    continue

                if item is self.detect_sentinel:
                    self._run_detector_batch(batch)
                    for _worker_index in range(self.crop_worker_count):
                        self.to_crop.put(self.crop_sentinel)
                    return

                batch.append(item)
                if len(batch) >= self.detector_batch_size:
                    self._run_detector_batch(batch)
                    batch = []
        except Exception as exc:
            for context in batch:
                self._close_context(context)

            self._report_pipeline_failure(exc)


    def _crop_worker(self) -> None:
        item: Any = None
        try:
            while True:
                try:
                    item = self.to_crop.get(timeout=0.05)
                except queue.Empty:
                    if self.error_event.is_set():
                        return

                    continue

                if item is self.crop_sentinel:
                    self.to_classify.put(self.classify_sentinel)
                    return

                tensor = BirdImagePreprocessor._classifier_tensor_from_box(ClassifierCropJob(item.context.loaded.image, item.box), self.config.crop_size)
                metadata = (item.context.prepared.latitude, item.context.prepared.longitude, item.context.prepared.datetime_text)
                with self.context_lock:
                    item.context.remaining_crops -= 1
                    should_close = item.context.remaining_crops <= 0 and not item.context.closed

                if should_close:
                    self._close_context(item.context)

                self.to_classify.put(StreamingClassifyJob(item.context.index, item.context.prepared, item.box, item.crop_index, tensor, metadata))
        except Exception as exc:
            if isinstance(item, StreamingCropJob):
                self._close_context(item.context)

            self._report_pipeline_failure(exc)


    def _run_classifier_batch(self, batch: list[StreamingClassifyJob]) -> None:
        if not batch:
            return

        tensors = np.stack([item.tensor for item in batch], axis=0).astype(np.float32)
        classifications = self.pipeline._run_classifier_batch(tensors, [item.metadata for item in batch])
        for item, classification in zip(batch, classifications):
            self.to_finalize.put(StreamingClassifiedEvent(item.index, item.box, item.crop_index, classification))


    def _classifier_worker(self) -> None:
        finished_crop_workers = 0
        batch: list[StreamingClassifyJob] = []
        try:
            while True:
                try:
                    item = self.to_classify.get(timeout=0.05)
                except queue.Empty:
                    if self.error_event.is_set():
                        return

                    if batch:
                        self._run_classifier_batch(batch)
                        batch = []

                    if finished_crop_workers >= self.crop_worker_count:
                        break

                    continue

                if item is self.classify_sentinel:
                    finished_crop_workers += 1
                    continue

                batch.append(item)
                if len(batch) >= self.classifier_batch_size:
                    self._run_classifier_batch(batch)
                    batch = []

            if batch:
                self._run_classifier_batch(batch)
        except Exception as exc:
            self._report_pipeline_failure(exc)
            return

        self.to_finalize.put(self.done_sentinel)


class PredictionService:
    def __init__(self, config: RuntimeConfig, runtime_probe: RuntimeProbe | None = None, forced_runtime: RuntimeResolution | None = None):
        self.config = config
        self._runtime_probe = runtime_probe
        self._forced_runtime = forced_runtime
        self._pipeline: BirdOnnxPipeline | None = None
        self._prediction_cache = PredictionCache()
        self._names = BirdNamesLoader(config.labels_path)
        self._corrections = ManualCorrectionStore(names=self._names)


    def clear_cache(self) -> int:
        return self._prediction_cache.clear()


    def predict(self, request: dict[str, Any], accepted_classification_threshold: float) -> dict[str, Any]:
        return self.predict_many([request], accepted_classification_threshold)[0]


    def predict_many(self, requests: list[dict[str, Any]], accepted_classification_threshold: float) -> list[dict[str, Any]]:
        return list(self.iter_predict_many(requests, accepted_classification_threshold))


    def iter_predict_many(self, requests: list[dict[str, Any]], accepted_classification_threshold: float):
        if not requests:
            return

        if any(request.get("includePreview") is not False for request in requests):
            for chunk in self._chunks(requests, self._request_chunk_size()):
                for result in self._predict_many_chunk(chunk, accepted_classification_threshold):
                    yield result

            return

        for chunk in self._chunks(requests, self._stream_source_chunk_size()):
            yield from self._iter_predict_many_streaming(chunk, accepted_classification_threshold)

    def _stream_source_chunk_size(self) -> int:
        detector_batch_size = max(1, int(getattr(self.config, "detector_batch_size", 1)))
        return max(4, min(32, detector_batch_size * 4))


    def _iter_predict_many_streaming(self, requests: list[dict[str, Any]], accepted_classification_threshold: float):
        model_fingerprint = PredictionCache.model_fingerprint(self.config)
        ready_results: dict[int, dict[str, Any]] = {}
        pending: list[tuple[int, PreparedPrediction]] = []
        for index, request in enumerate(requests):
            prepared = self._prepare_prediction(request, model_fingerprint)
            cached_result = self._cached_result(request, prepared, accepted_classification_threshold)
            if cached_result is not None:
                ready_results[index] = cached_result
            else:
                pending.append((index, prepared))

        if pending:
            pipeline = self._get_pipeline()
            next_yield_index = 0
            result_iterator = self._stream_pending_predictions(pending, accepted_classification_threshold, pipeline) if self._pipeline_supports_streaming(pipeline) else self._predict_prepared_many(pending, accepted_classification_threshold, pipeline)
            for index, result in result_iterator:
                ready_results[index] = result
                while next_yield_index in ready_results:
                    yield ready_results.pop(next_yield_index)
                    next_yield_index += 1

            while next_yield_index < len(requests):
                if next_yield_index not in ready_results:
                    break

                yield ready_results.pop(next_yield_index)
                next_yield_index += 1
            return

        for index in range(len(requests)):
            if index in ready_results:
                yield ready_results.pop(index)


    def _stream_pending_predictions(self, pending: list[tuple[int, PreparedPrediction]], accepted_classification_threshold: float, pipeline: Any):
        runner = StreamingPredictionRunner(self.config, pipeline, pending, accepted_classification_threshold, self._prediction_result_from_values)
        yield from runner.run()


    def _predict_prepared_many(self, pending: list[tuple[int, PreparedPrediction]], accepted_classification_threshold: float, pipeline: Any):
        for chunk in self._chunks(pending, self._request_chunk_size()):
            loaded_predictions: list[PreparedPrediction] = []
            try:
                for _index, prepared in chunk:
                    prepared.loaded = ImageLoader.load(prepared.source_path)
                    loaded_predictions.append(prepared)

                pipeline_inputs = [
                    PipelineInput(prepared.loaded.image, prepared.latitude, prepared.longitude, prepared.datetime_text)
                    for _index, prepared in chunk
                    if prepared.loaded is not None
                ]
                predictions = pipeline.predict_many(pipeline_inputs) if hasattr(pipeline, "predict_many") else [pipeline.predict(item.image, item.latitude, item.longitude, item.datetime_text) for item in pipeline_inputs]
                for (index, prepared), prediction in zip(chunk, predictions):
                    yield index, self._prediction_result(prepared, prediction, accepted_classification_threshold)
            finally:
                for prepared in loaded_predictions:
                    if prepared.loaded is not None:
                        ImageLoader.cleanup(prepared.loaded)


    def _pipeline_supports_streaming(self, pipeline: Any) -> bool:
        return hasattr(pipeline, "_detect_birds_many") and hasattr(pipeline, "_run_classifier_batch") and hasattr(pipeline, "_active_providers")


    def _predict_many_chunk(self, requests: list[dict[str, Any]], accepted_classification_threshold: float) -> list[dict[str, Any]]:
        model_fingerprint = PredictionCache.model_fingerprint(self.config)
        results: list[dict[str, Any] | None] = [None for _request in requests]
        pending: list[tuple[int, PreparedPrediction]] = []
        for index, request in enumerate(requests):
            prepared = self._prepare_prediction(request, model_fingerprint)
            cached_result = self._cached_result(request, prepared, accepted_classification_threshold)
            if cached_result is not None:
                results[index] = cached_result
            else:
                pending.append((index, prepared))

        if pending:
            loaded_predictions: list[PreparedPrediction] = []
            try:
                for _index, prepared in pending:
                    prepared.loaded = ImageLoader.load(prepared.source_path)
                    loaded_predictions.append(prepared)

                pipeline_inputs = [
                    PipelineInput(prepared.loaded.image, prepared.latitude, prepared.longitude, prepared.datetime_text)
                    for prepared in loaded_predictions
                    if prepared.loaded is not None
                ]
                pipeline = self._get_pipeline()
                predictions = pipeline.predict_many(pipeline_inputs) if hasattr(pipeline, "predict_many") else [pipeline.predict(item.image, item.latitude, item.longitude, item.datetime_text) for item in pipeline_inputs]
                for (index, prepared), prediction in zip(pending, predictions):
                    results[index] = self._prediction_result(prepared, prediction, accepted_classification_threshold)
            finally:
                for prepared in loaded_predictions:
                    if prepared.loaded is not None:
                        ImageLoader.cleanup(prepared.loaded)

        return [result if result is not None else {"birds": []} for result in results]


    def _prepare_prediction(self, request: dict[str, Any], model_fingerprint: str) -> PreparedPrediction:
        image_path = request.get("imagePath")
        if not image_path:
            raise ValueError("No image path provided.")

        source_path = Path(str(image_path))
        latitude = self._optional_float(request.get("latitude"))
        longitude = self._optional_float(request.get("longitude"))
        metadata = ImageLoader.read_metadata(source_path)
        datetime_text = request.get("datetime") or metadata.datetime_text
        include_preview = request.get("includePreview") is not False
        if latitude is None:
            latitude = metadata.latitude

        if longitude is None:
            longitude = metadata.longitude

        location_fingerprint = PredictionCache.location_fingerprint(latitude, longitude, datetime_text)

        return PreparedPrediction(source_path=source_path, latitude=latitude, longitude=longitude, datetime_text=datetime_text, include_preview=include_preview, model_fingerprint=model_fingerprint, location_fingerprint=location_fingerprint)


    def _cached_result(self, request: dict[str, Any], prepared: PreparedPrediction, accepted_classification_threshold: float) -> dict[str, Any] | None:
        if request.get("reprocess") is True:
            return None

        cached = self._prediction_cache.lookup(prepared.source_path, prepared.model_fingerprint, prepared.location_fingerprint)
        if cached is None:
            return None

        result = self._filtered_result(cached.get("result", {}))
        result["acceptedClassificationThreshold"] = accepted_classification_threshold
        result["usedLatitude"] = prepared.latitude
        result["usedLongitude"] = prepared.longitude
        result["usedDatetime"] = prepared.datetime_text
        result["source"] = "cache"
        result = self._corrections.apply(prepared.source_path, result)
        if prepared.include_preview:
            return self._with_loaded_preview(prepared.source_path, result)

        return result


    def _prediction_result(self, prepared: PreparedPrediction, prediction: PipelineResult, accepted_classification_threshold: float) -> dict[str, Any]:
        if prepared.loaded is None:
            raise RuntimeError("Prediction image was not loaded.")

        result = self._prediction_result_from_values(prepared, prediction, prepared.loaded.image.width, prepared.loaded.image.height, accepted_classification_threshold)
        if prepared.include_preview:
            return self._with_preview(result, prepared.loaded.image)

        return result


    def _prediction_result_from_values(self, prepared: PreparedPrediction, prediction: PipelineResult, width: int, height: int, accepted_classification_threshold: float) -> dict[str, Any]:
        cached_result = {"provider": prediction.provider, "birds": prediction.birds, "lowConfidenceThreshold": self.config.low_confidence_threshold, "usedLatitude": prepared.latitude, "usedLongitude": prepared.longitude, "usedDatetime": prepared.datetime_text, "width": width, "height": height}
        self._prediction_cache.store(prepared.source_path, prepared.model_fingerprint, prepared.location_fingerprint, cached_result)
        result = self._filtered_result(cached_result)
        result = self._corrections.apply(prepared.source_path, result)
        result["acceptedClassificationThreshold"] = accepted_classification_threshold
        result["source"] = "prediction"
        return result


    def cached_prediction_preview(self, request: dict[str, Any], accepted_classification_threshold: float) -> dict[str, Any]:
        image_path = request.get("imagePath")
        if not image_path:
            raise ValueError("No image path provided.")

        source_path = Path(str(image_path))
        latitude = self._optional_float(request.get("latitude"))
        longitude = self._optional_float(request.get("longitude"))
        datetime_text = request.get("datetime") if "datetime" in request else None
        metadata = None
        if "latitude" not in request or "longitude" not in request or "datetime" not in request:
            metadata = ImageLoader.read_metadata(source_path)

        if latitude is None and "latitude" not in request and metadata is not None:
            latitude = metadata.latitude

        if longitude is None and "longitude" not in request and metadata is not None:
            longitude = metadata.longitude

        if "datetime" not in request and metadata is not None:
            datetime_text = metadata.datetime_text

        model_fingerprint = PredictionCache.model_fingerprint(self.config)
        location_fingerprint = PredictionCache.location_fingerprint(latitude, longitude, datetime_text)
        cached = self._prediction_cache.lookup(source_path, model_fingerprint, location_fingerprint)
        if cached is None:
            raise ValueError("Cached prediction not found. Scan the collection again.")

        result = self._filtered_result(cached.get("result", {}))
        result["acceptedClassificationThreshold"] = accepted_classification_threshold
        result["usedLatitude"] = latitude
        result["usedLongitude"] = longitude
        result["usedDatetime"] = datetime_text
        result["source"] = "cache"
        result = self._corrections.apply(source_path, result)
        return self._with_loaded_preview(source_path, result)


    def thumbnail_data_url(self, path: Path) -> str | None:
        try:
            loaded = ImageLoader.load(path)
            try:
                return self._image_data_url(loaded.image, 160, 82)
            finally:
                ImageLoader.cleanup(loaded)
        except Exception:
            return None


    def _with_loaded_preview(self, image_path: Path, result: dict[str, Any]) -> dict[str, Any]:
        loaded = ImageLoader.load(image_path)
        try:
            return self._with_preview(result, loaded.image)
        finally:
            ImageLoader.cleanup(loaded)


    def _with_preview(self, result: dict[str, Any], image: Image.Image) -> dict[str, Any]:
        result["previewDataUrl"] = self._preview_data_url(image)
        result["width"] = image.width
        result["height"] = image.height
        return result


    def _get_pipeline(self) -> BirdOnnxPipeline:
        if self._pipeline is None:
            self._pipeline = BirdOnnxPipeline(self.config, self._forced_runtime or self._runtime())

        return self._pipeline


    def _filtered_result(self, result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {"birds": []}

        return PredictionResultFilter(self.config.min_classification_confidence).apply(result)


    def _runtime(self) -> RuntimeResolution:
        if self._runtime_probe is None:
            raise RuntimeError("Runtime probe is not available.")

        return self._runtime_probe.runtime()



    def _preview_data_url(self, image: Image.Image) -> str:
        return self._image_data_url(image, None, 92)


    def _image_data_url(self, image: Image.Image, max_size: int | None, quality: int) -> str:
        output = BytesIO()
        preview = image.copy()
        if max_size is not None:
            preview.thumbnail((max_size, max_size))

        preview.save(output, format="JPEG", quality=quality)
        preview.close()
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"


    def _optional_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None

        return float(value)


    def _request_chunk_size(self) -> int:
        return max(1, int(getattr(self.config, "detector_batch_size", 1)))


    def _chunks(self, values: list[Any], size: int) -> list[list[Any]]:
        return [values[index:index + size] for index in range(0, len(values), size)]

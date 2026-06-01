from __future__ import annotations

import csv
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ..data.gpx import GpxService
from ..runtime.config import RuntimeConfig
from .onnxruntime_loader import OnnxRuntimeLoader
from .preprocess import BirdBox, BirdImagePreprocessor, ClassifierCropJob
from .providers import ProviderSelector, RuntimeResolution, RuntimeResolver


DEFAULT_DETECTOR_LABELS = {"14": "bird"}


@dataclass
class PipelineResult:
    provider: list[str]
    birds: list[dict[str, Any]]


@dataclass(frozen=True)
class PipelineInput:
    image: Image.Image
    latitude: float | None
    longitude: float | None
    datetime_text: str | None


class BirdOnnxPipeline:
    def __init__(self, config: RuntimeConfig, runtime: RuntimeResolution | None = None):
        config.validate()
        self.config = config
        self.class_ids = self._load_class_ids(config.labels_path)
        self.detector_labels = dict(DEFAULT_DETECTOR_LABELS)
        self.runtime = runtime or RuntimeResolver.resolve(config)
        self.provider_selection = self.runtime.selection
        self._inference_lock = threading.Lock()
        try:
            self.detector_session = self._create_session(config.detector_model)
            self.classifier_session = self._create_session(config.classifier_model)
        except Exception:
            self.provider_selection = ProviderSelector.cpu_selection(self.provider_selection)
            self.detector_session = self._create_session(config.detector_model)
            self.classifier_session = self._create_session(config.classifier_model)


    def predict(self, image: Image.Image, latitude: float | None, longitude: float | None, datetime_text: str | None) -> PipelineResult:
        return self.predict_many([PipelineInput(image, latitude, longitude, datetime_text)])[0]


    def predict_many(self, inputs: list[PipelineInput]) -> list[PipelineResult]:
        if not inputs:
            return []

        boxes_by_image = self._detect_birds_many([item.image for item in inputs])
        crop_jobs: list[ClassifierCropJob] = []
        crop_locations: list[tuple[int, int]] = []
        crop_metadata: list[tuple[float | None, float | None, str | None]] = []
        for image_index, (item, boxes) in enumerate(zip(inputs, boxes_by_image)):
            for box_index, box in enumerate(boxes):
                crop_jobs.append(ClassifierCropJob(item.image, box))
                crop_locations.append((image_index, box_index))
                crop_metadata.append((item.latitude, item.longitude, item.datetime_text))

        classifications = self._classify_many(crop_jobs, crop_metadata)
        providers = self._active_providers()
        birds_by_image: list[list[dict[str, Any]]] = [[] for _item in inputs]
        for (image_index, box_index), classification in zip(crop_locations, classifications):
            if classification:
                box = boxes_by_image[image_index][box_index]
                birds_by_image[image_index].append({"box": box.box, "box_confidence": box.score, "classification": classification})

        return [PipelineResult(provider=providers, birds=birds) for birds in birds_by_image]


    def _create_session(self, path: Path):
        OnnxRuntimeLoader.prepare()
        import onnxruntime as ort

        return ort.InferenceSession(str(path), providers=self.provider_selection.selected)


    def _active_providers(self) -> list[str]:
        providers = []
        for session in (self.detector_session, self.classifier_session):
            for provider in session.get_providers():
                if provider not in providers:
                    providers.append(provider)

        return providers


    def _run_detector(self, feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        with self._inference_lock:
            return self.detector_session.run(None, feeds)


    def _run_classifier(self, feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        with self._inference_lock:
            return self.classifier_session.run(None, feeds)


    def _detect_birds(self, image: Image.Image) -> list[BirdBox]:
        tensor, _target_size, scale = BirdImagePreprocessor.detector_image(image)
        input_name = self.detector_session.get_inputs()[0].name
        outputs = self._run_detector({input_name: tensor})
        return self._postprocess_detector(outputs, scale)


    def _detect_birds_many(self, images: list[Image.Image]) -> list[list[BirdBox]]:
        results: list[list[BirdBox]] = []
        input_name = self.detector_session.get_inputs()[0].name
        chunk_size = self._detector_chunk_size()
        for start in range(0, len(images), chunk_size):
            batch_images = images[start:start + chunk_size]
            tensor, scales = BirdImagePreprocessor.detector_batch(batch_images)
            outputs = self._run_detector({input_name: tensor})
            results.extend(self._postprocess_detector_batch(outputs, scales))

        return results


    def _postprocess_detector(self, outputs: list[np.ndarray], scale: tuple[float, float]) -> list[BirdBox]:
        return self._postprocess_detector_batch(outputs, [scale])[0]


    def _postprocess_detector_batch(self, outputs: list[np.ndarray], scales: list[tuple[float, float]]) -> list[list[BirdBox]]:
        output_names = [out.name for out in self.detector_session.get_outputs()]
        by_name = {name: value for name, value in zip(output_names, outputs)}
        boxes = by_name.get("boxes")
        scores = by_name.get("scores")
        labels = by_name.get("labels")

        if boxes is None or scores is None or labels is None:
            raise RuntimeError("Detector ONNX must output boxes, scores, and labels. Re-export with scripts/models/export_detector.py.")

        boxes = boxes[None, :, :] if boxes.ndim == 2 else boxes
        scores = scores[None, :] if scores.ndim == 1 else scores
        labels = labels[None, :] if labels.ndim == 1 else labels
        results: list[list[BirdBox]] = []
        for row_boxes, row_scores, row_labels, scale in zip(boxes, scores, labels, scales):
            results.append(self._postprocess_detector_rows(row_boxes, row_scores, row_labels, scale))

        return results


    def _postprocess_detector_rows(self, boxes: np.ndarray, scores: np.ndarray, labels: np.ndarray, scale: tuple[float, float]) -> list[BirdBox]:
        scale_x, scale_y = scale
        results: list[BirdBox] = []
        for box, score, label in zip(boxes, scores, labels):
            score_value = float(score)
            label_key = str(int(label))
            label_name = self.detector_labels.get(label_key, label_key)
            if score_value >= self.config.detection_threshold and label_name == "bird":
                x0, y0, x1, y1 = [float(v) for v in box.tolist()]
                results.append(BirdBox([round(x0 * scale_x, 2), round(y0 * scale_y, 2), round(x1 * scale_x, 2), round(y1 * scale_y, 2)], score_value))

        return results


    def _load_class_ids(self, path: Path) -> list[str]:
        if not path.exists():
            return []

        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [str(record.get("species_id") or class_index).strip() for class_index, record in enumerate(reader)]


    def _classify(self, crops: list[Image.Image], latitude: float | None, longitude: float | None, datetime_text: str | None) -> list[list[dict[str, Any]]]:
        results: list[list[dict[str, Any]]] = []
        metadata = [(latitude, longitude, datetime_text) for _crop in crops]
        chunk_size = self._classifier_chunk_size()
        for start in range(0, len(crops), chunk_size):
            batch_crops = crops[start:start + chunk_size]
            batch_metadata = metadata[start:start + chunk_size]
            images = BirdImagePreprocessor.classifier_batch(batch_crops, self.config.crop_size)
            results.extend(self._run_classifier_batch(images, batch_metadata))

        return results


    def _classify_many(self, crop_jobs: list[ClassifierCropJob], metadata: list[tuple[float | None, float | None, str | None]]) -> list[list[dict[str, Any]]]:
        results: list[list[dict[str, Any]]] = []
        chunk_size = self._classifier_chunk_size()

        for start in range(0, len(crop_jobs), chunk_size):
            batch_crops = crop_jobs[start:start + chunk_size]
            batch_metadata = metadata[start:start + chunk_size]
            images = BirdImagePreprocessor.classifier_batch_from_boxes(batch_crops, self.config.crop_size)
            results.extend(self._run_classifier_batch(images, batch_metadata))

        return results


    def _run_classifier_batch(self, images: np.ndarray, metadata: list[tuple[float | None, float | None, str | None]]) -> list[list[dict[str, Any]]]:
        feeds = {
            "img": images,
            "lat": np.array([np.nan if latitude is None else float(latitude) for latitude, _longitude, _datetime_text in metadata], dtype=np.float32),
            "lon": np.array([np.nan if longitude is None else float(longitude) for _latitude, longitude, _datetime_text in metadata], dtype=np.float32),
            "day": np.array([GpxService.day_of_year(datetime_text) for _latitude, _longitude, datetime_text in metadata], dtype=np.float32),
        }
        return self._classifier_results_from_feeds(feeds)


    def _classifier_results_from_feeds(self, feeds: dict[str, np.ndarray]) -> list[list[dict[str, Any]]]:
        results: list[list[dict[str, Any]]] = []
        scores, indices = self._run_classifier(feeds)
        for row_scores, row_indices in zip(scores, indices):
            topk = []
            for score, idx in zip(row_scores, row_indices):
                confidence = float(score)
                class_index = int(idx)
                topk.append(self._classification_for_index(class_index, confidence))
            results.append(topk)

        return results


    def _classification_for_index(self, class_index: int, confidence: float) -> dict[str, Any]:
        classification: dict[str, Any] = {"species_id": str(class_index), "confidence": confidence}
        if class_index < len(self.class_ids) and self.class_ids[class_index]:
            classification["species_id"] = self.class_ids[class_index]

        return classification


    def _classifier_chunk_size(self) -> int:
        return self._session_chunk_size(self.classifier_session, max(1, int(getattr(self.config, "classifier_batch_size", 1))))


    def _detector_chunk_size(self) -> int:
        return self._session_chunk_size(self.detector_session, max(1, int(getattr(self.config, "detector_batch_size", 1))))


    def _session_chunk_size(self, session, configured: int) -> int:
        inputs = session.get_inputs()
        if not inputs:
            return configured

        batch_axis = inputs[0].shape[0] if inputs[0].shape else 1
        if isinstance(batch_axis, int) and batch_axis > 0:
            return min(configured, batch_axis)

        return configured

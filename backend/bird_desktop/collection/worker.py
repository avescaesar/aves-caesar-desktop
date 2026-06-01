from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ..inference.cache import PredictionCache
from ..inference.providers import ProviderSelector, RuntimeResolution
from ..inference.result_filter import PredictionResultFilter
from ..inference.services import PredictionService
from ..runtime.config import RuntimeConfig
from ..runtime.settings import DEFAULT_ACCEPTED_CLASSIFICATION_THRESHOLD
from ..runtime.worker_io import WorkerLogRedirect, WorkerStatusWriter
from .services import COLLECTION_SCAN_MODE_RAW_JPEG, COLLECTION_SCAN_MODES, CollectionIndexer, CollectionScanner, CollectionStore


class CollectionWorker:
    def __init__(self):
        self._prediction_service: PredictionService | None = None
        self._runtime_key: str | None = None
        self._log_path = sys.argv[1] if len(sys.argv) > 1 else None
        self._status_writer = WorkerStatusWriter()


    def run(self) -> None:
        line = sys.stdin.readline()
        if not line.strip():
            self._write(self._error_status("No collection request received."))
            return

        try:
            request = json.loads(line)
            runtime = self._runtime_from_request(request)
            request.pop("_runtimeSelection", None)
            self._run_collection(request, runtime)
        except Exception as exc:
            payload = self._error_status(str(exc))
            payload["traceback"] = traceback.format_exc()
            self._write(payload)


    def _run_collection(self, request: dict[str, Any], runtime: RuntimeResolution) -> None:
        base_directory = Path(self._required_string(request, "baseDirectory"))
        scan_mode = self._scan_mode(request.get("scanMode"))
        threshold = self._threshold(request.get("acceptedClassificationThreshold"))
        images = CollectionScanner.scan_images(base_directory, scan_mode)
        self._write_log({"event": "scan_images", "baseDirectory": str(base_directory), "scanMode": scan_mode, "count": len(images)})
        store = CollectionStore()
        indexer = CollectionIndexer(store.thumbnail_data_url)
        config = RuntimeConfig.load()
        model_fingerprint = PredictionCache.model_fingerprint(config)
        cached_predictions_by_image = self._cached_predictions_by_image(images, model_fingerprint, config.min_classification_confidence)
        processed_images: list[Path] = []
        total = len(images)
        completed = self._reuse_cached_predictions(images, cached_predictions_by_image, threshold, store, indexer, processed_images)
        errors = 0
        initial_status = {"state": "running", "total": total, "completed": completed, "errors": errors, "currentFile": "", "message": f"Found {total} image(s).", "species": indexer.species()}
        if completed > 0:
            store.save_thumbnails(initial_status)

        self._write(initial_status)

        service = self._prediction_service_for_runtime(runtime)
        missing_images = [image_path for image_path in images if store.image_key(image_path) not in cached_predictions_by_image]
        self._write_log({"event": "prediction_plan", "total": total, "cached": completed, "missing": len(missing_images), "providers": runtime.selection.selected})
        if missing_images:
            self._write({"state": "running", "total": total, "completed": completed, "errors": errors, "currentFile": str(missing_images[0]), "message": f"Processing {len(missing_images)} image(s).", "species": indexer.species()})

        for image_path, result, error in self._prediction_results_for_chunk(missing_images, service, threshold):
            current_file = str(image_path)
            if error is None and result is not None:
                indexer.add_prediction(image_path, result, threshold)
                processed_images.append(image_path)
                completed += 1
                status = {"state": "running", "total": total, "completed": completed, "errors": errors, "currentFile": current_file, "message": "Collection scan running.", "species": indexer.species()}
                store.save_thumbnails(status)
                self._write(status)
            else:
                errors += 1
                completed += 1
                status = {"state": "running", "total": total, "completed": completed, "errors": errors, "currentFile": current_file, "message": str(error), "species": indexer.species()}
                store.save_thumbnails(status)
                self._write(status)

        status = {"state": "done", "total": total, "completed": completed, "errors": errors, "currentFile": "", "message": "Collection scan complete.", "species": indexer.species()}
        store.save_thumbnails(status)
        self._write(status)


    def _prediction_results_for_chunk(self, image_paths: list[Path], service: PredictionService, threshold: float) -> Iterator[tuple[Path, dict[str, Any] | None, Exception | None]]:
        requests = [{"imagePath": str(image_path), "includePreview": False} for image_path in image_paths]
        completed = 0
        prediction_iterator = service.iter_predict_many(requests, threshold)
        self._write_log({"event": "prediction_stream_start", "count": len(image_paths), "detectorBatchSize": service.config.detector_batch_size, "classifierBatchSize": service.config.classifier_batch_size})
        try:
            for image_path in image_paths:
                self._write_log({"event": "prediction_next_start", "completed": completed, "path": str(image_path)})
                with WorkerLogRedirect(self._log_path):
                    result = next(prediction_iterator)

                completed += 1
                self._write_log({"event": "prediction_stream_result", "completed": completed, "path": str(image_path), "birds": len(result.get("birds", [])) if isinstance(result, dict) else None})
                yield image_path, result, None

            return
        except StopIteration:
            self._write_log({"event": "prediction_stream_stop_iteration", "completed": completed, "expected": len(image_paths)})
            return
        except Exception:
            self._write_log({"event": "prediction_stream_error", "completed": completed, "traceback": traceback.format_exc()})
            for image_path, request in zip(image_paths[completed:], requests[completed:]):
                try:
                    with WorkerLogRedirect(self._log_path):
                        result = service.predict(request, threshold)

                    self._write_log({"event": "prediction_fallback_result", "path": str(image_path), "birds": len(result.get("birds", [])) if isinstance(result, dict) else None})
                    yield image_path, result, None
                except Exception as exc:
                    self._write_log({"event": "prediction_fallback_error", "path": str(image_path), "message": str(exc), "traceback": traceback.format_exc()})
                    yield image_path, None, exc


    def _cached_predictions_by_image(self, images: list[Path], model_fingerprint: str, min_classification_confidence: float) -> dict[str, dict[str, Any]]:
        cache = PredictionCache()
        result_filter = PredictionResultFilter(min_classification_confidence)
        cached: dict[str, dict[str, Any]] = {}
        entries_by_image = cache.lookup_many_for_model(images, model_fingerprint)
        for image_key, entry in entries_by_image.items():
            if entry is not None and isinstance(entry.get("result"), dict):
                cached[image_key] = result_filter.apply(entry["result"])

        return cached


    def _reuse_cached_predictions(self, images: list[Path], cached_predictions_by_image: dict[str, dict[str, Any]], threshold: float, store: CollectionStore, indexer: CollectionIndexer, processed_images: list[Path]) -> int:
        completed = 0
        for image_path in images:
            image_key = store.image_key(image_path)
            cached_prediction = cached_predictions_by_image.get(image_key)
            if cached_prediction is not None:
                indexer.add_prediction(image_path, cached_prediction, threshold)
                processed_images.append(image_path)
                completed += 1

        return completed


    def _required_string(self, request: dict[str, Any], key: str) -> str:
        value = request.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing collection field: {key}.")

        return value


    def _threshold(self, value: Any) -> float:
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            return DEFAULT_ACCEPTED_CLASSIFICATION_THRESHOLD

        if threshold < 0 or threshold > 1:
            return DEFAULT_ACCEPTED_CLASSIFICATION_THRESHOLD

        return threshold


    def _scan_mode(self, value: Any) -> str:
        return value if value in COLLECTION_SCAN_MODES else COLLECTION_SCAN_MODE_RAW_JPEG


    def _runtime_from_request(self, request: dict[str, Any]) -> RuntimeResolution:
        selection = request.get("_runtimeSelection")
        if isinstance(selection, dict):
            return RuntimeResolution(selection=ProviderSelector.from_dict(selection))

        return RuntimeResolution(selection=ProviderSelector.from_dict({"selected": ["CPUExecutionProvider"]}))


    def _prediction_service_for_runtime(self, runtime: RuntimeResolution) -> PredictionService:
        runtime_key = json.dumps(runtime.selection.__dict__, sort_keys=True)
        if self._prediction_service is None or self._runtime_key != runtime_key:
            self._prediction_service = PredictionService(RuntimeConfig.load(), forced_runtime=runtime)
            self._runtime_key = runtime_key

        return self._prediction_service


    def _error_status(self, message: str) -> dict[str, Any]:
        return {"state": "error", "total": 0, "completed": 0, "errors": 1, "currentFile": "", "message": message, "error": message, "species": []}


    def _write(self, payload: dict[str, Any]) -> None:
        if not self._status_writer.write(payload):
            raise SystemExit(0)


    def _write_log(self, payload: dict[str, Any]) -> None:
        if not self._log_path:
            return

        try:
            log_path = Path(self._log_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"timestamp": datetime.now(timezone.utc).isoformat(), **payload}
            with log_path.open("a", encoding="utf-8", errors="replace") as handle:
                handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")
        except OSError:
            return


if __name__ == "__main__":
    CollectionWorker().run()

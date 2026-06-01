from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Iterator

from ..inference.providers import ProviderSelector, RuntimeResolution
from ..inference.services import PredictionService
from ..runtime.config import RuntimeConfig
from ..runtime.settings import DEFAULT_ACCEPTED_CLASSIFICATION_THRESHOLD, DEFAULT_GPX_MATCH_TOLERANCE_SECONDS, MAX_GPX_MATCH_TOLERANCE_SECONDS
from ..runtime.worker_io import WorkerLogRedirect, WorkerStatusWriter
from .services import BatchFileOrganizer, BatchGpxResolver, FOLDER_ERRORS, FOLDER_NO_BIRDS, FOLDER_UNCLASSIFIED


class BatchWorker:
    def __init__(self):
        self._prediction_service: PredictionService | None = None
        self._runtime_key: str | None = None
        self._log_path = sys.argv[1] if len(sys.argv) > 1 else None
        self._status_writer = WorkerStatusWriter()


    def run(self) -> None:
        line = sys.stdin.readline()
        if not line.strip():
            self._write({"state": "error", "error": "No batch request received."})
            return

        try:
            request = json.loads(line)
            runtime = self._runtime_from_request(request)
            request.pop("_runtimeSelection", None)
            self._run_batch(request, runtime)
        except Exception as exc:
            self._write({"state": "error", "error": str(exc), "message": str(exc), "traceback": traceback.format_exc(), "total": 0, "completed": 0, "copied": 0, "errors": 0, "currentFile": ""})


    def _run_batch(self, request: dict[str, Any], runtime: RuntimeResolution) -> None:
        source = Path(self._required_string(request, "sourceDirectory"))
        allow_non_empty_destination = request.get("allowNonEmptyDestination") is True
        destination = BatchFileOrganizer.prepare_destination(self._required_string(request, "destinationDirectory"), allow_non_empty_destination)
        gpx_paths = self._gpx_paths_from_request(request)
        accepted_classification_threshold = self._threshold(request.get("acceptedClassificationThreshold"))
        gpx_match_tolerance_seconds = self._gpx_match_tolerance_seconds(request.get("gpxMatchToleranceSeconds"))
        rename_files = request.get("renameFiles") is not False
        recursive = request.get("recursive") is not False
        images = BatchFileOrganizer.scan_images(source, recursive)
        resolver = BatchGpxResolver(gpx_paths, gpx_match_tolerance_seconds)
        total = len(images)
        completed = 0
        copied = 0
        errors = 0
        self._write({"state": "running", "total": total, "completed": completed, "copied": copied, "errors": errors, "currentFile": "", "message": f"Found {total} image(s)."})

        service = self._prediction_service_for_runtime(runtime)
        prepared_requests = self._prediction_requests_for_chunk(images, resolver)
        for image_path, result, error in self._prediction_results_for_chunk(prepared_requests, service, accepted_classification_threshold):
            current_file = str(image_path)
            if error is None and result is not None:
                confidence_threshold = self._confidence_threshold(result)
                target_folders = self._target_folders(result.get("birds", []), confidence_threshold)
                for folder_name in target_folders:
                    BatchFileOrganizer.copy_to_folder(image_path, destination, folder_name, rename_files)
                    copied += 1

                completed += 1
                self._write({"state": "running", "total": total, "completed": completed, "copied": copied, "errors": errors, "currentFile": current_file, "message": f"Copied to {len(target_folders)} folder(s)."})
            else:
                errors += 1
                try:
                    BatchFileOrganizer.copy_to_folder(image_path, destination, FOLDER_ERRORS, rename_files)
                    copied += 1
                except Exception:
                    pass

                completed += 1
                self._write({"state": "running", "total": total, "completed": completed, "copied": copied, "errors": errors, "currentFile": current_file, "message": str(error)})

        self._write({"state": "done", "total": total, "completed": completed, "copied": copied, "errors": errors, "currentFile": "", "message": "Batch sorting complete."})


    def _target_folders(self, birds: list[dict[str, Any]], confidence_threshold: float) -> list[str]:
        if not birds:
            return [FOLDER_NO_BIRDS]

        targets = BatchFileOrganizer.species_targets(birds, confidence_threshold)
        if not targets:
            return [FOLDER_UNCLASSIFIED]

        return [target.folder_name for target in targets]


    def _prediction_requests_for_chunk(self, image_paths: list[Path], resolver: BatchGpxResolver) -> list[tuple[Path, dict[str, Any] | None, Exception | None]]:
        prepared_requests = []
        for image_path in image_paths:
            try:
                latitude, longitude, datetime_text = resolver.coordinates_for(image_path)
                request = {"imagePath": str(image_path), "latitude": "" if latitude is None else str(latitude), "longitude": "" if longitude is None else str(longitude), "datetime": datetime_text, "includePreview": False}
                prepared_requests.append((image_path, request, None))
            except Exception as exc:
                prepared_requests.append((image_path, None, exc))

        return prepared_requests


    def _prediction_results_for_chunk(self, prepared_requests: list[tuple[Path, dict[str, Any] | None, Exception | None]], service: PredictionService, accepted_classification_threshold: float) -> Iterator[tuple[Path, dict[str, Any] | None, Exception | None]]:
        valid_requests = [(index, image_path, request) for index, (image_path, request, error) in enumerate(prepared_requests) if request is not None and error is None]
        if not valid_requests:
            for image_path, _request, error in prepared_requests:
                yield image_path, None, error

            return

        completed = 0
        prediction_iterator = service.iter_predict_many([request for _index, _image_path, request in valid_requests], accepted_classification_threshold)
        try:
            for _index, image_path, _request in valid_requests:
                with WorkerLogRedirect(self._log_path):
                    result = next(prediction_iterator)

                completed += 1
                yield image_path, result, None

            for image_path, _request, error in prepared_requests:
                if error is not None:
                    yield image_path, None, error

            return
        except StopIteration:
            return
        except Exception:
            for _index, image_path, request in valid_requests[completed:]:
                try:
                    with WorkerLogRedirect(self._log_path):
                        result = service.predict(request, accepted_classification_threshold)

                    yield image_path, result, None
                except Exception as exc:
                    yield image_path, None, exc

            for image_path, _request, error in prepared_requests:
                if error is not None:
                    yield image_path, None, error


    def _confidence_threshold(self, result: dict[str, Any]) -> float:
        try:
            return float(result.get("acceptedClassificationThreshold", 0.5))
        except (TypeError, ValueError):
            return 0.5


    def _required_string(self, request: dict[str, Any], key: str) -> str:
        value = request.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing batch field: {key}.")

        return value


    def _gpx_paths_from_request(self, request: dict[str, Any]) -> list[str]:
        values = request.get("gpxPaths")
        if isinstance(values, list):
            return [value for value in values if isinstance(value, str) and value.strip()]

        legacy = request.get("gpxPath")
        if isinstance(legacy, str) and legacy.strip():
            return [legacy]

        return []


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


    def _threshold(self, value: Any) -> float:
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            return DEFAULT_ACCEPTED_CLASSIFICATION_THRESHOLD

        if threshold < 0 or threshold > 1:
            return DEFAULT_ACCEPTED_CLASSIFICATION_THRESHOLD

        return threshold


    def _gpx_match_tolerance_seconds(self, value: Any) -> int:
        try:
            seconds = int(value)
        except (TypeError, ValueError):
            return DEFAULT_GPX_MATCH_TOLERANCE_SECONDS

        if seconds < 1 or seconds > MAX_GPX_MATCH_TOLERANCE_SECONDS:
            return DEFAULT_GPX_MATCH_TOLERANCE_SECONDS

        return seconds


    def _write(self, payload: dict[str, Any]) -> None:
        if not self._status_writer.write(payload):
            raise SystemExit(0)


if __name__ == "__main__":
    BatchWorker().run()

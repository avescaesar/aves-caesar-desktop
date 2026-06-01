from __future__ import annotations

import base64
import json
import subprocess
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import webview

from .collection import CollectionJobs, CollectionStore
from .data.bird_names import BirdNamesLoader
from .data.gpx import GpxService
from .inference.cache import PredictionCache
from .inference.corrections import ManualCorrectionStore
from .inference.providers import ProviderSelection, RuntimeProbe, RuntimeResolution
from .inference.services import PredictionService
from .lightroom import LightroomBridgeServer, LightroomJobs, LightroomPluginManager, LightroomPredictionService
from .media.image_io import ImageLoader
from .organization import BatchJobs
from .organization.services import BatchFileOrganizer
from .runtime.config import RuntimeConfig
from .runtime.logs import LogFiles
from .runtime.model_metadata import ModelMetadata
from .runtime.paths import AppPaths
from .runtime.settings import DEFAULT_COLLECTION_SCAN_MODE, MAX_GPX_MATCH_TOLERANCE_SECONDS, UserSettings, VALID_COLLECTION_SCAN_MODES
from .runtime.updates import UpdateService
from .runtime.version import AppVersion
from .runtime.worker_process import WorkerProcessCommand


class BirdDesktopApi:
    def __init__(self, runtime: RuntimeResolution | None = None):
        self.config = RuntimeConfig.load()
        self._forced_runtime = runtime
        self._runtime_probe = RuntimeProbe(self.config)
        self._model_metadata = ModelMetadata(self.config)
        self._names = BirdNamesLoader(self.config.labels_path)
        self._available_app_languages = self._names.available_languages()
        self._prediction_service = PredictionService(self.config, self._runtime_probe, runtime)
        self._corrections = ManualCorrectionStore(names=self._names)
        self._prediction_jobs = PredictionJobs(self._runtime_probe)
        self._batch_jobs = BatchJobs(self._runtime_probe)
        self._collection_jobs = CollectionJobs(self._runtime_probe)
        self._collection_store = CollectionStore()
        self._settings = UserSettings.load()
        self._logs = LogFiles()
        self._logs.prune_old_logs()
        self._updates = UpdateService()
        self._lightroom_service = LightroomPredictionService(self._predict_now, self._predict_many_iter_now)
        self._lightroom_jobs = LightroomJobs(self._lightroom_service, lambda: self._settings.accepted_classification_threshold, lambda: self._settings.gpx_match_tolerance_seconds)
        self._lightroom_server = LightroomBridgeServer(self._lightroom_jobs)
        self._lightroom_server.start()
        self._lightroom_plugin = LightroomPluginManager(self._lightroom_server.port)


    def choose_image(self) -> dict[str, Any] | None:
        window = webview.windows[0]
        paths = window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False, file_types=("Images (*.jpg;*.jpeg;*.heic;*.heif;*.png;*.tif;*.tiff;*.dng;*.cr2;*.cr3;*.nef;*.arw;*.rw2;*.orf;*.raf)", "All files (*.*)"))
        if not paths:
            return None

        path = Path(paths[0])
        metadata = ImageLoader.read_metadata(path)
        return {"path": str(path), "latitude": metadata.latitude, "longitude": metadata.longitude, "datetime": metadata.datetime_text, "thumbnailDataUrl": self._prediction_service.thumbnail_data_url(path)}


    def runtime_info(self) -> dict[str, Any]:
        if self._forced_runtime is not None:
            return self._runtime_payload(self._forced_runtime)

        self._runtime_probe.start()
        runtime = self._runtime_probe.runtime_if_ready()
        return self._runtime_payload(runtime)


    def refresh_runtime(self) -> dict[str, Any]:
        self._runtime_probe.refresh()
        return self.runtime_info()


    def clear_prediction_cache(self) -> dict[str, int]:
        if self._has_running_jobs():
            raise RuntimeError("Stop running prediction, batch, or collection jobs before clearing the prediction cache.")

        return {"clearedEntries": self._prediction_service.clear_cache(), "clearedCollectionThumbnails": self._collection_store.clear_thumbnails()}


    def bird_names(self, language: str = "en") -> list[dict[str, str]]:
        return self._corrections.bird_names(self._names.normalize_language(language))


    def set_prediction_correction(self, image_path: str, bird_index: int, species_id: str) -> dict[str, Any]:
        return self._corrections.set(image_path, int(bird_index), species_id)


    def clear_prediction_correction(self, image_path: str, bird_index: int) -> dict[str, Any]:
        return self._corrections.clear(image_path, int(bird_index))


    def log_frontend_event(self, event: str, payload: dict[str, Any] | None = None) -> dict[str, str]:
        log_path = AppPaths.logs_dir() / "frontend-events.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": str(event),
            "payload": payload if isinstance(payload, dict) else {},
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

        return {"path": str(log_path)}


    def export_logs(self) -> dict[str, int | str]:
        return self._logs.export_to_desktop()


    def set_batch_directories(self, source_directory: str, destination_directory: str) -> dict[str, str]:
        self._settings.batch_source_directory = source_directory
        self._settings.batch_destination_directory = destination_directory
        self._settings.save()
        return {"batchSourceDirectory": self._settings.batch_source_directory, "batchDestinationDirectory": self._settings.batch_destination_directory}


    def set_batch_options(self, recursive: bool, rename_files: bool) -> dict[str, bool]:
        self._settings.batch_recursive = recursive
        self._settings.batch_rename_files = rename_files
        self._settings.save()
        return {"batchRecursive": self._settings.batch_recursive, "batchRenameFiles": self._settings.batch_rename_files}


    def set_collection_directory(self, path: str) -> dict[str, str]:
        self._settings.collection_directory = path
        self._settings.save()
        return {"collectionDirectory": self._settings.collection_directory}


    def set_collection_scan_mode(self, scan_mode: str) -> dict[str, str]:
        if scan_mode not in VALID_COLLECTION_SCAN_MODES:
            raise ValueError("Invalid collection scan mode.")

        self._settings.collection_scan_mode = scan_mode
        self._settings.save()
        return {"collectionScanMode": self._settings.collection_scan_mode}


    def set_collection_scan_enabled(self, enabled: bool) -> dict[str, bool]:
        self._settings.collection_scan_enabled = bool(enabled)
        self._settings.save()
        return {"collectionScanEnabled": self._settings.collection_scan_enabled}


    def set_accepted_classification_threshold(self, value: float) -> dict[str, float]:
        threshold = float(value)
        if threshold < 0 or threshold > 1:
            raise ValueError("Accepted classification threshold must be between 0 and 1.")

        self._settings.accepted_classification_threshold = threshold
        self._settings.save()
        return {"acceptedClassificationThreshold": self._settings.accepted_classification_threshold}


    def set_gpx_match_tolerance_seconds(self, value: int) -> dict[str, int]:
        seconds = int(value)
        if seconds < 1 or seconds > MAX_GPX_MATCH_TOLERANCE_SECONDS:
            raise ValueError("GPX match tolerance must be between 1 second and 24 hours.")

        self._settings.gpx_match_tolerance_seconds = seconds
        self._settings.save()
        return {"gpxMatchToleranceSeconds": self._settings.gpx_match_tolerance_seconds}


    def set_app_language_preference(self, preference: str) -> dict[str, str]:
        normalized_preference = str(preference or "system").strip().lower().split("-", 1)[0]
        if normalized_preference != "system" and normalized_preference not in self._available_app_languages:
            raise ValueError("Invalid application language preference.")

        self._settings.app_language_preference = normalized_preference
        self._settings.save()
        return {"appLanguagePreference": self._settings.app_language_preference}


    def choose_gpx(self) -> list[str] | None:
        window = webview.windows[0]
        paths = window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True, file_types=("GPX files (*.gpx)", "All files (*.*)"))
        return [str(path) for path in paths] if paths else None


    def choose_directory(self) -> str | None:
        window = webview.windows[0]
        paths = window.create_file_dialog(webview.FileDialog.FOLDER, allow_multiple=False)
        return str(paths[0]) if paths else None


    def directory_has_entries(self, path: str) -> bool:
        return BatchFileOrganizer.has_entries(path)


    def reveal_in_file_explorer(self, path: str) -> dict[str, str]:
        image_path = Path(path)
        if not image_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        subprocess.Popen(["explorer", "/select,", str(image_path)])
        return {"path": str(image_path)}


    def match_gpx(self, gpx_paths: list[str], photo_datetime: str | None) -> dict[str, Any] | None:
        paths = gpx_paths if isinstance(gpx_paths, list) else []
        match = GpxService.match_many(paths, photo_datetime, self._settings.gpx_match_tolerance_seconds)
        if match is None:
            return None

        return {"latitude": match.latitude, "longitude": match.longitude, "timestamp": match.timestamp, "secondsDelta": match.seconds_delta}


    def cached_prediction_preview(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._prediction_service.cached_prediction_preview(request, self._settings.accepted_classification_threshold)


    def start_predict(self, request: dict[str, Any]) -> dict[str, str]:
        request["acceptedClassificationThreshold"] = self._settings.accepted_classification_threshold
        return self._prediction_jobs.start(request)


    def prediction_status(self, job_id: str) -> dict[str, Any]:
        return self._prediction_jobs.status(job_id)


    def start_batch(self, request: dict[str, Any]) -> dict[str, str]:
        request["acceptedClassificationThreshold"] = self._settings.accepted_classification_threshold
        request["gpxMatchToleranceSeconds"] = self._settings.gpx_match_tolerance_seconds
        return self._batch_jobs.start(request)


    def batch_status(self, job_id: str) -> dict[str, Any]:
        return self._batch_jobs.status(job_id)


    def stop_batch(self, job_id: str) -> dict[str, Any]:
        return self._batch_jobs.stop(job_id)


    def start_collection_scan(self, request: dict[str, Any]) -> dict[str, str]:
        request["acceptedClassificationThreshold"] = self._settings.accepted_classification_threshold
        request["scanMode"] = request.get("scanMode") if request.get("scanMode") in VALID_COLLECTION_SCAN_MODES else self._settings.collection_scan_mode
        return self._collection_jobs.start(request)


    def collection_index(self, base_directory: str | None = None, scan_mode: str | None = None) -> dict[str, Any]:
        directory = base_directory or self._settings.collection_directory
        if not directory:
            return self._missing_collection_index("No collection directory selected.")

        selected_scan_mode = scan_mode if scan_mode in VALID_COLLECTION_SCAN_MODES else self._settings.collection_scan_mode or DEFAULT_COLLECTION_SCAN_MODE
        status = self._collection_store.load(directory, self._settings.accepted_classification_threshold, PredictionCache.model_fingerprint(self.config), self.config.min_classification_confidence, selected_scan_mode)
        if status is None:
            return self._missing_collection_index("No cached collection predictions.")

        return status


    def collection_status(self, job_id: str) -> dict[str, Any]:
        return self._collection_jobs.status(job_id)


    def stop_collection_scan(self, job_id: str) -> dict[str, Any]:
        return self._collection_jobs.stop(job_id)


    def lightroom_info(self) -> dict[str, Any]:
        plugin_info = self._lightroom_plugin.info()
        return {"server": self._lightroom_server.status(), "plugin": plugin_info}


    def install_lightroom_plugin(self) -> dict[str, Any]:
        return {"plugin": self._lightroom_plugin.install(), "server": self._lightroom_server.status()}


    def uninstall_lightroom_plugin(self) -> dict[str, Any]:
        return {"plugin": self._lightroom_plugin.uninstall(), "server": self._lightroom_server.status()}


    def update_info(self) -> dict[str, Any]:
        return self._updates.info()


    def check_for_updates(self) -> dict[str, Any]:
        return self._updates.check()


    def dismiss_update(self, version: str) -> dict[str, Any]:
        return self._updates.dismiss(version)


    def download_and_install_update(self) -> dict[str, Any]:
        return self._updates.start_download_and_install()


    def update_install_status(self, job_id: str) -> dict[str, Any]:
        return self._updates.install_status(job_id)


    def cancel_update_install(self, job_id: str) -> dict[str, Any]:
        return self._updates.cancel_install(job_id)


    def _predict_now(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._prediction_service.predict(request, self._settings.accepted_classification_threshold)


    def _predict_many_now(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._prediction_service.predict_many(requests, self._settings.accepted_classification_threshold)


    def _predict_many_iter_now(self, requests: list[dict[str, Any]]):
        return self._prediction_service.iter_predict_many(requests, self._settings.accepted_classification_threshold)


    def _runtime_payload(self, runtime: RuntimeResolution | None) -> dict[str, Any]:
        return {
            "appVersion": AppVersion.current(),
            "versionDetails": self._model_metadata.version_details(),
            "availableAppLanguages": self._available_app_languages,
            "batchSourceDirectory": self._settings.batch_source_directory,
            "batchDestinationDirectory": self._settings.batch_destination_directory,
            "batchRecursive": self._settings.batch_recursive,
            "batchRenameFiles": self._settings.batch_rename_files,
            "collectionDirectory": self._settings.collection_directory,
            "collectionScanMode": self._settings.collection_scan_mode,
            "collectionScanEnabled": self._settings.collection_scan_enabled,
            "acceptedClassificationThreshold": self._settings.accepted_classification_threshold,
            "gpxMatchToleranceSeconds": self._settings.gpx_match_tolerance_seconds,
            "appLanguagePreference": self._settings.app_language_preference,
            "appIconDataUrl": self._app_icon_data_url(),
            "runtimeProvider": self._runtime_provider_label(runtime.selection) if runtime else "",
            "runtimeDevice": self._runtime_device_label(runtime) if runtime else "Detecting...",
        }


    def _runtime_provider_label(self, selection: ProviderSelection) -> str:
        if not selection.selected:
            return "Unavailable"

        provider = selection.selected[0]
        labels = {
            "CUDAExecutionProvider": "CUDA",
            "DmlExecutionProvider": "DirectML",
            "CoreMLExecutionProvider": "CoreML",
            "CPUExecutionProvider": "CPU",
        }
        return labels.get(provider, provider)


    def _runtime_device_label(self, runtime: RuntimeResolution) -> str:
        if not runtime.selection.selected:
            return "Unavailable"

        provider = runtime.selection.selected[0]
        if provider == "CPUExecutionProvider":
            return "CPU"

        return f"GPU ({self._runtime_provider_label(runtime.selection)})"


    def _missing_collection_index(self, message: str) -> dict[str, Any]:
        return {"state": "missing", "total": 0, "completed": 0, "errors": 0, "currentFile": "", "message": message, "species": []}


    def _has_running_jobs(self) -> bool:
        return self._prediction_jobs.has_running() or self._batch_jobs.has_running() or self._collection_jobs.has_running() or self._lightroom_jobs.has_running()


    def _app_icon_data_url(self) -> str | None:
        path = AppPaths.app_icon()
        if not path.exists():
            return None

        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"


class PredictionJobs:
    def __init__(self, runtime_probe: RuntimeProbe):
        self._runtime_probe = runtime_probe
        self._worker = PredictionWorkerClient()
        self._jobs: dict[str, PredictionProcess] = {}


    def start(self, request: dict[str, Any]) -> dict[str, str]:
        job_id = uuid.uuid4().hex
        self._jobs[job_id] = PredictionProcess.start(request, self._runtime_probe, self._worker)
        return {"jobId": job_id}


    def status(self, job_id: str) -> dict[str, Any]:
        job = self._jobs.get(job_id)
        if job is None:
            return {"state": "missing", "error": "Prediction job not found."}

        if not job.done():
            return {"state": "running"}

        return job.result()


    def has_running(self) -> bool:
        return any(not job.done() for job in self._jobs.values())


class PredictionWorkerClient:
    _executor = ThreadPoolExecutor(max_workers=1)

    def __init__(self):
        self._process: subprocess.Popen[str] | None = None


    def submit(self, request: dict[str, Any], runtime_probe: RuntimeProbe) -> Future[dict[str, Any]]:
        return self._executor.submit(self._predict, dict(request), runtime_probe)


    def _predict(self, request: dict[str, Any], runtime_probe: RuntimeProbe) -> dict[str, Any]:
        runtime = runtime_probe.runtime()
        request["_runtimeSelection"] = runtime.selection.__dict__
        process = self._ensure_process()
        if process.stdin is None or process.stdout is None:
            raise RuntimeError("Prediction worker is not available.")

        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        return self._read_response(process)


    def _ensure_process(self) -> subprocess.Popen[str]:
        if self._process is not None and self._process.poll() is None:
            return self._process

        log_path = AppPaths.logs_dir() / "prediction-worker.log"
        command = WorkerProcessCommand("prediction_worker").with_log_path(log_path)
        self._process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", **WorkerProcessCommand.hidden_window_options())
        return self._process


    def _read_response(self, process: subprocess.Popen[str]) -> dict[str, Any]:
        if process.stdout is None:
            raise RuntimeError("Prediction worker stdout is not available.")

        while True:
            line = process.stdout.readline()
            if line == "":
                raise RuntimeError("Prediction worker stopped unexpectedly.")

            if line.startswith("{"):
                return json.loads(line)


class PredictionProcess:
    def __init__(self, future: Future[dict[str, Any]], started_at: float):
        self._future = future
        self._started_at = started_at
        self._result: dict[str, Any] | None = None


    @staticmethod
    def start(request: dict[str, Any], runtime_probe: RuntimeProbe, worker: PredictionWorkerClient) -> "PredictionProcess":
        started_at = time.perf_counter()
        future = worker.submit(request, runtime_probe)
        return PredictionProcess(future, started_at)


    def done(self) -> bool:
        return self._future.done()


    def result(self) -> dict[str, Any]:
        if self._result is not None:
            return self._result

        try:
            self._result = self._future.result()
        except Exception as exc:
            self._result = {"state": "error", "error": str(exc)}
            return self._result

        if self._result.get("state") == "done" and isinstance(self._result.get("result"), dict):
            self._result["result"]["elapsedSeconds"] = round(time.perf_counter() - self._started_at, 3)

        return self._result

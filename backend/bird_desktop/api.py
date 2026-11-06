from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import webview
from PIL import Image

from .collection import CollectionJobs, CollectionStore
from .data.bird_names import BirdNamesLoader
from .data.gpx import GpxService
from .inference.cache import PredictionCache
from .inference.corrections import ManualCorrectionStore
from .inference.providers import ProviderSelection, RuntimeProbe, RuntimeResolution
from .inference.services import PredictionService
from .lightroom import LightroomBridgeServer, LightroomJobs, LightroomPluginManager, LightroomPredictionService
from .media.exiftool import ExifTool
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
from .runtime.worker_lifecycle import workers


MAX_EBIRD_PHOTO_BYTES = 9_500_000


def _export_photo_as_jpeg(source: Path, destination: Path) -> bool:
    """Export a compatible JPEG and keep it below eBird's 10 MB image limit."""
    is_raw = ExifTool.is_raw_file(source)
    is_jpeg = source.suffix.lower() in {".jpg", ".jpeg"}
    if is_jpeg and not is_raw and source.stat().st_size <= MAX_EBIRD_PHOTO_BYTES:
        shutil.copy2(source, destination)
        return False

    loaded = ImageLoader.load(source)
    working = loaded.image.copy()
    exif_data = loaded.image.info.get("exif")
    quality = 95
    try:
        while True:
            working.save(destination, format="JPEG", quality=quality, optimize=True, exif=exif_data or b"")
            if is_raw:
                ExifTool.copy_metadata(source, destination)
            if destination.stat().st_size <= MAX_EBIRD_PHOTO_BYTES:
                return True

            if quality > 60:
                quality -= 5
                continue

            width, height = working.size
            if min(width, height) <= 320:
                destination.unlink(missing_ok=True)
                raise RuntimeError(f"Could not reduce {source.name} below the eBird photo size limit.")
            resized = working.resize((max(1, int(width * 0.85)), max(1, int(height * 0.85))), Image.Resampling.LANCZOS)
            working.close()
            working = resized
            quality = 90
    finally:
        working.close()
        ImageLoader.cleanup(loaded)


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
        self._ebird_export_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ebird-export")
        self._ebird_export_lock = Lock()
        self._ebird_export_jobs: dict[str, dict[str, Any]] = {}
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


    def start_ebird_package_export(self, csv_text: str, date: str, location: str, photos: list[dict[str, Any]]) -> dict[str, str] | None:
        window = webview.windows[0]
        paths = window.create_file_dialog(webview.FileDialog.FOLDER, allow_multiple=False)
        if not paths:
            return None

        parent = Path(paths if isinstance(paths, str) else paths[0])
        job_id = str(uuid.uuid4())
        total = sum(len(species.get("imagePaths", [])) for species in photos if isinstance(species, dict))
        with self._ebird_export_lock:
            self._ebird_export_jobs[job_id] = {
                "state": "running", "progress": 0, "processed": 0, "total": total,
                "current": "Preparing export folder...",
            }
        self._ebird_export_executor.submit(self._run_ebird_package_export, job_id, parent, csv_text, date, location, photos)
        return {"jobId": job_id}


    def ebird_export_status(self, job_id: str) -> dict[str, Any]:
        with self._ebird_export_lock:
            status = self._ebird_export_jobs.get(str(job_id))
            return dict(status) if status else {"state": "missing", "progress": 0, "processed": 0, "total": 0, "current": "Export job not found"}


    def _update_ebird_export_progress(self, job_id: str, processed: int, total: int, current: str) -> None:
        with self._ebird_export_lock:
            status = self._ebird_export_jobs.get(job_id)
            if status:
                status.update({"processed": processed, "total": total, "progress": int(processed * 100 / total) if total else 0, "current": current})


    def _run_ebird_package_export(self, job_id: str, parent: Path, csv_text: str, date: str, location: str, photos: list[dict[str, Any]]) -> None:
        try:
            result = self._write_ebird_package(parent, csv_text, date, location, photos, job_id)
        except Exception as exc:
            with self._ebird_export_lock:
                status = self._ebird_export_jobs.get(job_id)
                if status:
                    status.update({"state": "error", "error": str(exc), "current": "Export failed"})
        else:
            with self._ebird_export_lock:
                status = self._ebird_export_jobs.get(job_id)
                if status:
                    status.update({"state": "done", "progress": 100, "result": result, "current": "Export complete"})


    def _write_ebird_package(self, parent: Path, csv_text: str, date: str, location: str, photos: list[dict[str, Any]], job_id: str) -> dict[str, Any]:
        def safe_name(value: str, fallback: str) -> str:
            cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value)).strip(" ._")
            return cleaned[:100] or fallback

        folder_name = f"{safe_name(date, 'unknown-date')}_{safe_name(location, 'birding-location')}"
        output_directory = parent / folder_name
        suffix = 2
        while output_directory.exists():
            output_directory = parent / f"{folder_name} ({suffix})"
            suffix += 1

        output_directory.mkdir(parents=True)
        (output_directory / "aves-caesar-ebird-records.csv").write_text(str(csv_text), encoding="utf-8", newline="")
        exported_photos = 0
        converted_photos = 0
        total = sum(len(species.get("imagePaths", [])) for species in photos if isinstance(species, dict))
        processed = 0
        self._update_ebird_export_progress(job_id, processed, total, "Preparing photos...")
        for species in photos if isinstance(photos, list) else []:
            if not isinstance(species, dict):
                continue
            species_name = safe_name(str(species.get("name", "")), "unknown-species")
            species_directory = output_directory / species_name
            copied_names: set[str] = set()
            for raw_path in species.get("imagePaths", []):
                source = Path(str(raw_path))
                if not source.is_file():
                    processed += 1
                    self._update_ebird_export_progress(job_id, processed, total, f"Skipping missing photo: {source.name}")
                    continue
                keep_jpeg = source.suffix.lower() in {".jpg", ".jpeg"} and source.stat().st_size <= MAX_EBIRD_PHOTO_BYTES and not ExifTool.is_raw_file(source)
                destination_name = source.name if keep_jpeg else f"{source.stem}.jpg"
                stem, extension = Path(destination_name).stem, Path(destination_name).suffix
                duplicate_index = 2
                while destination_name.casefold() in copied_names:
                    destination_name = f"{stem} ({duplicate_index}){extension}"
                    duplicate_index += 1
                copied_names.add(destination_name.casefold())
                species_directory.mkdir(parents=True, exist_ok=True)
                destination = species_directory / destination_name
                converted_photos += int(_export_photo_as_jpeg(source, destination))
                exported_photos += 1
                processed += 1
                self._update_ebird_export_progress(job_id, processed, total, f"Exported {source.name}")

        return {"path": str(output_directory), "photoCount": exported_photos, "convertedPhotoCount": converted_photos}


    def save_ebird_csv(self, csv_text: str) -> dict[str, str] | None:
        window = webview.windows[0]
        paths = window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename="aves-caesar-ebird-records.csv",
            file_types=("CSV files (*.csv)",),
        )
        if not paths:
            return None

        output_path = Path(paths if isinstance(paths, str) else paths[0])
        if output_path.suffix.lower() != ".csv":
            output_path = output_path.with_suffix(".csv")
        output_path.write_text(str(csv_text), encoding="utf-8", newline="")
        return {"path": str(output_path)}


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


    def get_collection_view_preferences(self, directory: str) -> dict[str, Any]:
        key = self._collection_preferences_key(directory)
        preferences = (self._settings.collection_view_preferences or {}).get(key, {})
        return {"preferences": preferences}


    def set_collection_view_preferences(self, directory: str, preferences: dict[str, Any]) -> dict[str, str]:
        if not isinstance(preferences, dict):
            raise ValueError("Collection view preferences must be an object.")

        if self._settings.collection_view_preferences is None:
            self._settings.collection_view_preferences = {}
        self._settings.collection_view_preferences[self._collection_preferences_key(directory)] = preferences
        self._settings.save()
        return {"status": "saved"}


    def _collection_preferences_key(self, directory: str) -> str:
        return str(Path(str(directory or "").strip()).expanduser()).replace("\\", "/").rstrip("/").casefold()


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
        if self._process is not None:
            workers.stop(self._process)
        self._process = workers.start(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
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

from __future__ import annotations

import threading
import time
import uuid
import traceback
import json
from pathlib import Path
from typing import Any, Callable

from ..data.bird_names import BirdNamesLoader
from ..runtime.paths import AppPaths
from ..runtime.config import RuntimeConfig
from ..runtime.settings import DEFAULT_GPX_MATCH_TOLERANCE_SECONDS
from .services import LightroomPredictionService

ThresholdProvider = Callable[[], float]
GpxToleranceProvider = Callable[[], int]


class LightroomJobs:
    def __init__(self, service: LightroomPredictionService, threshold_provider: ThresholdProvider, gpx_tolerance_provider: GpxToleranceProvider | None = None):
        self._service = service
        self._threshold_provider = threshold_provider
        self._gpx_tolerance_provider = gpx_tolerance_provider or (lambda: DEFAULT_GPX_MATCH_TOLERANCE_SECONDS)
        self._jobs: dict[str, LightroomJob] = {}


    def start(self, request: dict[str, Any]) -> dict[str, Any]:
        files = request.get("files")
        if not isinstance(files, list):
            raise ValueError("Missing Lightroom files list.")

        paths = [str(path) for path in files if isinstance(path, str) and path.strip()]
        language = BirdNamesLoader(RuntimeConfig.load().labels_path).normalize_language(str(request.get("language") or "fr"))
        threshold = self._threshold_provider()
        gpx_match_tolerance_seconds = self._gpx_tolerance_provider()
        reprocess = request.get("reprocess") is True
        context = str(request.get("context") or "")
        gpx_paths = self._gpx_paths_from_request(request)
        job_id = uuid.uuid4().hex
        log_path = AppPaths.logs_dir() / f"lightroom-{job_id}.log"
        job = LightroomJob(job_id, paths, language, threshold, gpx_match_tolerance_seconds, reprocess, context, gpx_paths, log_path, self._service)
        self._jobs[job_id] = job
        job.start()
        return {"jobId": job_id, "total": len(paths)}


    def status(self, job_id: str) -> dict[str, Any]:
        job = self._jobs.get(job_id)
        if job is None:
            return {"state": "missing", "total": 0, "completed": 0, "errors": 0, "updated": 0, "empty": 0, "currentFile": "", "etaSeconds": None, "message": "Lightroom job not found."}

        return job.status()


    def results(self, job_id: str) -> dict[str, Any]:
        job = self._jobs.get(job_id)
        if job is None:
            return {"state": "missing", "results": [], "message": "Lightroom job not found."}

        return job.results()


    def has_running(self) -> bool:
        return any(job.running() for job in self._jobs.values())


    def client_log(self, job_id: str, payload: dict[str, Any]) -> dict[str, str]:
        job = self._jobs.get(job_id)
        if job is None:
            return {"state": "error", "message": "Lightroom job not found."}

        job.client_log(payload)
        return {"state": "ok"}


    def _gpx_paths_from_request(self, request: dict[str, Any]) -> list[str]:
        values = request.get("gpxPaths")
        if isinstance(values, list):
            return [value for value in values if isinstance(value, str) and value.strip()]

        legacy = request.get("gpxPath")
        if isinstance(legacy, str) and legacy.strip():
            return [legacy]

        return []


class LightroomJob:
    def __init__(self, job_id: str, paths: list[str], language: str, threshold: float, gpx_match_tolerance_seconds: int, reprocess: bool, context: str, gpx_paths: list[str], log_path: Path, service: LightroomPredictionService):
        self.job_id = job_id
        self._paths = paths
        self._language = language
        self._threshold = threshold
        self._gpx_match_tolerance_seconds = gpx_match_tolerance_seconds
        self._reprocess = reprocess
        self._context = context
        self._gpx_paths = gpx_paths
        self._log_path = log_path
        self._service = service
        self._lock = threading.Lock()
        self._results: list[dict[str, Any]] = []
        self._started_at = time.time()
        self._finished_at: float | None = None
        self._current_file = ""
        self._thread = threading.Thread(target=self._run, daemon=True)


    def start(self) -> None:
        self._thread.start()


    def status(self) -> dict[str, Any]:
        with self._lock:
            completed = len(self._results)
            errors = sum(1 for result in self._results if result.get("state") == "error")
            updated = sum(1 for result in self._results if result.get("state") == "ok" and result.get("keywords"))
            empty = sum(1 for result in self._results if result.get("state") == "ok" and not result.get("keywords"))
            state = "done" if self._finished_at is not None else "running"
            elapsed = (self._finished_at or time.time()) - self._started_at
            eta = self._eta_seconds(completed, elapsed)
            return {
                "state": state,
                "jobId": self.job_id,
                "context": self._context,
                "total": len(self._paths),
                "completed": completed,
                "errors": errors,
                "updated": updated,
                "empty": empty,
                "currentFile": self._current_file,
                "etaSeconds": eta,
                "elapsedSeconds": round(elapsed, 3),
                "reprocess": self._reprocess,
                "finishedAt": self._finished_at,
            }


    def results(self) -> dict[str, Any]:
        with self._lock:
            return {"state": "done" if self._finished_at is not None else "running", "jobId": self.job_id, "results": list(self._results)}


    def running(self) -> bool:
        return self.status().get("state") == "running"


    def client_log(self, payload: dict[str, Any]) -> None:
        self._write_log({"event": "lightroom_plugin", "payload": payload})


    def _run(self) -> None:
        self._write_log({"event": "start", "jobId": self.job_id, "total": len(self._paths), "language": self._language, "threshold": self._threshold, "gpxMatchToleranceSeconds": self._gpx_match_tolerance_seconds, "reprocess": self._reprocess, "context": self._context, "gpxPaths": self._gpx_paths})
        completed = 0
        try:
            with self._lock:
                self._current_file = self._paths[0] if self._paths else ""

            for result in self._process_paths(self._paths):
                completed += 1
                self._write_log({"event": "file", "result": result})
                with self._lock:
                    self._current_file = str(result.get("path") or "")
                    self._results.append(result)
        except Exception as exc:
            for path in self._paths[completed:]:
                result = {"path": path, "state": "error", "keywords": [], "species": [], "message": str(exc), "traceback": traceback.format_exc()}
                self._write_log({"event": "file", "result": result})
                with self._lock:
                    self._current_file = path
                    self._results.append(result)

        with self._lock:
            self._current_file = ""
            self._finished_at = time.time()

        self._write_log({"event": "done", **self.status()})


    def _eta_seconds(self, completed: int, elapsed: float) -> float | None:
        if completed <= 0 or completed >= len(self._paths):
            return None

        average = elapsed / completed
        remaining = len(self._paths) - completed
        return round(average * remaining, 1)


    def _process_paths(self, paths: list[str]):
        if hasattr(self._service, "iter_process_files"):
            yield from self._service.iter_process_files(paths, self._language, self._threshold, self._reprocess, self._gpx_paths, self._gpx_match_tolerance_seconds)
            return

        for path in paths:
            yield self._service.process_file(path, self._language, self._threshold, self._reprocess, self._gpx_paths, self._gpx_match_tolerance_seconds)


    def _write_log(self, payload: dict[str, Any]) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

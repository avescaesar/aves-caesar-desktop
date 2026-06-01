from __future__ import annotations

import json
import subprocess
import threading
import uuid
from typing import Any

from ..inference.providers import RuntimeProbe
from ..runtime.paths import AppPaths
from ..runtime.worker_process import WorkerProcessCommand


class CollectionJobs:
    def __init__(self, runtime_probe: RuntimeProbe):
        self._runtime_probe = runtime_probe
        self._jobs: dict[str, CollectionProcess] = {}


    def start(self, request: dict[str, Any]) -> dict[str, str]:
        job_id = uuid.uuid4().hex
        runtime = self._runtime_probe.runtime()
        request = dict(request)
        request["_runtimeSelection"] = runtime.selection.__dict__
        self._jobs[job_id] = CollectionProcess.start(job_id, request)
        return {"jobId": job_id}


    def status(self, job_id: str) -> dict[str, Any]:
        job = self._jobs.get(job_id)
        if job is None:
            return self._missing_status()

        return job.status()


    def stop(self, job_id: str) -> dict[str, Any]:
        job = self._jobs.get(job_id)
        if job is None:
            return self._missing_status()

        return job.stop()


    def has_running(self) -> bool:
        return any(job.running() for job in self._jobs.values())


    def _missing_status(self) -> dict[str, Any]:
        return {"state": "missing", "total": 0, "completed": 0, "errors": 0, "currentFile": "", "message": "Collection job not found.", "error": "Collection job not found.", "species": []}


class CollectionProcess:
    def __init__(self, process: subprocess.Popen[str]):
        self._process = process
        self._lock = threading.Lock()
        self._stop_requested = False
        self._status: dict[str, Any] = {"state": "running", "total": 0, "completed": 0, "errors": 0, "currentFile": "", "message": "Starting collection scan...", "species": []}
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()


    @staticmethod
    def start(job_id: str, request: dict[str, Any]) -> "CollectionProcess":
        log_path = AppPaths.logs_dir() / f"collection-{job_id}.log"
        command = WorkerProcessCommand("collection.worker").with_log_path(log_path)
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", **WorkerProcessCommand.hidden_window_options())
        if process.stdin is None:
            raise RuntimeError("Collection worker stdin is not available.")

        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.close()
        return CollectionProcess(process)


    def status(self) -> dict[str, Any]:
        with self._lock:
            status = dict(self._status)

        if status.get("state") in ("done", "stopped", "error", "missing"):
            return status

        returncode = self._process.poll()
        if returncode is None:
            return status

        if self._stop_requested:
            return self._terminal_status("stopped", "Collection scan stopped.")

        if returncode != 0:
            return self._terminal_status("error", "Collection worker stopped unexpectedly.")

        return status


    def stop(self) -> dict[str, Any]:
        self._stop_requested = True
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)

        return self._terminal_status("stopped", "Collection scan stopped.")


    def running(self) -> bool:
        return self.status().get("state") == "running"


    def _read_output(self) -> None:
        if self._process.stdout is None:
            self._terminal_status("error", "Collection worker stdout is not available.")
            return

        for line in self._process.stdout:
            if not line.startswith("{"):
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            with self._lock:
                self._status.update(payload)


    def _terminal_status(self, state: str, message: str) -> dict[str, Any]:
        with self._lock:
            self._status["state"] = state
            self._status["message"] = message
            status = dict(self._status)

        return status

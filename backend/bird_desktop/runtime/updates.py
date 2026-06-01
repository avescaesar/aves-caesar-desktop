from __future__ import annotations

import hashlib
import json
import subprocess
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from bird_desktop import __version__

from .paths import AppPaths
from .version import AppVersion


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    platform: str
    url: str
    sha256: str
    published_at: int


class UpdateService:
    ALLOW_DEVELOPMENT_UPDATES = False
    DEFAULT_MANIFEST_URL = "https://aves-caesar.com/releases/version.json"
    PLATFORM = "windows-x64"
    CHECK_TIMEOUT_SECONDS = 6
    DOWNLOAD_TIMEOUT_SECONDS = 30

    def __init__(self, manifest_url: str | None = None):
        self._manifest_url = manifest_url or self.DEFAULT_MANIFEST_URL
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._install_jobs: dict[str, UpdateInstallJob] = {}


    def info(self) -> dict[str, Any]:
        return {"flightId": self.flight_id(), "ignoredVersion": self._ignored_version()}


    def check(self) -> dict[str, Any]:
        app_version = AppVersion.current()
        current_version = self._current_version_for_update_check()
        if app_version == AppVersion.DEVELOPMENT_VERSION and not self.ALLOW_DEVELOPMENT_UPDATES:
            self._log("check_skipped_development", currentVersion=current_version)
            return self._status("development", current_version)

        self._log("check_started", currentVersion=current_version, developmentUpdates=self.ALLOW_DEVELOPMENT_UPDATES)
        manifest = self._fetch_manifest()
        if manifest is None:
            return self._status("error", current_version, error="Update check failed.")

        if manifest.platform != self.PLATFORM:
            self._log("platform_ignored", manifestPlatform=manifest.platform)
            return self._status("current", current_version)

        if self._compare_versions(manifest.version, current_version) <= 0:
            self._log("no_update", availableVersion=manifest.version, currentVersion=current_version)
            return self._status("current", current_version)

        ignored = self._ignored_version() == manifest.version
        self._log("update_available", availableVersion=manifest.version, currentVersion=current_version, ignored=ignored)
        return self._status("available", current_version, manifest, ignored=ignored)


    def dismiss(self, version: str) -> dict[str, Any]:
        normalized_version = str(version or "").strip()
        if not normalized_version:
            raise ValueError("Update version is required.")

        self._state_path().parent.mkdir(parents=True, exist_ok=True)
        self._write_state({**self._read_state(), "ignoredVersion": normalized_version})
        self._log("version_ignored", version=normalized_version)
        return {"ignoredVersion": normalized_version}


    def start_download_and_install(self) -> dict[str, str]:
        job_id = uuid.uuid4().hex
        job = UpdateInstallJob(job_id)
        self._install_jobs[job_id] = job
        job.future = self._executor.submit(self._download_and_install_job, job)
        return {"jobId": job_id}


    def install_status(self, job_id: str) -> dict[str, Any]:
        job = self._install_jobs.get(job_id)
        if job is None:
            return {"state": "missing", "message": "Update job not found.", "completedBytes": 0, "totalBytes": None, "progressPercent": None, "downloadSpeedBytesPerSecond": None}

        if job.future and job.future.done():
            try:
                job.future.result()
            except UpdateCancelledError:
                job.cancel()
            except Exception as exc:
                if not job.is_cancelled():
                    job.fail(str(exc))

        return job.status()


    def cancel_install(self, job_id: str) -> dict[str, Any]:
        job = self._install_jobs.get(job_id)
        if job is None:
            return {"state": "missing", "message": "Update job not found.", "completedBytes": 0, "totalBytes": None, "progressPercent": None, "downloadSpeedBytesPerSecond": None}

        job.cancel()
        if job.future is not None:
            job.future.cancel()

        self._log("install_cancel_requested", jobId=job_id)
        return job.status()


    def flight_id(self) -> str:
        state = self._read_state()
        existing = state.get("flightId")
        if isinstance(existing, str) and existing:
            return existing

        flight_id = str(uuid.uuid4())
        self._state_path().parent.mkdir(parents=True, exist_ok=True)
        self._write_state({**state, "flightId": flight_id})
        self._log("flight_id_created", flightId=flight_id)
        return flight_id


    def _fetch_manifest(self) -> UpdateManifest | None:
        url = f"{self._manifest_url}?flightId={quote(self.flight_id())}&t={int(time.time())}"
        try:
            request = Request(url, headers={"User-Agent": f"AvesCaesar/{self._current_version_for_update_check()}", "Cache-Control": "no-cache"})
            with urlopen(request, timeout=self.CHECK_TIMEOUT_SECONDS) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    self._log("check_failed_http", status=status)
                    return None

                payload = response.read().decode("utf-8")
        except Exception as exc:
            self._log("check_failed_network", error=str(exc))
            return None

        try:
            data = json.loads(payload)
            manifest = self._parse_manifest(data)
        except (json.JSONDecodeError, ValueError) as exc:
            self._log("check_failed_manifest", error=str(exc))
            return None

        self._log("manifest_received", version=manifest.version, platform=manifest.platform, url=manifest.url)
        return manifest


    def _parse_manifest(self, data: Any) -> UpdateManifest:
        if not isinstance(data, dict):
            raise ValueError("Manifest must be an object.")

        version = data.get("version")
        platform = data.get("platform")
        url = data.get("url")
        sha256 = data.get("sha256")
        published_at = data.get("publishedAt")
        if not all(isinstance(value, str) and value.strip() for value in [version, platform, url, sha256]):
            raise ValueError("Manifest is missing required fields.")

        if not isinstance(published_at, int) or published_at < 1_000_000_000_000:
            raise ValueError("Manifest publishedAt must be a Unix timestamp in milliseconds.")

        self._parse_version(version)
        if len(sha256.strip()) != 64:
            raise ValueError("Manifest sha256 must be 64 hex characters.")

        return UpdateManifest(version=version.strip(), platform=platform.strip(), url=url.strip(), sha256=sha256.strip().lower(), published_at=published_at)


    def _download_and_install_job(self, job: "UpdateInstallJob") -> None:
        job.update("checking", "Checking for updates.")
        check = self.check()
        self._raise_if_cancelled(job)
        if check.get("state") != "available":
            raise RuntimeError("No update is available.")

        manifest = self._manifest_from_status(check)
        installer_path = self._download_installer(manifest, job)
        self._raise_if_cancelled(job, installer_path)
        job.update("verifying", "Verifying update package.", installer_path=installer_path)
        self._verify_installer(installer_path, manifest.sha256)
        self._raise_if_cancelled(job, installer_path)
        command = self._installer_command(installer_path)
        self._log("installer_launching", installerPath=str(installer_path), command=command)
        job.update("installing", "Launching installer.", installer_path=installer_path)
        subprocess.Popen(command, cwd=str(installer_path.parent))
        job.update("done", "Installer launched.", installer_path=installer_path)


    def _download_installer(self, manifest: UpdateManifest, job: "UpdateInstallJob | None" = None) -> Path:
        url = self._resolve_url(manifest.url)
        destination = AppPaths.updates_dir() / f"AvesCaesarSetup-{manifest.version}-x64.exe"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if self._cached_installer_is_valid(destination, manifest.sha256):
            self._log("download_skipped_cached", version=manifest.version, destination=str(destination))
            return destination

        self._log("download_started", version=manifest.version, url=url, destination=str(destination))
        try:
            self._raise_if_cancelled(job, destination)
            request = Request(url, headers={"User-Agent": f"AvesCaesar/{self._current_version_for_update_check()}"})
            with urlopen(request, timeout=self.DOWNLOAD_TIMEOUT_SECONDS) as response:
                total_bytes = self._content_length(response)
                if job is not None:
                    job.update("downloading", "Downloading update.", total_bytes=total_bytes, installer_path=destination)

                with destination.open("wb") as handle:
                    completed_bytes = 0
                    while True:
                        self._raise_if_cancelled(job, destination)
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break

                        self._raise_if_cancelled(job, destination)
                        handle.write(chunk)
                        completed_bytes += len(chunk)
                        if job is not None:
                            job.update("downloading", "Downloading update.", completed_bytes=completed_bytes, total_bytes=total_bytes, installer_path=destination)
        except UpdateCancelledError:
            self._log("download_cancelled", destination=str(destination))
            self._delete_partial_installer(destination)
            raise
        except Exception as exc:
            self._log("download_failed", error=str(exc), destination=str(destination))
            self._delete_partial_installer(destination)

            raise RuntimeError("Update download failed.") from exc

        self._log("download_finished", destination=str(destination), size=destination.stat().st_size)
        return destination


    def _content_length(self, response: Any) -> int | None:
        try:
            value = response.headers.get("Content-Length")
        except AttributeError:
            return None

        try:
            length = int(value)
        except (TypeError, ValueError):
            return None

        return length if length > 0 else None


    def _verify_installer(self, installer_path: Path, expected_sha256: str) -> None:
        actual_sha256 = self._installer_sha256(installer_path)
        if actual_sha256 != expected_sha256:
            self._log("hash_invalid", installerPath=str(installer_path), expected=expected_sha256, actual=actual_sha256)
            raise RuntimeError("Downloaded update hash does not match the manifest.")

        self._log("hash_verified", installerPath=str(installer_path), sha256=actual_sha256)


    def _cached_installer_is_valid(self, installer_path: Path, expected_sha256: str) -> bool:
        if not installer_path.exists():
            return False

        actual_sha256 = self._installer_sha256(installer_path)
        if actual_sha256 == expected_sha256:
            self._log("cached_installer_valid", installerPath=str(installer_path), sha256=actual_sha256)
            return True

        self._log("cached_installer_invalid", installerPath=str(installer_path), expected=expected_sha256, actual=actual_sha256)
        self._delete_partial_installer(installer_path)
        return False


    def _installer_sha256(self, installer_path: Path) -> str:
        digest = hashlib.sha256()
        with installer_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)

        return digest.hexdigest()


    def _installer_command(self, installer_path: Path) -> list[str]:
        return [
            str(installer_path),
            "/SILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/SP-",
            "/TASKS=",
            "/UPDATE=1",
            f"/DELETEINSTALLER={installer_path}",
        ]


    def _manifest_from_status(self, status: dict[str, Any]) -> UpdateManifest:
        return UpdateManifest(version=str(status["availableVersion"]), platform=str(status["platform"]), url=str(status["url"]), sha256=str(status["sha256"]), published_at=int(status["publishedAt"]))


    def _raise_if_cancelled(self, job: "UpdateInstallJob | None", installer_path: Path | None = None) -> None:
        if job is None or not job.is_cancelled():
            return

        if installer_path is not None:
            self._delete_partial_installer(installer_path)

        self._log("install_cancelled", jobId=job.job_id)
        raise UpdateCancelledError("Update installation was cancelled.")


    def _delete_partial_installer(self, path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass


    def _current_version_for_update_check(self) -> str:
        current_version = AppVersion.current()
        if current_version == AppVersion.DEVELOPMENT_VERSION and self.ALLOW_DEVELOPMENT_UPDATES:
            return __version__

        return current_version


    def _status(self, state: str, current_version: str, manifest: UpdateManifest | None = None, ignored: bool = False, error: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {"state": state, "currentVersion": current_version, "availableVersion": None, "ignored": ignored, "error": error, "flightId": self.flight_id()}
        if manifest is not None:
            payload.update({"availableVersion": manifest.version, "platform": manifest.platform, "url": manifest.url, "sha256": manifest.sha256, "publishedAt": manifest.published_at})

        return payload


    def _resolve_url(self, url: str) -> str:
        return urljoin(self._manifest_url, url)


    def _ignored_version(self) -> str:
        ignored = self._read_state().get("ignoredVersion")
        return ignored if isinstance(ignored, str) else ""


    def _read_state(self) -> dict[str, Any]:
        path = self._state_path()
        if not path.exists():
            return {}

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        return data if isinstance(data, dict) else {}


    def _write_state(self, data: dict[str, Any]) -> None:
        self._state_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


    def _state_path(self) -> Path:
        return AppPaths.user_data_dir() / "updates.json"


    def _log(self, event: str, **payload: Any) -> None:
        try:
            log_path = AppPaths.logs_dir() / "updates.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, "payload": payload}
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError:
            return


    def _compare_versions(self, left: str, right: str) -> int:
        left_parts = self._parse_version(left)
        right_parts = self._parse_version(right)
        return (left_parts > right_parts) - (left_parts < right_parts)


    def _parse_version(self, value: str) -> tuple[int, int, int]:
        parts = value.split(".")
        if len(parts) != 3:
            raise ValueError(f"Unsupported version: {value}")

        try:
            return int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError as exc:
            raise ValueError(f"Unsupported version: {value}") from exc


class UpdateCancelledError(RuntimeError):
    pass


class UpdateInstallJob:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.future: Future[None] | None = None
        self._lock = Lock()
        self._state = "preparing"
        self._message = "Preparing update."
        self._completed_bytes = 0
        self._total_bytes: int | None = None
        self._installer_path = ""
        self._cancelled = False
        self._download_started_at: float | None = None


    def update(self, state: str, message: str, completed_bytes: int | None = None, total_bytes: int | None = None, installer_path: Path | None = None) -> None:
        with self._lock:
            if self._cancelled:
                return

            self._state = state
            self._message = message
            if state == "downloading" and self._download_started_at is None:
                self._download_started_at = time.monotonic()

            if completed_bytes is not None:
                self._completed_bytes = completed_bytes

            if total_bytes is not None:
                self._total_bytes = total_bytes

            if installer_path is not None:
                self._installer_path = str(installer_path)


    def fail(self, message: str) -> None:
        with self._lock:
            if self._cancelled:
                return

            self._state = "error"
            self._message = message


    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            self._state = "cancelled"
            self._message = "Update download cancelled."


    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled


    def status(self) -> dict[str, Any]:
        with self._lock:
            progress_percent = None
            if self._total_bytes and self._total_bytes > 0:
                progress_percent = min(100, round((self._completed_bytes / self._total_bytes) * 100))

            download_speed_bytes_per_second = self._download_speed_bytes_per_second()
            return {
                "jobId": self.job_id,
                "state": self._state,
                "message": self._message,
                "completedBytes": self._completed_bytes,
                "totalBytes": self._total_bytes,
                "progressPercent": progress_percent,
                "downloadSpeedBytesPerSecond": download_speed_bytes_per_second,
                "installerPath": self._installer_path,
            }


    def _download_speed_bytes_per_second(self) -> float | None:
        if self._state != "downloading" or self._download_started_at is None or self._completed_bytes <= 0:
            return None

        elapsed_seconds = time.monotonic() - self._download_started_at
        if elapsed_seconds <= 0:
            return None

        return self._completed_bytes / elapsed_seconds

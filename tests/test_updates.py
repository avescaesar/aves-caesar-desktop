from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from bird_desktop import __version__
from bird_desktop.runtime.paths import AppPaths
from bird_desktop.runtime.updates import UpdateInstallJob, UpdateService
from bird_desktop.runtime.version import AppVersion


class FakeResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self._payload = payload
        self.status = status
        self._offset = 0
        self.headers = {"Content-Length": str(len(payload))}


    def __enter__(self) -> "FakeResponse":
        return self


    def __exit__(self, *_args: Any) -> None:
        return None


    def read(self, size: int = -1) -> bytes:
        if size == -1:
            return self._payload

        chunk = self._payload[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk


class CancellingResponse(FakeResponse):
    def __init__(self, job: UpdateInstallJob):
        super().__init__(b"partial installer")
        self._job = job


    def read(self, size: int = -1) -> bytes:
        payload = super().read(size)
        if payload:
            self._job.cancel()

        return payload


@pytest.fixture()
def update_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    user_data = tmp_path / "Aves Caesar"
    monkeypatch.setattr(AppPaths, "user_data_dir", staticmethod(lambda: user_data))
    return user_data


def test_update_flight_id_is_stable(update_paths: Path) -> None:
    service = UpdateService("https://example.test/version.json")

    flight_id = service.flight_id()

    assert service.flight_id() == flight_id
    assert json.loads((update_paths / "updates.json").read_text(encoding="utf-8"))["flightId"] == flight_id


def test_update_check_detects_newer_version(monkeypatch: pytest.MonkeyPatch, update_paths: Path) -> None:
    manifest = {"version": "0.1.20", "platform": "windows-x64", "url": "/releases/AvesCaesarSetup-0.1.20-x64.exe", "sha256": "a" * 64, "publishedAt": 1779926400000}
    monkeypatch.setattr(AppVersion, "current", staticmethod(lambda: "0.1.19"))
    monkeypatch.setattr("bird_desktop.runtime.updates.urlopen", lambda *_args, **_kwargs: FakeResponse(json.dumps(manifest).encode("utf-8")))

    result = UpdateService("https://example.test/version.json").check()

    assert result["state"] == "available"
    assert result["availableVersion"] == "0.1.20"
    assert result["ignored"] is False


def test_update_check_can_run_in_development_with_constant(monkeypatch: pytest.MonkeyPatch, update_paths: Path) -> None:
    manifest = {"version": "99.0.0", "platform": "windows-x64", "url": "/releases/AvesCaesarSetup-99.0.0-x64.exe", "sha256": "a" * 64, "publishedAt": 1779926400000}
    monkeypatch.setattr(AppVersion, "current", staticmethod(lambda: AppVersion.DEVELOPMENT_VERSION))
    monkeypatch.setattr(UpdateService, "ALLOW_DEVELOPMENT_UPDATES", True)
    monkeypatch.setattr("bird_desktop.runtime.updates.urlopen", lambda *_args, **_kwargs: FakeResponse(json.dumps(manifest).encode("utf-8")))

    result = UpdateService("https://example.test/version.json").check()

    assert result["state"] == "available"
    assert result["currentVersion"] == __version__
    assert "check_skipped_development" not in (update_paths / "logs" / "updates.log").read_text(encoding="utf-8")


def test_update_check_adds_flight_id_and_timestamp_to_manifest_url(monkeypatch: pytest.MonkeyPatch, update_paths: Path) -> None:
    captured_urls: list[str] = []
    manifest = {"version": "0.1.19", "platform": "windows-x64", "url": "/releases/AvesCaesarSetup-0.1.19-x64.exe", "sha256": "a" * 64, "publishedAt": 1779926400000}
    monkeypatch.setattr(AppVersion, "current", staticmethod(lambda: "0.1.19"))
    monkeypatch.setattr("bird_desktop.runtime.updates.time.time", lambda: 1779926400)

    def capture_url(request: Any, **_kwargs: Any) -> FakeResponse:
        captured_urls.append(request.full_url)
        return FakeResponse(json.dumps(manifest).encode("utf-8"))

    monkeypatch.setattr("bird_desktop.runtime.updates.urlopen", capture_url)

    service = UpdateService("https://example.test/version.json")
    flight_id = service.flight_id()
    service.check()

    assert captured_urls == [f"https://example.test/version.json?flightId={flight_id}&t=1779926400"]


def test_update_check_marks_ignored_version(monkeypatch: pytest.MonkeyPatch, update_paths: Path) -> None:
    manifest = {"version": "0.1.20", "platform": "windows-x64", "url": "/releases/AvesCaesarSetup-0.1.20-x64.exe", "sha256": "a" * 64, "publishedAt": 1779926400000}
    service = UpdateService("https://example.test/version.json")
    service.dismiss("0.1.20")
    monkeypatch.setattr(AppVersion, "current", staticmethod(lambda: "0.1.19"))
    monkeypatch.setattr("bird_desktop.runtime.updates.urlopen", lambda *_args, **_kwargs: FakeResponse(json.dumps(manifest).encode("utf-8")))

    result = service.check()

    assert result["state"] == "available"
    assert result["ignored"] is True


def test_update_check_logs_network_errors(monkeypatch: pytest.MonkeyPatch, update_paths: Path) -> None:
    monkeypatch.setattr(AppVersion, "current", staticmethod(lambda: "0.1.19"))

    def fail_urlopen(*_args: Any, **_kwargs: Any) -> FakeResponse:
        raise OSError("offline")

    monkeypatch.setattr("bird_desktop.runtime.updates.urlopen", fail_urlopen)

    result = UpdateService("https://example.test/version.json").check()

    assert result["state"] == "error"
    assert "check_failed_network" in (update_paths / "logs" / "updates.log").read_text(encoding="utf-8")


def test_update_download_rejects_invalid_hash(monkeypatch: pytest.MonkeyPatch, update_paths: Path) -> None:
    manifest = {"version": "0.1.20", "platform": "windows-x64", "url": "/releases/AvesCaesarSetup-0.1.20-x64.exe", "sha256": "0" * 64, "publishedAt": 1779926400000}
    responses = [FakeResponse(json.dumps(manifest).encode("utf-8")), FakeResponse(b"installer")]
    monkeypatch.setattr(AppVersion, "current", staticmethod(lambda: "0.1.19"))
    monkeypatch.setattr("bird_desktop.runtime.updates.urlopen", lambda *_args, **_kwargs: responses.pop(0))

    service = UpdateService("https://example.test/version.json")
    job_id = service.start_download_and_install()["jobId"]
    status = service.install_status(job_id)
    while status["state"] not in {"error", "missing"}:
        status = service.install_status(job_id)

    assert "hash" in status["message"]
    assert "hash_invalid" in (update_paths / "logs" / "updates.log").read_text(encoding="utf-8")


def test_update_download_reports_progress(monkeypatch: pytest.MonkeyPatch, update_paths: Path) -> None:
    manifest = {"version": "0.1.20", "platform": "windows-x64", "url": "/releases/AvesCaesarSetup-0.1.20-x64.exe", "sha256": "0" * 64, "publishedAt": 1779926400000}
    responses = [FakeResponse(b"installer")]
    monkeypatch.setattr(AppVersion, "current", staticmethod(lambda: "0.1.19"))
    monkeypatch.setattr("bird_desktop.runtime.updates.urlopen", lambda *_args, **_kwargs: responses.pop(0))
    service = UpdateService("https://example.test/version.json")
    manifest_object = service._manifest_from_status({**manifest, "availableVersion": manifest["version"]})
    job = UpdateInstallJob("test")

    service._download_installer(manifest_object, job)
    status = job.status()

    assert status["state"] == "downloading"
    assert status["completedBytes"] == len(b"installer")
    assert status["totalBytes"] == len(b"installer")
    assert status["progressPercent"] == 100


def test_update_download_reports_average_speed(monkeypatch: pytest.MonkeyPatch) -> None:
    times = iter([100.0, 102.0])
    monkeypatch.setattr("bird_desktop.runtime.updates.time.monotonic", lambda: next(times))
    job = UpdateInstallJob("test")

    job.update("downloading", "Downloading update.", total_bytes=4 * 1024 * 1024)
    job.update("downloading", "Downloading update.", completed_bytes=2 * 1024 * 1024)
    status = job.status()

    assert status["downloadSpeedBytesPerSecond"] == 1024 * 1024


def test_update_download_reuses_valid_cached_installer(monkeypatch: pytest.MonkeyPatch, update_paths: Path) -> None:
    installer_content = b"installer"
    expected_sha256 = hashlib.sha256(installer_content).hexdigest()
    manifest = {"version": "0.1.20", "platform": "windows-x64", "url": "/releases/AvesCaesarSetup-0.1.20-x64.exe", "sha256": expected_sha256, "publishedAt": 1779926400000}
    cached_installer = update_paths / "cache" / "updates" / "AvesCaesarSetup-0.1.20-x64.exe"
    cached_installer.parent.mkdir(parents=True)
    cached_installer.write_bytes(installer_content)

    def fail_urlopen(*_args: Any, **_kwargs: Any) -> FakeResponse:
        raise AssertionError("Existing valid installer should not be downloaded again.")

    monkeypatch.setattr("bird_desktop.runtime.updates.urlopen", fail_urlopen)
    service = UpdateService("https://example.test/version.json")
    manifest_object = service._manifest_from_status({**manifest, "availableVersion": manifest["version"]})

    result = service._download_installer(manifest_object, UpdateInstallJob("test"))

    assert result == cached_installer
    assert "download_skipped_cached" in (update_paths / "logs" / "updates.log").read_text(encoding="utf-8")


def test_update_cancel_marks_job_cancelled(update_paths: Path) -> None:
    service = UpdateService("https://example.test/version.json")
    service._install_jobs["test"] = UpdateInstallJob("test")

    status = service.cancel_install("test")

    assert status["state"] == "cancelled"
    assert status["message"] == "Update download cancelled."


def test_update_download_cancel_removes_partial_installer(monkeypatch: pytest.MonkeyPatch, update_paths: Path) -> None:
    manifest = {"version": "0.1.20", "platform": "windows-x64", "url": "/releases/AvesCaesarSetup-0.1.20-x64.exe", "sha256": "0" * 64, "publishedAt": 1779926400000}
    monkeypatch.setattr("bird_desktop.runtime.updates.urlopen", lambda *_args, **_kwargs: CancellingResponse(job))
    service = UpdateService("https://example.test/version.json")
    manifest_object = service._manifest_from_status({**manifest, "availableVersion": manifest["version"]})
    job = UpdateInstallJob("test")

    with pytest.raises(RuntimeError, match="cancelled"):
        service._download_installer(manifest_object, job)

    assert not (update_paths / "cache" / "updates" / "AvesCaesarSetup-0.1.20-x64.exe").exists()


def test_update_installer_command_uses_visible_silent_upgrade_flags(tmp_path: Path) -> None:
    installer = tmp_path / "AvesCaesarSetup-0.1.20-x64.exe"
    installer.write_bytes(hashlib.sha256(b"unused").digest())

    command = UpdateService("https://example.test/version.json")._installer_command(installer)

    assert "/SILENT" in command
    assert "/VERYSILENT" not in command
    assert "/UPDATE=1" in command
    assert "/TASKS=" in command
    assert any(item.startswith("/DELETEINSTALLER=") for item in command)

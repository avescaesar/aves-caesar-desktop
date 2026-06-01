from __future__ import annotations

import errno
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from bird_desktop.runtime.worker_io import WorkerStatusWriter
from bird_desktop.runtime.worker_process import WorkerProcessCommand


class RaisingStream:
    def __init__(self, exc: Exception):
        self._exc = exc


    def write(self, _text: str) -> int:
        raise self._exc


    def flush(self) -> None:
        return None


def test_worker_command_uses_python_module_in_development(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "executable", "python.exe")
    monkeypatch.delattr(sys, "frozen", raising=False)

    command = WorkerProcessCommand("prediction_worker").with_log_path(tmp_path / "worker.log")

    assert command == ["python.exe", "-m", "bird_desktop.prediction_worker", str(tmp_path / "worker.log")]


def test_worker_command_uses_executable_dispatch_when_frozen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "executable", "AvesCaesar.exe")
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    command = WorkerProcessCommand("organization.worker").with_log_path(tmp_path / "worker.log")

    assert command == ["AvesCaesar.exe", "--bird-desktop-worker", "organization.worker", str(tmp_path / "worker.log")]


def test_worker_command_supports_collection_worker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "executable", "python.exe")
    monkeypatch.delattr(sys, "frozen", raising=False)

    command = WorkerProcessCommand("collection.worker").with_log_path(tmp_path / "worker.log")

    assert command == ["python.exe", "-m", "bird_desktop.collection.worker", str(tmp_path / "worker.log")]


def test_worker_hidden_window_options_hide_windows_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    options = WorkerProcessCommand.hidden_window_options()

    assert options["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert options["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert options["startupinfo"].wShowWindow == subprocess.SW_HIDE


def test_worker_hidden_window_options_are_empty_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    assert WorkerProcessCommand.hidden_window_options() == {}


def test_worker_status_writer_writes_json_line() -> None:
    stream = io.StringIO()

    assert WorkerStatusWriter(stream).write({"state": "done"}) is True

    assert json.loads(stream.getvalue()) == {"state": "done"}


def test_worker_status_writer_ignores_closed_parent_pipe() -> None:
    assert WorkerStatusWriter(RaisingStream(BrokenPipeError())).write({"state": "running"}) is False
    assert WorkerStatusWriter(RaisingStream(OSError(errno.EINVAL, "Invalid argument"))).write({"state": "running"}) is False
    assert WorkerStatusWriter(RaisingStream(OSError(errno.EPIPE, "Broken pipe"))).write({"state": "running"}) is False

from __future__ import annotations

import os
import time
import zipfile
from pathlib import Path

from bird_desktop.runtime.logs import LogFiles


def test_log_files_export_writes_zip_to_desktop(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    desktop_dir = tmp_path / "Desktop"
    logs_dir.mkdir()
    (logs_dir / "current.log").write_text("current", encoding="utf-8")

    result = LogFiles(logs_dir, desktop_dir).export_to_desktop()

    zip_path = Path(str(result["zipPath"]))
    assert zip_path.parent == desktop_dir
    assert result["logCount"] == 1
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.namelist() == ["current.log"]
        assert archive.read("current.log") == b"current"


def test_log_files_prunes_logs_older_than_48_hours(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    desktop_dir = tmp_path / "Desktop"
    logs_dir.mkdir()
    old_log = logs_dir / "old.log"
    current_log = logs_dir / "current.log"
    old_log.write_text("old", encoding="utf-8")
    current_log.write_text("current", encoding="utf-8")
    now = time.time()
    os.utime(old_log, (now - (49 * 60 * 60), now - (49 * 60 * 60)))
    os.utime(current_log, (now - (47 * 60 * 60), now - (47 * 60 * 60)))

    deleted_count = LogFiles(logs_dir, desktop_dir).prune_old_logs(now)

    assert deleted_count == 1
    assert not old_log.exists()
    assert current_log.exists()

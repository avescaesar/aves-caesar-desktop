from __future__ import annotations

import time
import zipfile
from datetime import datetime
from pathlib import Path

from .paths import AppPaths


class LogFiles:
    RETENTION_SECONDS = 48 * 60 * 60

    def __init__(self, logs_dir: Path | None = None, desktop_dir: Path | None = None):
        self._logs_dir = logs_dir or AppPaths.logs_dir()
        self._desktop_dir = desktop_dir or AppPaths.desktop_dir()


    def prune_old_logs(self, now: float | None = None) -> int:
        cutoff = (now if now is not None else time.time()) - self.RETENTION_SECONDS
        deleted_count = 0
        for path in self._log_files():
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    deleted_count += 1
            except OSError:
                continue

        return deleted_count


    def export_to_desktop(self) -> dict[str, int | str]:
        self.prune_old_logs()
        self._desktop_dir.mkdir(parents=True, exist_ok=True)
        zip_path = self._desktop_dir / f"AvesCaesar-logs-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        log_count = 0
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in self._log_files():
                try:
                    archive.write(path, path.relative_to(self._logs_dir))
                    log_count += 1
                except OSError:
                    continue

        return {"zipPath": str(zip_path), "logCount": log_count}


    def _log_files(self) -> list[Path]:
        if not self._logs_dir.exists():
            return []

        return sorted(path for path in self._logs_dir.rglob("*") if path.is_file())

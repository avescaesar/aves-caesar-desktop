from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any


class WorkerProcessCommand:
    FROZEN_WORKER_ARGUMENT = "--bird-desktop-worker"


    def __init__(self, module_name: str):
        self._module_name = module_name


    def with_log_path(self, log_path: Path) -> list[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable, self.FROZEN_WORKER_ARGUMENT, self._module_name, str(log_path)]

        return [sys.executable, "-m", f"bird_desktop.{self._module_name}", str(log_path)]


    @staticmethod
    def hidden_window_options() -> dict[str, Any]:
        if sys.platform != "win32":
            return {}

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": startupinfo}

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path


class AppRunner:
    ROOT = Path(__file__).resolve().parents[2]


    def __init__(self):
        self.system = platform.system().lower()
        self.venv_python = self._venv_python_path()
        self.npm = "npm.cmd" if self.system == "windows" else "npm"


    def run(self) -> None:
        self._ensure_venv()
        self._install_python_dependencies()
        self._ensure_exiftool()
        self._install_node_dependencies()
        self._run([self.npm, "run", "build"])
        self._run([str(self.venv_python), "-m", "bird_desktop"])


    def _venv_python_path(self) -> Path:
        executable = "python.exe" if self.system == "windows" else "python"
        scripts_dir = "Scripts" if self.system == "windows" else "bin"
        return self.ROOT / ".venv" / scripts_dir / executable


    def _ensure_venv(self) -> None:
        if self.venv_python.exists():
            return

        self._run([sys.executable, "-m", "venv", ".venv"])


    def _install_python_dependencies(self) -> None:
        self._run([str(self.venv_python), "-m", "pip", "install", "-r", self._requirements_file()])
        self._run([str(self.venv_python), "-m", "pip", "install", "-e", "."])


    def _requirements_file(self) -> str:
        if self.system == "windows":
            return "requirements-windows.txt"

        if self.system == "darwin":
            return "requirements-macos.txt"

        return "requirements-cpu.txt"


    def _ensure_exiftool(self) -> None:
        self._run([str(self.venv_python), "scripts/setup/install_exiftool.py"])


    def _install_node_dependencies(self) -> None:
        if self._node_executable_path("vite").exists():
            return

        self._run([self.npm, "install"])


    def _node_executable_path(self, name: str) -> Path:
        suffix = ".cmd" if self.system == "windows" else ""
        return self.ROOT / "node_modules" / ".bin" / f"{name}{suffix}"


    def _run(self, command: list[str]) -> None:
        print(" ".join(command))
        subprocess.run(command, cwd=self.ROOT, check=True)


AppRunner().run()

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


class InstallerBuilder:
    ROOT = Path(__file__).resolve().parents[2]
    WINDOWS_ARCHITECTURE = "x64"


    def run(self) -> None:
        version = self._package_version()
        source_dir = self.ROOT / "dist" / "AvesCaesar"
        if not (source_dir / "AvesCaesar.exe").exists():
            raise RuntimeError("Missing dist/AvesCaesar/AvesCaesar.exe. Run scripts/packaging/package.py --platform windows first.")

        output_dir = self.ROOT / "dist" / "installer"
        output_dir.mkdir(parents=True, exist_ok=True)
        command = [
            str(self._iscc_path()),
            str(self.ROOT / "installer" / "windows" / "AvesCaesar.iss"),
            f"/DAppVersion={version}",
            f"/DSourceDir={source_dir}",
            f"/DOutputDir={output_dir}",
        ]
        print(" ".join(command))
        subprocess.run(command, cwd=self.ROOT, check=True)
        print(f"Installer written to {output_dir / f'AvesCaesarSetup-{version}-{self.WINDOWS_ARCHITECTURE}.exe'}")


    def _package_version(self) -> str:
        package_json = json.loads((self.ROOT / "package.json").read_text(encoding="utf-8"))
        version = package_json.get("version")
        if not isinstance(version, str):
            raise RuntimeError("package.json does not contain a valid version.")

        return version


    def _iscc_path(self) -> Path:
        configured_path = os.environ.get("INNO_SETUP_ISCC")
        if configured_path:
            path = Path(configured_path)
            if path.exists():
                return path

            raise RuntimeError(f"INNO_SETUP_ISCC does not exist: {configured_path}")

        path_from_path = self._find_on_path()
        if path_from_path is not None:
            return path_from_path

        candidates = [
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
            Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

        raise RuntimeError("Could not find ISCC.exe. Set INNO_SETUP_ISCC to the full Inno Setup compiler path.")


    def _find_on_path(self) -> Path | None:
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            if not directory:
                continue

            candidate = Path(directory) / "ISCC.exe"
            if candidate.exists():
                return candidate

        return None


if __name__ == "__main__":
    if sys.platform != "win32":
        raise RuntimeError("The Inno Setup installer can only be built on Windows.")

    InstallerBuilder().run()

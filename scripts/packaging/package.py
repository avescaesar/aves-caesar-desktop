from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
from pathlib import Path


LIGHTROOM_LUA_PACKAGE = "bird_desktop.lightroom.lua"
REQUIRED_MODEL_PACKAGE_FILES = ["bird_detector.onnx", "bird_classifier.onnx", "bird_classifier.onnx.data", "species_mapping_v2.csv", "model-build-info.json"]
REQUIRED_ROOT_PACKAGE_FILES = ["runtime_config.json"]


class Packager:
    ROOT = Path(__file__).resolve().parents[2]


    def __init__(self):
        self.args = self._parse_args()
        self.npm = "npm.cmd" if platform.system() == "Windows" else "npm"
        self.separator = ";" if self.args.platform == "windows" else ":"


    def run(self) -> None:
        self._run([sys.executable, "scripts/setup/install_exiftool.py"])
        self._verify_exiftool_package_files()
        self._verify_model_package_files()
        version = self._write_release_version(self.args.version) if self.args.version else self._bump_patch_version()
        print(f"Packaging version {version}")
        self._run([self.npm, "run", "build"])
        self._run_pyinstaller()
        if self.args.install:
            self._run_installer()


    def _parse_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--platform", choices=["windows", "macos"], default="windows" if platform.system() == "Windows" else "macos")
        parser.add_argument("--install", action="store_true", help="Also build the Windows installer after the PyInstaller app.")
        parser.add_argument("--version", help="Use an exact app version instead of incrementing the current patch version.")
        return parser.parse_args()


    def _verify_exiftool_package_files(self) -> None:
        exiftool_dir = self.ROOT / "resources" / "exiftool"
        required = ["exiftool.exe", "exiftool_files"] if self.args.platform == "windows" else ["exiftool", "lib"]
        missing = [name for name in required if not (exiftool_dir / name).exists()]
        if missing:
            raise RuntimeError("ExifTool package files are missing from resources/exiftool: " + ", ".join(missing))


    def _verify_model_package_files(self) -> None:
        models_dir = self.ROOT / "resources" / "models"
        missing = [name for name in REQUIRED_MODEL_PACKAGE_FILES if not (models_dir / name).exists()]
        missing.extend(name for name in REQUIRED_ROOT_PACKAGE_FILES if not (self.ROOT / name).exists())
        if missing:
            raise RuntimeError("Model package files are missing from resources/models: " + ", ".join(missing))


    def _bump_patch_version(self) -> str:
        current = self._read_app_version()
        major, minor, patch = self._parse_version(current)
        version = f"{major}.{minor}.{patch + 1}"
        return self._write_release_version(version)


    def _write_release_version(self, version: str) -> str:
        self._parse_version(version)
        self._replace_version(self.ROOT / "backend" / "bird_desktop" / "__init__.py", r'(^__version__ = ")(\d+\.\d+\.\d+)(")', version)
        self._write_package_json_version(version)
        self._write_package_lock_version(version)
        return version


    def _read_app_version(self) -> str:
        contents = (self.ROOT / "backend" / "bird_desktop" / "__init__.py").read_text(encoding="utf-8")
        match = re.search(r'^__version__ = "(\d+\.\d+\.\d+)"', contents, flags=re.MULTILINE)
        if match is None:
            raise RuntimeError("backend/bird_desktop/__init__.py does not contain a valid version.")

        return match.group(1)


    def _parse_version(self, version: str) -> tuple[int, int, int]:
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
        if not match:
            raise RuntimeError(f"Unsupported version format: {version}")

        return int(match.group(1)), int(match.group(2)), int(match.group(3))


    def _write_package_json_version(self, version: str) -> None:
        path = self.ROOT / "package.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = version
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


    def _write_package_lock_version(self, version: str) -> None:
        path = self.ROOT / "package-lock.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = version
        if isinstance(data.get("packages"), dict) and isinstance(data["packages"].get(""), dict):
            data["packages"][""]["version"] = version

        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


    def _replace_version(self, path: Path, pattern: str, version: str) -> None:
        contents = path.read_text(encoding="utf-8")
        updated, count = re.subn(pattern, rf"\g<1>{version}\g<3>", contents, count=1, flags=re.MULTILINE)
        if count != 1:
            raise RuntimeError(f"Could not update version in {path}")

        path.write_text(updated, encoding="utf-8")


    def _run_pyinstaller(self) -> None:
        entrypoint = self.ROOT / "backend" / "run_bird_desktop.py"
        data_args = [
            "--add-data", f"frontend/dist{self.separator}frontend/dist",
            "--add-data", f"runtime_config.json{self.separator}.",
            "--add-data", f"resources{self.separator}resources",
            "--add-data", f"icon.png{self.separator}.",
        ]
        runtime_hook = self.ROOT / "scripts" / "packaging" / "pyinstaller_onnxruntime_runtime_hook.py"
        self._run([sys.executable, "-m", "PyInstaller", "--name", "AvesCaesar", "--windowed", "--noconfirm", "--paths", str(self.ROOT / "backend"), "--runtime-hook", str(runtime_hook), "--hidden-import", LIGHTROOM_LUA_PACKAGE, "--collect-data", LIGHTROOM_LUA_PACKAGE, *self._icon_args(), *data_args, str(entrypoint)])


    def _run_installer(self) -> None:
        if self.args.platform != "windows":
            raise RuntimeError("The Inno Setup installer can only be built for the windows platform.")

        self._run([sys.executable, "scripts/packaging/build_installer.py"])


    def _icon_args(self) -> list[str]:
        icon = self.ROOT / "icon.png"
        if not icon.exists():
            return []

        if self.args.platform == "windows":
            ico = self.ROOT / "build" / "aves-caesar.ico"
            ico.parent.mkdir(parents=True, exist_ok=True)
            from PIL import Image
            with Image.open(icon) as image:
                image.save(ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

            return ["--icon", str(ico)]

        return ["--icon", str(icon)]


    def _run(self, command: list[str]) -> None:
        print(" ".join(command))
        subprocess.run(command, cwd=self.ROOT, check=True)


if __name__ == "__main__":
    Packager().run()

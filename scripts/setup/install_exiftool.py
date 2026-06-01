from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path


class ExifToolInstaller:
    VERSION = "13.58"
    ROOT = Path(__file__).resolve().parents[2]
    TARGET = ROOT / "resources" / "exiftool"
    WINDOWS_URL = f"https://sourceforge.net/projects/exiftool/files/exiftool-{VERSION}_64.zip/download"
    UNIX_URL = f"https://sourceforge.net/projects/exiftool/files/Image-ExifTool-{VERSION}.tar.gz/download"


    def __init__(self):
        self.system = platform.system().lower()


    def ensure(self) -> Path:
        bundled = self._bundled_executable()
        if bundled and self._works(bundled):
            print(f"ExifTool already installed: {bundled}")
            return bundled

        self.TARGET.mkdir(parents=True, exist_ok=True)
        copied = self._copy_from_existing_install()
        if copied and self._works(copied):
            print(f"ExifTool installed from local copy: {copied}")
            return copied

        installed = self._download_and_install()
        print(f"ExifTool installed: {installed}")
        return installed


    def _bundled_executable(self) -> Path | None:
        executable = self.TARGET / ("exiftool.exe" if self.system == "windows" else "exiftool")
        return executable if executable.exists() else None


    def _copy_from_existing_install(self) -> Path | None:
        source = self._existing_install_dir()
        if source is None:
            return None

        return self._copy_install_dir(source)


    def _existing_install_dir(self) -> Path | None:
        env_home = os.environ.get("EXIFTOOL_HOME")
        candidates = [Path(env_home)] if env_home else []
        candidates.extend(self._known_windows_candidates())
        path_exe = shutil.which("exiftool")
        if path_exe:
            candidates.append(Path(path_exe).resolve().parent)

        for candidate in candidates:
            if self._install_dir_is_complete(candidate):
                return candidate

        return None


    def _known_windows_candidates(self) -> list[Path]:
        if self.system != "windows":
            return []

        user_root = self.ROOT.parents[1]
        return [
            user_root / "Photato2" / "app" / "softs" / "exiftool",
            user_root / "PhotoCuller2" / "node_modules" / "exiftool-vendored.exe" / "bin",
        ]


    def _install_dir_is_complete(self, path: Path) -> bool:
        if self.system == "windows":
            return (path / "exiftool.exe").exists() and (path / "exiftool_files").exists()

        return (path / "exiftool").exists() and (path / "lib").exists()


    def _copy_install_dir(self, source: Path) -> Path:
        executable_name = "exiftool.exe" if self.system == "windows" else "exiftool"
        support_name = "exiftool_files" if self.system == "windows" else "lib"
        shutil.copy2(source / executable_name, self.TARGET / executable_name)
        support_target = self.TARGET / support_name
        if support_target.exists():
            shutil.rmtree(support_target)

        shutil.copytree(source / support_name, support_target)
        self._make_executable(self.TARGET / executable_name)
        return self.TARGET / executable_name


    def _download_and_install(self) -> Path:
        with tempfile.TemporaryDirectory(prefix="bird-exiftool-") as temp_name:
            temp = Path(temp_name)
            archive = temp / ("exiftool.zip" if self.system == "windows" else "exiftool.tar.gz")
            self._download(self.WINDOWS_URL if self.system == "windows" else self.UNIX_URL, archive)
            return self._install_windows_archive(archive, temp) if self.system == "windows" else self._install_unix_archive(archive, temp)


    def _download(self, url: str, destination: Path) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": "bird-desktop-installer"})
        with urllib.request.urlopen(request) as response:
            destination.write_bytes(response.read())


    def _install_windows_archive(self, archive: Path, temp: Path) -> Path:
        with zipfile.ZipFile(archive) as zip_file:
            zip_file.extractall(temp)

        source = self._find_extracted_dir("exiftool*.exe", "exiftool_files", temp)
        return self._copy_install_dir(source)


    def _install_unix_archive(self, archive: Path, temp: Path) -> Path:
        with tarfile.open(archive) as tar_file:
            tar_file.extractall(temp)

        source = self._find_extracted_dir("exiftool", "lib", temp)
        return self._copy_install_dir(source)


    def _find_extracted_dir(self, executable_pattern: str, support_name: str, temp: Path) -> Path:
        for executable in temp.rglob(executable_pattern):
            source = executable.parent
            if (source / support_name).exists():
                if self.system == "windows" and executable.name != "exiftool.exe":
                    executable.rename(source / "exiftool.exe")

                return source

        raise RuntimeError("Downloaded ExifTool archive did not contain a complete installation.")


    def _make_executable(self, path: Path) -> None:
        if self.system != "windows":
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


    def _works(self, executable: Path) -> bool:
        return subprocess.run([str(executable), "-ver"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0


ExifToolInstaller().ensure()

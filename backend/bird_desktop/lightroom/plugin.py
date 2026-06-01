from __future__ import annotations

import os
import platform
import re
import shutil
from importlib.resources import files
from pathlib import Path


PLUGIN_NAME = "Aves.lrplugin"
LUA_PACKAGE = "bird_desktop.lightroom.lua"
BASE_URL_TOKEN = "__AVES_LIGHTROOM_BASE_URL__"
PLUGIN_VERSION_PATTERN = re.compile(r"PLUGIN_VERSION\s*=\s*['\"]([^'\"]+)['\"]")
INFO_VERSION_PATTERN = re.compile(r"VERSION\s*=\s*\{\s*major\s*=\s*(\d+),\s*minor\s*=\s*(\d+),\s*revision\s*=\s*(\d+),\s*build\s*=\s*(\d+)")


class LightroomPluginManager:
    def __init__(self, port: int):
        self.port = port


    def info(self) -> dict[str, str | bool | None]:
        install_path = self.install_path()
        installed = install_path.exists() if install_path is not None else False
        installed_version = self._installed_version(install_path) if install_path is not None and installed else None
        return {
            "installed": installed,
            "installedVersion": installed_version,
            "availableVersion": self._available_version(),
            "port": str(self.port),
        }


    def install(self) -> dict[str, str | bool | None]:
        install_path = self.install_path()
        if install_path is None:
            raise RuntimeError("Lightroom Modules directory is not supported on this platform.")

        self.create_plugin(install_path)
        return self.info()


    def uninstall(self) -> dict[str, str | bool | None]:
        install_path = self.install_path()
        if install_path is None:
            raise RuntimeError("Lightroom Modules directory is not supported on this platform.")

        if install_path.exists():
            shutil.rmtree(install_path)

        return self.info()


    def create_plugin(self, plugin_path: Path) -> Path:
        if plugin_path.exists():
            shutil.rmtree(plugin_path)

        plugin_path.mkdir(parents=True)
        files_by_name = self._plugin_files()
        for name, contents in files_by_name.items():
            (plugin_path / name).write_text(contents, encoding="utf-8", newline="\n")

        return plugin_path


    def install_path(self) -> Path | None:
        system = platform.system().lower()
        if system == "windows":
            appdata = os.environ.get("APPDATA")
            if not appdata:
                return None

            return Path(appdata) / "Adobe" / "Lightroom" / "Modules" / PLUGIN_NAME

        if system == "darwin":
            return Path.home() / "Library" / "Application Support" / "Adobe" / "Lightroom" / "Modules" / PLUGIN_NAME

        return None


    def _plugin_files(self) -> dict[str, str]:
        result: dict[str, str] = {}
        base_url = f"http://127.0.0.1:{self.port}/api/lightroom"
        for resource in files(LUA_PACKAGE).iterdir():
            if resource.name.endswith(".lua"):
                result[resource.name] = resource.read_text(encoding="utf-8").replace(BASE_URL_TOKEN, base_url)

        return result


    def _available_version(self) -> str | None:
        aves_plugin = files(LUA_PACKAGE).joinpath("AvesPlugin.lua")
        return self._version_from_text(aves_plugin.read_text(encoding="utf-8"))


    def _installed_version(self, plugin_path: Path) -> str | None:
        aves_plugin_path = plugin_path / "AvesPlugin.lua"
        if aves_plugin_path.exists():
            version = self._version_from_text(aves_plugin_path.read_text(encoding="utf-8"))
            if version is not None:
                return version

        info_path = plugin_path / "Info.lua"
        if info_path.exists():
            return self._version_from_text(info_path.read_text(encoding="utf-8"))

        return None


    def _version_from_text(self, text: str) -> str | None:
        plugin_version_match = PLUGIN_VERSION_PATTERN.search(text)
        if plugin_version_match is not None:
            return plugin_version_match.group(1)

        info_version_match = INFO_VERSION_PATTERN.search(text)
        if info_version_match is None:
            return None

        major, minor, revision, build = info_version_match.groups()
        version = f"{major}.{minor}.{revision}"
        if int(build) > 0:
            version = f"{version}.{build}"

        return version

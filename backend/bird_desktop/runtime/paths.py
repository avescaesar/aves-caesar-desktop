from __future__ import annotations

import sys
import os
from pathlib import Path


class AppPaths:
    @staticmethod
    def app_root() -> Path:
        if getattr(sys, "frozen", False):
            bundle_root = getattr(sys, "_MEIPASS", None)
            if bundle_root:
                return Path(bundle_root).resolve()

            return Path(sys.executable).resolve().parent

        return Path(__file__).resolve().parents[3]


    @staticmethod
    def frontend_index() -> Path:
        return AppPaths.app_root() / "frontend" / "dist" / "index.html"


    @staticmethod
    def app_icon() -> Path:
        return AppPaths.app_root() / "icon.png"


    @staticmethod
    def app_window_icon() -> Path:
        return AppPaths.app_root() / "resources" / "aves-caesar.ico"


    @staticmethod
    def models_dir() -> Path:
        if getattr(sys, "frozen", False):
            return AppPaths.resources_dir() / "models"

        return AppPaths.app_root() / "models"


    @staticmethod
    def model_build_info() -> Path:
        return AppPaths.models_dir() / "model-build-info.json"


    @staticmethod
    def resources_dir() -> Path:
        return AppPaths.app_root() / "resources"


    @staticmethod
    def logs_dir() -> Path:
        return AppPaths.user_data_dir() / "logs"


    @staticmethod
    def desktop_dir() -> Path:
        return Path.home() / "Desktop"


    @staticmethod
    def user_data_dir() -> Path:
        app_name = "Aves Caesar" if getattr(sys, "frozen", False) else "Aves Caesar Dev"
        if sys.platform == "win32":
            return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / app_name

        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / app_name

        unix_name = "aves-caesar" if getattr(sys, "frozen", False) else "aves-caesar-dev"
        return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / unix_name


    @staticmethod
    def cache_dir() -> Path:
        return AppPaths.user_data_dir() / "cache"


    @staticmethod
    def updates_dir() -> Path:
        return AppPaths.cache_dir() / "updates"

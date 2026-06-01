from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import AppPaths


DEFAULT_ACCEPTED_CLASSIFICATION_THRESHOLD = 0.5
DEFAULT_GPX_MATCH_TOLERANCE_SECONDS = 300
MAX_GPX_MATCH_TOLERANCE_SECONDS = 86400
VALID_COLLECTION_SCAN_MODES = {"raw", "jpeg", "raw_jpeg"}
DEFAULT_COLLECTION_SCAN_MODE = "raw_jpeg"
DEFAULT_APP_LANGUAGE_PREFERENCE = "system"


@dataclass
class UserSettings:
    batch_source_directory: str = ""
    batch_destination_directory: str = ""
    batch_recursive: bool = True
    batch_rename_files: bool = True
    collection_directory: str = ""
    collection_scan_mode: str = DEFAULT_COLLECTION_SCAN_MODE
    collection_scan_enabled: bool = False
    accepted_classification_threshold: float = DEFAULT_ACCEPTED_CLASSIFICATION_THRESHOLD
    gpx_match_tolerance_seconds: int = DEFAULT_GPX_MATCH_TOLERANCE_SECONDS
    app_language_preference: str = DEFAULT_APP_LANGUAGE_PREFERENCE

    @staticmethod
    def load() -> "UserSettings":
        data = UserSettingsStore.read()
        source_directory = data.get("batchSourceDirectory")
        destination_directory = data.get("batchDestinationDirectory")
        recursive = data.get("batchRecursive")
        rename_files = data.get("batchRenameFiles")
        collection_directory = data.get("collectionDirectory")
        collection_scan_mode = data.get("collectionScanMode")
        collection_scan_enabled = data.get("collectionScanEnabled")
        accepted_classification_threshold = UserSettings._threshold(data.get("acceptedClassificationThreshold"))
        gpx_match_tolerance_seconds = UserSettings._gpx_match_tolerance_seconds(data.get("gpxMatchToleranceSeconds"))
        app_language_preference = UserSettings._app_language_preference(data.get("appLanguagePreference"))
        return UserSettings(batch_source_directory=source_directory if isinstance(source_directory, str) else "", batch_destination_directory=destination_directory if isinstance(destination_directory, str) else "", batch_recursive=recursive if isinstance(recursive, bool) else True, batch_rename_files=rename_files if isinstance(rename_files, bool) else True, collection_directory=collection_directory if isinstance(collection_directory, str) else "", collection_scan_mode=collection_scan_mode if collection_scan_mode in VALID_COLLECTION_SCAN_MODES else DEFAULT_COLLECTION_SCAN_MODE, collection_scan_enabled=collection_scan_enabled if isinstance(collection_scan_enabled, bool) else False, accepted_classification_threshold=accepted_classification_threshold, gpx_match_tolerance_seconds=gpx_match_tolerance_seconds, app_language_preference=app_language_preference)


    def save(self) -> None:
        path = UserSettingsStore.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"batchSourceDirectory": self.batch_source_directory, "batchDestinationDirectory": self.batch_destination_directory, "batchRecursive": self.batch_recursive, "batchRenameFiles": self.batch_rename_files, "collectionDirectory": self.collection_directory, "collectionScanMode": self.collection_scan_mode, "collectionScanEnabled": self.collection_scan_enabled, "acceptedClassificationThreshold": self.accepted_classification_threshold, "gpxMatchToleranceSeconds": self.gpx_match_tolerance_seconds, "appLanguagePreference": self.app_language_preference}

        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


    @staticmethod
    def _threshold(value: Any) -> float:
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            return DEFAULT_ACCEPTED_CLASSIFICATION_THRESHOLD

        if threshold < 0 or threshold > 1:
            return DEFAULT_ACCEPTED_CLASSIFICATION_THRESHOLD

        return threshold


    @staticmethod
    def _gpx_match_tolerance_seconds(value: Any) -> int:
        try:
            seconds = int(value)
        except (TypeError, ValueError):
            return DEFAULT_GPX_MATCH_TOLERANCE_SECONDS

        if seconds < 1 or seconds > MAX_GPX_MATCH_TOLERANCE_SECONDS:
            return DEFAULT_GPX_MATCH_TOLERANCE_SECONDS

        return seconds


    @staticmethod
    def _app_language_preference(value: Any) -> str:
        if not isinstance(value, str):
            return DEFAULT_APP_LANGUAGE_PREFERENCE

        preference = value.strip().lower().split("-", 1)[0]
        return preference if preference else DEFAULT_APP_LANGUAGE_PREFERENCE


class UserSettingsStore:
    @staticmethod
    def settings_path() -> Path:
        return AppPaths.user_data_dir() / "settings.json"


    @staticmethod
    def read() -> dict[str, Any]:
        path = UserSettingsStore.settings_path()
        if not path.exists():
            return {}

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        return data if isinstance(data, dict) else {}

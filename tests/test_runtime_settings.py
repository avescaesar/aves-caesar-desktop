from __future__ import annotations

import json
from pathlib import Path

import pytest

from bird_desktop.runtime.settings import UserSettings, UserSettingsStore


def test_user_settings_loads_batch_recursive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"batchRecursive": False}), encoding="utf-8")
    monkeypatch.setattr(UserSettingsStore, "settings_path", staticmethod(lambda: settings_path))

    settings = UserSettings.load()

    assert settings.batch_recursive is False


def test_user_settings_loads_collection_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"collectionDirectory": "D:/Photos", "collectionScanMode": "raw", "collectionScanEnabled": True, "acceptedClassificationThreshold": 0.72, "gpxMatchToleranceSeconds": 900, "appLanguagePreference": "en"}), encoding="utf-8")
    monkeypatch.setattr(UserSettingsStore, "settings_path", staticmethod(lambda: settings_path))

    settings = UserSettings.load()

    assert settings.collection_directory == "D:/Photos"
    assert settings.collection_scan_mode == "raw"
    assert settings.collection_scan_enabled is True
    assert settings.accepted_classification_threshold == 0.72
    assert settings.gpx_match_tolerance_seconds == 900
    assert settings.app_language_preference == "en"


def test_user_settings_collection_scan_mode_falls_back_when_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"collectionScanMode": "png"}), encoding="utf-8")
    monkeypatch.setattr(UserSettingsStore, "settings_path", staticmethod(lambda: settings_path))

    settings = UserSettings.load()

    assert settings.collection_scan_mode == "raw_jpeg"


def test_user_settings_threshold_falls_back_when_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"acceptedClassificationThreshold": 3}), encoding="utf-8")
    monkeypatch.setattr(UserSettingsStore, "settings_path", staticmethod(lambda: settings_path))

    settings = UserSettings.load()

    assert settings.accepted_classification_threshold == 0.5


def test_user_settings_gpx_match_tolerance_falls_back_when_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"gpxMatchToleranceSeconds": 0}), encoding="utf-8")
    monkeypatch.setattr(UserSettingsStore, "settings_path", staticmethod(lambda: settings_path))

    settings = UserSettings.load()

    assert settings.gpx_match_tolerance_seconds == 300


def test_user_settings_save_includes_language_preference(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(UserSettingsStore, "settings_path", staticmethod(lambda: settings_path))
    settings = UserSettings()

    settings.save()

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["appLanguagePreference"] == "system"
    assert data["collectionScanMode"] == "raw_jpeg"
    assert data["collectionScanEnabled"] is False
    assert data["acceptedClassificationThreshold"] == 0.5
    assert data["gpxMatchToleranceSeconds"] == 300

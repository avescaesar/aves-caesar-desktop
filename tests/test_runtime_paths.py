from __future__ import annotations

import sys
from pathlib import Path

from bird_desktop.runtime.paths import AppPaths
from bird_desktop.runtime.settings import UserSettingsStore


def test_windows_user_data_dir_uses_dev_folder_in_python(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert AppPaths.user_data_dir() == tmp_path / "Aves Caesar Dev"
    assert AppPaths.cache_dir() == tmp_path / "Aves Caesar Dev" / "cache"
    assert AppPaths.logs_dir() == tmp_path / "Aves Caesar Dev" / "logs"
    assert UserSettingsStore.settings_path() == tmp_path / "Aves Caesar Dev" / "settings.json"


def test_windows_user_data_dir_uses_release_folder_when_frozen(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert AppPaths.user_data_dir() == tmp_path / "Aves Caesar"
    assert AppPaths.cache_dir() == tmp_path / "Aves Caesar" / "cache"
    assert AppPaths.logs_dir() == tmp_path / "Aves Caesar" / "logs"
    assert UserSettingsStore.settings_path() == tmp_path / "Aves Caesar" / "settings.json"


def test_models_dir_uses_resources_models_when_frozen(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(AppPaths, "app_root", staticmethod(lambda: tmp_path))

    assert AppPaths.models_dir() == tmp_path / "resources" / "models"
    assert AppPaths.model_build_info() == tmp_path / "resources" / "models" / "model-build-info.json"

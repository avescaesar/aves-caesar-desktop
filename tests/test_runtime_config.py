from __future__ import annotations

import json
from pathlib import Path

from bird_desktop.runtime.config import RuntimeConfig
from bird_desktop.runtime.paths import AppPaths


def test_runtime_config_loads_from_app_root_and_resolves_models(monkeypatch, tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    config_path = tmp_path / "runtime_config.json"
    config_path.write_text(json.dumps({"detector_model": "custom_detector.onnx"}), encoding="utf-8")
    monkeypatch.setattr(AppPaths, "app_root", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(AppPaths, "models_dir", staticmethod(lambda: models_dir))

    config = RuntimeConfig.load()

    assert config.detector_model == models_dir / "custom_detector.onnx"
    assert config.classifier_model == models_dir / "bird_classifier.onnx"
    assert config.labels_path == models_dir / "species_mapping_v2.csv"

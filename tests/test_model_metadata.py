from __future__ import annotations

import json
from pathlib import Path

import pytest

from bird_desktop.runtime.config import RuntimeConfig
from bird_desktop.runtime.model_metadata import ModelMetadata
from bird_desktop.runtime.paths import AppPaths


def test_model_metadata_reads_classifier_performance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    classifier_model = tmp_path / "bird_classifier.onnx"
    classifier_model.write_text("model", encoding="utf-8")
    performance_path = tmp_path / "model_performance.json"
    performance_path.write_text(json.dumps({"classification_model": {"evaluation": {"with_gps": {"species_top1_percent": 94.1, "species_top5_percent": 98.82}, "without_gps": {"species_top1_percent": 85.69, "species_top5_percent": 96.77}}}}), encoding="utf-8")
    monkeypatch.setattr(AppPaths, "app_root", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(AppPaths, "models_dir", staticmethod(lambda: tmp_path))
    config = RuntimeConfig(detector_model=tmp_path / "bird_detector.onnx", classifier_model=classifier_model, labels_path=tmp_path / "species_mapping_v2.csv")

    details = ModelMetadata(config).version_details()

    assert details["appExecutableDate"] is None
    assert details["classifierModelPerformance"] == {
        "withGps": {"speciesTop1Percent": 94.1, "speciesTop5Percent": 98.82},
        "withoutGps": {"speciesTop1Percent": 85.69, "speciesTop5Percent": 96.77},
    }


def test_model_metadata_reads_model_build_info(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    build_info_path = tmp_path / "model-build-info.json"
    build_info_path.write_text(json.dumps({"repository": "avescaesar/bird-detect-classify", "repositoryUrl": "https://huggingface.co/avescaesar/bird-detect-classify", "revision": "v1.2.0", "downloadedAt": "2026-06-01T12:00:00+00:00", "files": [{"path": "bird_detector.onnx", "size": 12, "sha256": "abc"}]}), encoding="utf-8")
    monkeypatch.setattr(AppPaths, "app_root", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(AppPaths, "models_dir", staticmethod(lambda: tmp_path))
    config = RuntimeConfig(detector_model=tmp_path / "bird_detector.onnx", classifier_model=tmp_path / "bird_classifier.onnx", labels_path=tmp_path / "species_mapping_v2.csv")

    details = ModelMetadata(config).version_details()

    assert details["modelBuildInfo"] == {
        "repository": "avescaesar/bird-detect-classify",
        "repositoryUrl": "https://huggingface.co/avescaesar/bird-detect-classify",
        "revision": "v1.2.0",
        "downloadedAt": "2026-06-01T12:00:00+00:00",
        "files": [{"path": "bird_detector.onnx", "size": 12, "sha256": "abc"}],
    }

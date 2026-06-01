from __future__ import annotations

import os
from pathlib import Path

from bird_desktop.inference.providers import RuntimeCache
from bird_desktop.runtime.config import RuntimeConfig


def test_runtime_cache_key_ignores_model_mtime_when_content_is_unchanged(tmp_path: Path) -> None:
    detector = tmp_path / "bird_detector.onnx"
    classifier = tmp_path / "bird_classifier.onnx"
    labels = tmp_path / "species_mapping_v2.csv"
    detector.write_text("detector", encoding="utf-8")
    classifier.write_text("classifier", encoding="utf-8")
    labels.write_text("species_id,scientific_name,name_en\n0,Corvus brachyrhynchos,American Crow\n", encoding="utf-8")
    config = _runtime_config(detector, classifier, labels)

    original = RuntimeCache._key(config)
    os.utime(detector, (1000, 1000))
    os.utime(classifier, (1000, 1000))

    assert RuntimeCache._key(config) == original


def test_runtime_cache_key_changes_when_external_model_data_changes(tmp_path: Path) -> None:
    detector = tmp_path / "bird_detector.onnx"
    classifier = tmp_path / "bird_classifier.onnx"
    classifier_data = tmp_path / "bird_classifier.onnx.data"
    labels = tmp_path / "species_mapping_v2.csv"
    detector.write_text("detector", encoding="utf-8")
    classifier.write_text("classifier", encoding="utf-8")
    classifier_data.write_text("weights-v1", encoding="utf-8")
    labels.write_text("species_id,scientific_name,name_en\n0,Corvus brachyrhynchos,American Crow\n", encoding="utf-8")
    config = _runtime_config(detector, classifier, labels)

    original = RuntimeCache._key(config)
    classifier_data.write_text("weights-v2", encoding="utf-8")

    assert RuntimeCache._key(config) != original


def _runtime_config(detector: Path, classifier: Path, labels: Path) -> RuntimeConfig:
    return RuntimeConfig(
        detector_model=detector,
        classifier_model=classifier,
        labels_path=labels,
        detection_threshold=0.7,
        classification_top_k=5,
        low_confidence_threshold=0.5,
        min_classification_confidence=0.01,
        crop_size=224,
        provider_preference="auto",
    )

from __future__ import annotations

import os
import sqlite3
from dataclasses import replace
from pathlib import Path

from bird_desktop.inference.cache import PredictionCache
from bird_desktop.runtime.config import RuntimeConfig


def test_prediction_cache_uses_path_size_and_mtime_without_hash_fallback(tmp_path: Path) -> None:
    cache = PredictionCache(tmp_path / "cache.sqlite3")
    source = tmp_path / "source.jpg"
    copy = tmp_path / "copy.jpg"
    source.write_text("same", encoding="utf-8")
    copy.write_text("same", encoding="utf-8")

    cache.store(source, "model", "location", {"birds": []})

    assert cache.lookup(source, "model", "location") is not None
    assert cache.lookup(copy, "model", "location") is None


def test_prediction_cache_can_load_many_entries_for_model_without_location_match(tmp_path: Path) -> None:
    cache = PredictionCache(tmp_path / "cache.sqlite3")
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    missing = tmp_path / "missing.jpg"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    missing.write_text("missing", encoding="utf-8")
    cache.store(first, "model", "first-location", {"birds": [{"id": 1}]})
    cache.store(second, "other-model", "second-location", {"birds": [{"id": 2}]})

    entries = cache.lookup_many_for_model([first, second, missing], "model")

    assert list(entries) == [str(first.resolve()).casefold()]
    assert entries[str(first.resolve()).casefold()]["result"]["birds"] == [{"id": 1}]


def test_prediction_cache_can_load_entries_under_directory_prefix(tmp_path: Path) -> None:
    cache = PredictionCache(tmp_path / "cache.sqlite3")
    source = tmp_path / "source"
    sibling = tmp_path / "source-other"
    source.mkdir()
    sibling.mkdir()
    nested = source / "nested" / "first.jpg"
    nested.parent.mkdir()
    sibling_image = sibling / "second.jpg"
    nested.write_text("first", encoding="utf-8")
    sibling_image.write_text("second", encoding="utf-8")
    cache.store(nested, "model", "location", {"birds": [{"id": 1}]})
    cache.store(sibling_image, "model", "location", {"birds": [{"id": 2}]})

    entries = cache.lookup_under_directory_for_model(source, "model")

    assert list(entries) == [str(nested.resolve()).casefold()]


def test_prediction_cache_clear_returns_count_when_vacuum_fails(tmp_path: Path) -> None:
    cache = PredictionCache(tmp_path / "cache.sqlite3")
    image = tmp_path / "source.jpg"
    image.write_text("source", encoding="utf-8")
    cache.store(image, "model", "location", {"birds": []})

    def fail_vacuum() -> None:
        raise sqlite3.OperationalError("database is locked")

    cache._vacuum = fail_vacuum

    assert cache.clear() == 1
    assert cache.lookup(image, "model", "location") is None


def test_model_fingerprint_ignores_model_mtime_when_content_is_unchanged(tmp_path: Path) -> None:
    detector = tmp_path / "bird_detector.onnx"
    classifier = tmp_path / "bird_classifier.onnx"
    labels = tmp_path / "species_mapping_v2.csv"
    detector.write_text("detector", encoding="utf-8")
    classifier.write_text("classifier", encoding="utf-8")
    labels.write_text("species_id,scientific_name,name_en\n0,Corvus brachyrhynchos,American Crow\n", encoding="utf-8")
    config = _runtime_config(detector, classifier, labels)

    original = PredictionCache.model_fingerprint(config)
    os.utime(detector, (1000, 1000))
    os.utime(classifier, (1000, 1000))
    os.utime(labels, (1000, 1000))

    assert PredictionCache.model_fingerprint(config) == original


def test_model_fingerprint_changes_when_external_model_data_changes(tmp_path: Path) -> None:
    detector = tmp_path / "bird_detector.onnx"
    classifier = tmp_path / "bird_classifier.onnx"
    classifier_data = tmp_path / "bird_classifier.onnx.data"
    labels = tmp_path / "species_mapping_v2.csv"
    detector.write_text("detector", encoding="utf-8")
    classifier.write_text("classifier", encoding="utf-8")
    classifier_data.write_text("weights-v1", encoding="utf-8")
    labels.write_text("species_id,scientific_name,name_en\n0,Corvus brachyrhynchos,American Crow\n", encoding="utf-8")
    config = _runtime_config(detector, classifier, labels)

    original = PredictionCache.model_fingerprint(config)
    classifier_data.write_text("weights-v2", encoding="utf-8")

    assert PredictionCache.model_fingerprint(config) != original


def test_model_fingerprint_ignores_min_classification_confidence(tmp_path: Path) -> None:
    detector = tmp_path / "bird_detector.onnx"
    classifier = tmp_path / "bird_classifier.onnx"
    labels = tmp_path / "species_mapping_v2.csv"
    detector.write_text("detector", encoding="utf-8")
    classifier.write_text("classifier", encoding="utf-8")
    labels.write_text("species_id,scientific_name,name_en\n0,Corvus brachyrhynchos,American Crow\n", encoding="utf-8")
    config = _runtime_config(detector, classifier, labels)

    original = PredictionCache.model_fingerprint(config)

    assert PredictionCache.model_fingerprint(replace(config, min_classification_confidence=0.8)) == original


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

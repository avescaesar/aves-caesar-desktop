from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image

from bird_desktop.inference.cache import PredictionCache
from bird_desktop.inference.pipeline import PipelineResult
from bird_desktop.inference.preprocess import BirdBox
from bird_desktop.inference.services import PredictionService
from bird_desktop.media.image_io import ImageLoader, ImageMetadata
from bird_desktop.runtime.config import RuntimeConfig
from bird_desktop.runtime.paths import AppPaths


class FakePipeline:
    def predict(self, _image, _latitude, _longitude, _datetime_text) -> PipelineResult:
        return PipelineResult(
            provider=["CPUExecutionProvider"],
            birds=[
                {
                    "box": [1, 2, 3, 4],
                    "classification": [
                        {"species_id": "amecro", "confidence": 0.91},
                        {"species_id": "norcar", "confidence": 0.22},
                    ],
                },
                {"box": [5, 6, 7, 8], "classification": [{"species_id": "low", "confidence": 0.12}]},
            ],
        )


class FakeStreamingPipeline:
    def __init__(self) -> None:
        self.detector_batches: list[int] = []
        self.classifier_batches: list[int] = []


    def _detect_birds_many(self, images) -> list[list[BirdBox]]:
        self.detector_batches.append(len(images))
        return [[BirdBox([1, 1, 12, 12], 0.9)] for _image in images]


    def _run_classifier_batch(self, images: np.ndarray, _metadata) -> list[list[dict]]:
        self.classifier_batches.append(int(images.shape[0]))
        return [[{"species_id": "amecro", "confidence": 0.91}] for _row in images]


    def _active_providers(self) -> list[str]:
        return ["CPUExecutionProvider"]


def test_prediction_service_stores_unfiltered_cache_and_filters_on_read(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(AppPaths, "cache_dir", staticmethod(lambda: tmp_path / "cache"))
    monkeypatch.setattr(ImageLoader, "read_metadata", staticmethod(lambda _path: ImageMetadata(None, None, None)))
    image_path = tmp_path / "bird.jpg"
    Image.new("RGB", (32, 32), "white").save(image_path)
    config = _runtime_config(tmp_path, 0.5)
    service = PredictionService(config)
    service._get_pipeline = lambda: FakePipeline()

    result = service.predict({"imagePath": str(image_path), "includePreview": False}, 0.5)

    assert [bird["classification"] for bird in result["birds"]] == [[{"species_id": "amecro", "confidence": 0.91}]]

    cache = PredictionCache(tmp_path / "cache" / "prediction-cache.sqlite3")
    cached = cache.lookup(image_path, PredictionCache.model_fingerprint(config), PredictionCache.location_fingerprint(None, None, None))
    assert cached is not None
    assert len(cached["result"]["birds"]) == 2
    assert [classification["species_id"] for classification in cached["result"]["birds"][0]["classification"]] == ["amecro", "norcar"]

    lower_min_config = replace(config, min_classification_confidence=0.01)
    cached_service = PredictionService(lower_min_config)
    cached_service._get_pipeline = lambda: (_ for _ in ()).throw(AssertionError("cache miss"))
    cached_result = cached_service.predict({"imagePath": str(image_path), "includePreview": False}, 0.5)

    assert [bird["classification"][0]["species_id"] for bird in cached_result["birds"]] == ["amecro", "low"]
    assert [classification["species_id"] for classification in cached_result["birds"][0]["classification"]] == ["amecro", "norcar"]


def test_prediction_service_streams_partial_final_batches(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(AppPaths, "cache_dir", staticmethod(lambda: tmp_path / "cache"))
    monkeypatch.setattr(ImageLoader, "read_metadata", staticmethod(lambda _path: ImageMetadata(None, None, None)))
    image_paths = []
    for index in range(5):
        image_path = tmp_path / f"bird-{index}.jpg"
        Image.new("RGB", (32 + index, 32 + index), "white").save(image_path)
        image_paths.append(image_path)

    config = _runtime_config(tmp_path, 0.5)
    config = replace(config, detector_batch_size=2, classifier_batch_size=3, crop_size=16)
    pipeline = FakeStreamingPipeline()
    service = PredictionService(config)
    service._get_pipeline = lambda: pipeline

    requests = [{"imagePath": str(image_path), "includePreview": False} for image_path in image_paths]
    results = list(service.iter_predict_many(requests, 0.5))

    assert len(results) == 5
    assert pipeline.detector_batches == [2, 2, 1]
    assert sum(pipeline.classifier_batches) == 5
    assert max(pipeline.classifier_batches) <= 3
    assert any(batch_size < 3 for batch_size in pipeline.classifier_batches)
    assert all(result["birds"][0]["classification"][0]["species_id"] == "amecro" for result in results)


def _runtime_config(base: Path, min_classification_confidence: float) -> RuntimeConfig:
    detector = base / "bird_detector.onnx"
    classifier = base / "bird_classifier.onnx"
    labels = base / "species_mapping_v2.csv"
    detector.write_text("detector", encoding="utf-8")
    classifier.write_text("classifier", encoding="utf-8")
    labels.write_text(
        "species_id,scientific_name,name_en,name_fr\n"
        "amecro,Corvus brachyrhynchos,American Crow,Corneille d'Amerique\n"
        "norcar,Cardinalis cardinalis,Northern Cardinal,Cardinal rouge\n"
        "low,Lowus birdus,Low Bird,Oiseau bas\n",
        encoding="utf-8",
    )
    return RuntimeConfig(
        detector_model=detector,
        classifier_model=classifier,
        labels_path=labels,
        detection_threshold=0.7,
        classification_top_k=5,
        low_confidence_threshold=0.5,
        min_classification_confidence=min_classification_confidence,
        crop_size=224,
        provider_preference="auto",
    )

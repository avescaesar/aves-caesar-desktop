from __future__ import annotations
from pathlib import Path

import numpy as np

from bird_desktop.data.bird_names import BirdNamesLoader
from bird_desktop.inference.pipeline import BirdOnnxPipeline


class FakeOutput:
    def __init__(self, name: str):
        self.name = name


class FakeDetectorSession:
    def get_outputs(self) -> list[FakeOutput]:
        return [FakeOutput("boxes"), FakeOutput("scores"), FakeOutput("labels")]


def test_bird_names_loader_reads_numeric_species_mapping(tmp_path: Path) -> None:
    labels_path = tmp_path / "species_mapping_v2.csv"
    labels_path.write_text("species_id,scientific_name,name_en,name_fr\n0,Corvus brachyrhynchos,American Crow,Corneille d'Amerique\n", encoding="utf-8")

    names = BirdNamesLoader(labels_path).all()

    assert list(names) == ["0"]
    assert names["0"].name == "American Crow"
    assert names["0"].name_lat == "Corvus brachyrhynchos"


def test_bird_names_loader_reads_csv_language_on_demand(tmp_path: Path) -> None:
    labels_path = tmp_path / "species_mapping_v2.csv"
    labels_path.write_text("species_id,scientific_name,name_en,name_fr,name_es\n0,Corvus brachyrhynchos,American Crow,Corneille d'Amerique,Cuervo americano\n", encoding="utf-8")
    loader = BirdNamesLoader(labels_path)

    names = loader.all("es")

    assert loader.available_languages() == ["en", "fr", "es"]
    assert names["0"].name == "Cuervo americano"
    assert names["0"].name_lat == "Corvus brachyrhynchos"


def test_pipeline_classification_uses_exported_species_record() -> None:
    pipeline = BirdOnnxPipeline.__new__(BirdOnnxPipeline)
    pipeline.class_ids = ["0"]

    classification = pipeline._classification_for_index(0, 0.91)

    assert classification == {
        "species_id": "0",
        "confidence": 0.91,
    }


def test_detector_postprocess_uses_bird_label_fallback_when_classifier_labels_have_no_detector_labels() -> None:
    pipeline = BirdOnnxPipeline.__new__(BirdOnnxPipeline)
    pipeline.detector_session = FakeDetectorSession()
    pipeline.detector_labels = {"14": "bird"}
    pipeline.config = type("Config", (), {"detection_threshold": 0.7})()
    outputs = [
        np.array([[[1.0, 2.0, 11.0, 12.0]]], dtype=np.float32),
        np.array([[0.96]], dtype=np.float32),
        np.array([[14]], dtype=np.int64),
    ]

    boxes = pipeline._postprocess_detector(outputs, (2.0, 3.0))

    assert len(boxes) == 1
    assert boxes[0].box == [2.0, 6.0, 22.0, 36.0]
    assert round(boxes[0].score, 2) == 0.96

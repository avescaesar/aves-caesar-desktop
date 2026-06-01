from pathlib import Path

from PIL import Image

from bird_desktop.collection.services import CollectionStore
from bird_desktop.data.bird_names import BirdNames
from bird_desktop.inference.cache import PredictionCache
from bird_desktop.inference.corrections import ManualCorrectionStore


class FakeNames:
    def __init__(self):
        self.names = {
            "amecro": BirdNames(name="American Crow", name_lat="Corvus brachyrhynchos"),
            "norcar": BirdNames(name="Northern Cardinal", name_lat="Cardinalis cardinalis"),
        }


    def all(self):
        return dict(self.names)


    def get(self, species_id: str):
        return self.names.get(species_id)


def test_manual_correction_promotes_corrected_species(tmp_path: Path) -> None:
    image_path = tmp_path / "birds.jpg"
    Image.new("RGB", (120, 90), "white").save(image_path)
    corrections = ManualCorrectionStore(tmp_path / "manual-corrections.sqlite3", FakeNames())
    corrections.set(image_path, 0, "norcar")

    result = corrections.apply(
        image_path,
        {
            "birds": [
                {
                    "box": [10, 10, 40, 50],
                    "classification": [
                        {"species_id": "amecro", "confidence": 0.81},
                        {"species_id": "norcar", "confidence": 0.22},
                    ],
                }
            ]
        },
    )

    bird = result["birds"][0]
    assert bird["classification"][0]["species_id"] == "norcar"
    assert bird["classification"][0]["manual"] is True
    assert bird["manualCorrection"]["originalClassification"]["species_id"] == "amecro"


def test_collection_store_counts_manual_correction_below_threshold(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    image_path = source / "birds.jpg"
    Image.new("RGB", (120, 90), "white").save(image_path)
    cache = PredictionCache(tmp_path / "prediction-cache.sqlite3")
    cache.store(image_path, "model-v1", "location-v1", {"birds": [{"box": [10, 10, 40, 50], "classification": [{"species_id": "amecro", "confidence": 0.42}]}]})
    corrections = ManualCorrectionStore(tmp_path / "manual-corrections.sqlite3", FakeNames())
    corrections.set(image_path, 0, "norcar")
    store = CollectionStore(tmp_path / "collection-index.sqlite3", cache, corrections)

    status = store.load(source, 0.9, "model-v1", 0.01)

    assert status is not None
    assert [item["speciesId"] for item in status["species"]] == ["norcar"]
    assert status["species"][0]["occurrences"][0]["classification"]["manual"] is True

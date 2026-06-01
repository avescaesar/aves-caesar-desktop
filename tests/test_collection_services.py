from __future__ import annotations

import sqlite3
from pathlib import Path

from PIL import Image

from bird_desktop.collection.services import CollectionIndexer, CollectionScanner, CollectionStore
from bird_desktop.collection.worker import CollectionWorker
from bird_desktop.inference.cache import PredictionCache


def test_collection_scan_is_recursive(tmp_path: Path) -> None:
    source = tmp_path / "source"
    nested = source / "nested"
    nested.mkdir(parents=True)
    (source / "root.jpg").write_text("x", encoding="utf-8")
    (nested / "nested.jpg").write_text("x", encoding="utf-8")

    assert CollectionScanner.scan_images(source) == [nested / "nested.jpg", source / "root.jpg"]


def test_collection_scan_filters_by_scan_mode(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    raw = source / "bird.NEF"
    heic = source / "bird.HEIC"
    heif = source / "bird.heif"
    jpeg = source / "bird.jpg"
    png = source / "bird.png"
    raw.write_text("x", encoding="utf-8")
    heic.write_text("x", encoding="utf-8")
    heif.write_text("x", encoding="utf-8")
    jpeg.write_text("x", encoding="utf-8")
    png.write_text("x", encoding="utf-8")

    assert CollectionScanner.scan_images(source, "raw") == [raw]
    assert CollectionScanner.scan_images(source, "jpeg") == [heic, heif, jpeg]
    assert CollectionScanner.scan_images(source, "raw_jpeg") == [heic, heif, jpeg, raw]


def test_collection_indexer_groups_species_and_preserves_occurrences(tmp_path: Path) -> None:
    image_path = tmp_path / "birds.jpg"
    Image.new("RGB", (120, 90), "white").save(image_path)
    indexer = CollectionIndexer()

    indexer.add_prediction(
        image_path,
        {
            "birds": [
                {"box": [10, 10, 40, 50], "classification": [{"species_id": "amecro", "confidence": 0.91}]},
                {"box": [60, 20, 95, 70], "classification": [{"species_id": "amecro", "confidence": 0.86}]},
                {"box": [5, 5, 20, 25], "classification": [{"species_id": "norcar", "confidence": 0.74}]},
            ]
        },
        0.5,
    )

    species = {item["speciesId"]: item for item in indexer.species()}

    assert species["amecro"]["occurrenceCount"] == 2
    assert species["amecro"]["imageCount"] == 1
    assert species["norcar"]["occurrenceCount"] == 1


def test_collection_indexer_skips_low_confidence(tmp_path: Path) -> None:
    image_path = tmp_path / "birds.jpg"
    Image.new("RGB", (120, 90), "white").save(image_path)
    indexer = CollectionIndexer()

    indexer.add_prediction(image_path, {"birds": [{"box": [10, 10, 40, 50], "classification": [{"species_id": "amecro", "confidence": 0.49}]}]}, 0.5)

    assert indexer.species() == []


def test_collection_thumbnail_is_centered_data_url(tmp_path: Path) -> None:
    image_path = tmp_path / "birds.jpg"
    Image.new("RGB", (120, 90), "white").save(image_path)
    indexer = CollectionIndexer()

    indexer.add_prediction(image_path, {"birds": [{"box": [10, 10, 40, 50], "classification": [{"species_id": "amecro", "confidence": 0.91}]}]}, 0.5)

    species = indexer.species()

    assert species[0]["thumbnailDataUrl"].startswith("data:image/jpeg;base64,")
    assert species[0]["occurrences"][0]["thumbnailDataUrl"].startswith("data:image/jpeg;base64,")


def test_collection_indexer_reuses_cached_thumbnail_without_loading_image(tmp_path: Path) -> None:
    image_path = tmp_path / "birds.jpg"
    image_path.write_text("not an image", encoding="utf-8")
    indexer = CollectionIndexer(lambda _key: "data:image/jpeg;base64,cached")

    indexer.add_prediction(image_path, {"birds": [{"box": [10, 10, 40, 50], "classification": [{"species_id": "amecro", "confidence": 0.91}]}]}, 0.5)

    species = indexer.species()

    assert species[0]["thumbnailDataUrl"] == "data:image/jpeg;base64,cached"
    assert species[0]["occurrences"][0]["thumbnailDataUrl"] == "data:image/jpeg;base64,cached"


def test_collection_store_loads_cached_predictions_by_directory_prefix_and_threshold(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    image_path = source / "birds.jpg"
    Image.new("RGB", (120, 90), "white").save(image_path)
    outside_path = tmp_path / "source-other.jpg"
    Image.new("RGB", (120, 90), "white").save(outside_path)
    cache = PredictionCache(tmp_path / "prediction-cache.sqlite3")
    cache.store(
        image_path,
        "model-v1",
        "location-v1",
        {
            "birds": [
                {"box": [10, 10, 40, 50], "classification": [{"species_id": "amecro", "confidence": 0.91}]},
                {"box": [60, 20, 95, 70], "classification": [{"species_id": "norcar", "confidence": 0.61}]},
            ]
        },
    )
    cache.store(outside_path, "model-v1", "location-v1", {"birds": [{"box": [10, 10, 40, 50], "classification": [{"species_id": "outside", "confidence": 0.99}]}]})
    store = CollectionStore(tmp_path / "collection-index.sqlite3", cache)

    loaded = store.load(source, 0.7, "model-v1", 0.0)

    assert loaded is not None
    assert loaded["total"] == 1
    assert loaded["completed"] == 1
    assert [item["speciesId"] for item in loaded["species"]] == ["amecro"]


def test_collection_store_loads_lower_threshold_from_same_prediction_cache(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    image_path = source / "birds.jpg"
    Image.new("RGB", (120, 90), "white").save(image_path)
    cache = PredictionCache(tmp_path / "prediction-cache.sqlite3")
    cache.store(
        image_path,
        "model-v1",
        "location-v1",
        {
            "birds": [
                {"box": [10, 10, 40, 50], "classification": [{"species_id": "amecro", "confidence": 0.91}]},
                {"box": [60, 20, 95, 70], "classification": [{"species_id": "norcar", "confidence": 0.61}]},
            ]
        },
    )
    store = CollectionStore(tmp_path / "collection-index.sqlite3", cache)

    loaded = store.load(source, 0.5, "model-v1", 0.0)
    assert loaded is not None
    assert [item["speciesId"] for item in loaded["species"]] == ["amecro", "norcar"]


def test_collection_store_load_does_not_generate_missing_thumbnails(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    image_path = source / "birds.jpg"
    image_path.write_text("not an image", encoding="utf-8")
    cache = PredictionCache(tmp_path / "prediction-cache.sqlite3")
    cache.store(image_path, "model-v1", "location-v1", {"birds": [{"box": [10, 10, 40, 50], "classification": [{"species_id": "amecro", "confidence": 0.91}]}]})
    store = CollectionStore(tmp_path / "collection-index.sqlite3", cache)

    loaded = store.load(source, 0.5, "model-v1", 0.0)

    assert loaded is not None
    assert loaded["species"][0]["thumbnailDataUrl"] is None
    assert loaded["species"][0]["occurrences"][0]["thumbnailDataUrl"] is None


def test_collection_store_saves_thumbnails_without_collection_index_tables(tmp_path: Path) -> None:
    image_path = tmp_path / "birds.jpg"
    Image.new("RGB", (120, 90), "white").save(image_path)
    indexer = CollectionIndexer()
    indexer.add_prediction(image_path, {"birds": [{"box": [10, 10, 40, 50], "classification": [{"species_id": "amecro", "confidence": 0.91}]}]}, 0.5)
    store_path = tmp_path / "collection-index.sqlite3"
    store = CollectionStore(store_path)

    store.save_thumbnails({"species": indexer.species()})

    with sqlite3.connect(store_path) as connection:
        thumbnail_count = connection.execute("select count(*) from collection_thumbnails").fetchone()[0]
        collection_index_table = connection.execute("select name from sqlite_master where type = 'table' and name = 'collection_index'").fetchone()

    assert thumbnail_count == 1
    assert collection_index_table is None


def test_collection_worker_reuses_cached_predictions_before_processing_missing_images(tmp_path: Path) -> None:
    first_image = tmp_path / "first.jpg"
    second_image = tmp_path / "second.jpg"
    Image.new("RGB", (120, 90), "white").save(first_image)
    Image.new("RGB", (120, 90), "white").save(second_image)
    store = CollectionStore(tmp_path / "collection-index.sqlite3")
    indexer = CollectionIndexer()
    cached_predictions = {
        store.image_key(first_image): {
            "birds": [{"box": [10, 10, 40, 50], "classification": [{"species_id": "amecro", "confidence": 0.91}]}]
        }
    }
    processed_images: list[Path] = []

    completed = CollectionWorker()._reuse_cached_predictions([first_image, second_image], cached_predictions, 0.5, store, indexer, processed_images)

    assert completed == 1
    assert processed_images == [first_image]
    assert indexer.species()[0]["speciesId"] == "amecro"


def test_collection_worker_filters_cached_predictions_with_threshold(tmp_path: Path) -> None:
    image_path = tmp_path / "birds.jpg"
    Image.new("RGB", (120, 90), "white").save(image_path)
    store = CollectionStore(tmp_path / "collection-index.sqlite3")
    indexer = CollectionIndexer()
    cached_predictions = {
        store.image_key(image_path): {
            "birds": [
                {"box": [10, 10, 40, 50], "classification": [{"species_id": "amecro", "confidence": 0.91}]},
                {"box": [50, 10, 80, 50], "classification": [{"species_id": "norcar", "confidence": 0.61}]},
            ]
        }
    }
    processed_images: list[Path] = []

    completed = CollectionWorker()._reuse_cached_predictions([image_path], cached_predictions, 0.7, store, indexer, processed_images)
    species = indexer.species()

    assert completed == 1
    assert processed_images == [image_path]
    assert [item["speciesId"] for item in species] == ["amecro"]


def test_collection_store_keeps_scan_modes_separate(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    raw_path = source / "birds.NEF"
    jpeg_path = source / "birds.jpg"
    raw_path.write_text("raw", encoding="utf-8")
    Image.new("RGB", (120, 90), "white").save(jpeg_path)
    cache = PredictionCache(tmp_path / "prediction-cache.sqlite3")
    cache.store(jpeg_path, "model-v1", "location-v1", {"birds": [{"box": [10, 10, 40, 50], "classification": [{"species_id": "amecro", "confidence": 0.91}]}]})
    cache.store(raw_path, "model-v1", "location-v1", {"birds": [{"box": [10, 10, 40, 50], "classification": [{"species_id": "rawbird", "confidence": 0.91}]}]})
    store = CollectionStore(tmp_path / "collection-index.sqlite3", cache)

    assert store.load(source, 0.5, "model-v1", 0.0, "jpeg") is not None
    assert store.load(source, 0.5, "model-v1", 0.0, "jpeg")["species"][0]["speciesId"] == "amecro"
    assert store.load(source, 0.5, "model-v1", 0.0, "raw")["species"][0]["speciesId"] == "rawbird"

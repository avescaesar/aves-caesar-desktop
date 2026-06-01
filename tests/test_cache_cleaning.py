from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bird_desktop.api import BirdDesktopApi
from bird_desktop.collection.services import CollectionStore
from bird_desktop.data.bird_names import BirdNames
from bird_desktop.inference.cache import PredictionCache
from bird_desktop.inference.corrections import ManualCorrectionStore


class CacheBackedPredictionService:
    def __init__(self, cache: PredictionCache):
        self.cache = cache


    def clear_cache(self) -> int:
        return self.cache.clear()


class FakeJobs:
    def __init__(self, running: bool = False):
        self.running = running


    def has_running(self) -> bool:
        return self.running


class FakeNames:
    def __init__(self):
        self.names = {
            "amecro": BirdNames(name="American Crow", name_lat="Corvus brachyrhynchos"),
            "norcar": BirdNames(name="Northern Cardinal", name_lat="Cardinalis cardinalis"),
        }


    def all(self) -> dict[str, BirdNames]:
        return dict(self.names)


    def get(self, species_id: str) -> BirdNames | None:
        return self.names.get(species_id)


def test_clear_prediction_cache_removes_predictions_and_collection_thumbnails(tmp_path: Path) -> None:
    image = tmp_path / "bird.jpg"
    image.write_bytes(b"image-data")
    cache = PredictionCache(tmp_path / "prediction-cache.sqlite3")
    cache.store(image, "model-v1", "location-v1", {"birds": []})
    store = CollectionStore(tmp_path / "collection-index.sqlite3", cache)
    _insert_thumbnail(store, "thumbnail-key", "data:image/jpeg;base64,cached")
    api = _api_for_cache(cache, store)

    result = api.clear_prediction_cache()

    assert result == {"clearedEntries": 1, "clearedCollectionThumbnails": 1}
    assert cache.lookup(image, "model-v1", "location-v1") is None
    assert store.thumbnail_data_url("thumbnail-key") is None


def test_clear_prediction_cache_keeps_manual_corrections(tmp_path: Path) -> None:
    image = tmp_path / "bird.jpg"
    image.write_bytes(b"image-data")
    cache = PredictionCache(tmp_path / "prediction-cache.sqlite3")
    store = CollectionStore(tmp_path / "collection-index.sqlite3", cache)
    corrections = ManualCorrectionStore(tmp_path / "manual-corrections.sqlite3", FakeNames())
    corrections.set(image, 0, "norcar")
    api = _api_for_cache(cache, store)

    api.clear_prediction_cache()
    result = corrections.apply(image, {"birds": [{"classification": [{"species_id": "amecro", "confidence": 0.91}]}]})

    assert result["birds"][0]["classification"][0]["species_id"] == "norcar"
    assert result["birds"][0]["classification"][0]["manual"] is True


def test_clear_prediction_cache_rejects_running_jobs(tmp_path: Path) -> None:
    image = tmp_path / "bird.jpg"
    image.write_bytes(b"image-data")
    cache = PredictionCache(tmp_path / "prediction-cache.sqlite3")
    cache.store(image, "model-v1", "location-v1", {"birds": []})
    store = CollectionStore(tmp_path / "collection-index.sqlite3", cache)
    api = _api_for_cache(cache, store, prediction_running=True)

    with pytest.raises(RuntimeError):
        api.clear_prediction_cache()

    assert cache.lookup(image, "model-v1", "location-v1") is not None


def _api_for_cache(cache: PredictionCache, store: CollectionStore, prediction_running: bool = False, batch_running: bool = False, collection_running: bool = False, lightroom_running: bool = False) -> BirdDesktopApi:
    api = BirdDesktopApi.__new__(BirdDesktopApi)
    api._prediction_service = CacheBackedPredictionService(cache)
    api._collection_store = store
    api._prediction_jobs = FakeJobs(prediction_running)
    api._batch_jobs = FakeJobs(batch_running)
    api._collection_jobs = FakeJobs(collection_running)
    api._lightroom_jobs = FakeJobs(lightroom_running)
    return api


def _insert_thumbnail(store: CollectionStore, thumbnail_key: str, data_url: str) -> None:
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "insert into collection_thumbnails (thumbnail_key, data_url, generated_at) values (?, ?, ?)",
            (thumbnail_key, data_url, "2026-05-24T00:00:00+00:00"),
        )

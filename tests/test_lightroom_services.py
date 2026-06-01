from __future__ import annotations

import time
from pathlib import Path

import pytest

from bird_desktop.data.gpx import GpxMatch, GpxService
from bird_desktop.inference.cache import PredictionCache
from bird_desktop.lightroom.jobs import LightroomJobs
from bird_desktop.lightroom.plugin import LightroomPluginManager
from bird_desktop.lightroom.services import LightroomPredictionService
from bird_desktop.media.image_io import ImageLoader, ImageMetadata
from bird_desktop.runtime.paths import AppPaths


def test_lightroom_plugin_generation_creates_expected_files(tmp_path: Path) -> None:
    plugin_path = tmp_path / "Aves.lrplugin"

    LightroomPluginManager(38387).create_plugin(plugin_path)

    assert (plugin_path / "Info.lua").exists()
    assert (plugin_path / "OpenPanel.lua").exists()
    assert (plugin_path / "AvesPlugin.lua").exists()
    assert "Aves Caesar..." in (plugin_path / "Info.lua").read_text(encoding="utf-8")
    plugin_lua = (plugin_path / "AvesPlugin.lua").read_text(encoding="utf-8")
    assert "function Aves.openPanel()" in plugin_lua
    assert "Tag selected photos" in plugin_lua
    assert "Reprocess" in plugin_lua
    assert "PLUGIN_VERSION = '1.0.20'" in plugin_lua
    assert "Confidence threshold" not in plugin_lua
    assert "properties.threshold" not in plugin_lua
    assert "threshold = options.threshold" not in plugin_lua
    assert "pcall(function()" in plugin_lua
    assert "photo:addKeyword(keyword)" in plugin_lua
    assert "catalog:getKeywords()" in plugin_lua
    assert "/client-log" in plugin_lua
    assert "operation = 'apply_keyword_error'" in plugin_lua
    assert "WRITE_ACCESS_TIMEOUT_SECONDS" not in plugin_lua
    assert "timeout =" not in plugin_lua
    assert "pcall(function()\n            return catalog:createKeyword" not in plugin_lua
    assert "return catalog:createKeyword(name, {}, parent ~= nil, parent, false)" in plugin_lua
    assert "local function ensure_keyword_path(catalog, path)" in plugin_lua
    assert "operation = 'create_keyword_before'" not in plugin_lua
    assert "operation = 'create_keyword_after'" not in plugin_lua
    assert "operation = 'ensure_keyword_path_error'" in plugin_lua
    assert "find_child_keyword(parent, name)" in plugin_lua
    assert "Keyword is not under ' .. KEYWORD_ROOT .. ' after creation" in plugin_lua
    assert "pcall(function()\n        return keyword:getParent()" not in plugin_lua
    assert "pcall(function()\n        return catalog:getKeywords()" not in plugin_lua
    assert "collect_keyword_tree(keyword, result)" in plugin_lua
    assert "local function aves_managed_keywords(catalog)" in plugin_lua
    assert "No Aves Caesar keywords found." in plugin_lua
    assert "photo:getRawMetadata('keywords')" in plugin_lua
    assert "local function photos_without_aves_keywords(photos)" in plugin_lua
    assert "Skipped existing Aves Caesar keywords" in plugin_lua
    assert "APPLY_BATCH_SIZE" not in plugin_lua
    assert "operation = 'apply_result_start'" not in plugin_lua
    assert "apply_batch" not in plugin_lua
    assert "local removed = remove_aves_keywords(photo, managed_keywords)" in plugin_lua
    assert "clear_errors = clear_errors + removed" not in plugin_lua
    assert "This removes only keywords under the Aves root." not in plugin_lua
    assert "if #parts <= 1 then" in plugin_lua
    assert "return string.format('%02d:%02d:%02d'" not in plugin_lua
    assert "return two_digits(hours) .. ':' .. two_digits(minutes) .. ':' .. two_digits(remaining_seconds)" in plugin_lua
    assert "local function numeric_value(value, fallback)" in plugin_lua
    assert "local function update_progress(job_id, progress, completed, total, caption)" in plugin_lua
    assert "operation = 'progress_before'" not in plugin_lua
    assert "operation = 'progress_set_portion_error'" in plugin_lua
    assert "operation = 'plugin_unhandled_error'" in plugin_lua
    assert "operation = 'poll_status_after'" not in plugin_lua
    assert "operation = 'with_write_access_entered'" not in plugin_lua
    assert "operation = 'with_write_access_call_before'" not in plugin_lua
    assert "operation = 'with_write_access_exception'" in plugin_lua
    assert "LrTasks.pcall(function()" in plugin_lua
    assert "operation = 'apply_keyword_exception'" not in plugin_lua
    assert "operation = 'remove_aves_keywords_error'" not in plugin_lua
    assert "operation = 'remove_aves_keywords_before'" not in plugin_lua
    assert "update_progress(job_id, progress, completed, total_number, caption)" in plugin_lua
    assert "xpcall" not in plugin_lua
    assert "local ok, message = pcall(function()" not in plugin_lua


def test_lightroom_plugin_info_reports_installed_and_available_versions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    manager = LightroomPluginManager(38387)
    install_path = manager.install_path()
    assert install_path is not None

    manager.create_plugin(install_path)

    info = manager.info()

    assert info["installed"] is True
    assert "installPath" not in info
    assert info["installedVersion"] == "1.0.20"
    assert info["availableVersion"] == "1.0.20"


def test_lightroom_plugin_uninstall_removes_generated_plugin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    manager = LightroomPluginManager(38387)
    install_path = manager.install_path()
    assert install_path is not None
    install_path.mkdir(parents=True)
    (install_path / "Info.lua").write_text("return {}", encoding="utf-8")

    info = manager.uninstall()

    assert info["installed"] is False
    assert not install_path.exists()


def test_lightroom_service_forwards_reprocess_flag(tmp_path: Path) -> None:
    image = tmp_path / "bird.jpg"
    image.write_bytes(b"image-data")
    requests = []

    def predictor(request):
        requests.append(request)
        return prediction("gretit1", "Great Tit", "Mesange charbonniere", 0.92)

    service = LightroomPredictionService(predictor)

    service.process_file(str(image), "fr", 0.5, True)

    assert requests[0]["reprocess"] is True
    assert requests[0]["includePreview"] is False


def test_lightroom_service_reports_prediction_source(tmp_path: Path) -> None:
    image = tmp_path / "bird.jpg"
    image.write_bytes(b"image-data")
    service = LightroomPredictionService(lambda _request: prediction("gretit1", "Great Tit", "Mesange charbonniere", 0.92, "cache"))

    result = service.process_file(str(image), "fr", 0.5, False)

    assert result["source"] == "cache"


def test_lightroom_jobs_use_settings_threshold(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image = tmp_path / "bird.jpg"
    image.write_bytes(b"image-data")
    thresholds = []
    monkeypatch.setattr(AppPaths, "logs_dir", staticmethod(lambda: tmp_path))

    class FakeService:
        def process_file(self, path: str, language: str, threshold: float, reprocess: bool, gpx_paths: list[str], gpx_match_tolerance_seconds: int) -> dict:
            thresholds.append(threshold)
            return {"path": path, "state": "ok", "keywords": [], "species": []}

    jobs = LightroomJobs(FakeService(), lambda: 0.72)

    start = jobs.start({"files": [str(image)], "language": "fr", "threshold": 0.12})
    status = {"state": "running"}
    for _ in range(50):
        status = jobs.status(start["jobId"])
        if status["state"] == "done":
            break

        time.sleep(0.01)

    assert status["state"] == "done"
    assert thresholds == [0.72]


def test_prediction_cache_does_not_reuse_moved_file_without_same_path(tmp_path: Path) -> None:
    original = tmp_path / "bird.jpg"
    moved = tmp_path / "renamed.jpg"
    original.write_bytes(b"image-data")
    moved.write_bytes(b"image-data")
    cache = PredictionCache(tmp_path / "prediction-cache.sqlite3")
    model_fingerprint = "model-v1"
    location_fingerprint = "location-v1"
    result = prediction("gretit1", "Great Tit", "Mesange charbonniere", 0.92)

    cache.store(original, model_fingerprint, location_fingerprint, result)
    cached = cache.lookup(moved, model_fingerprint, location_fingerprint)

    assert cached is None


def test_prediction_cache_model_change_invalidates_entry(tmp_path: Path) -> None:
    image = tmp_path / "bird.jpg"
    image.write_bytes(b"image-data")
    cache = PredictionCache(tmp_path / "prediction-cache.sqlite3")
    location_fingerprint = "location-v1"
    result = prediction("gretit1", "Great Tit", "Mesange charbonniere", 0.92)

    cache.store(image, "model-v1", location_fingerprint, result)

    assert cache.lookup(image, "model-v2", location_fingerprint) is None


def test_prediction_cache_clear_removes_entries(tmp_path: Path) -> None:
    image = tmp_path / "bird.jpg"
    image.write_bytes(b"image-data")
    cache = PredictionCache(tmp_path / "prediction-cache.sqlite3")
    result = prediction("gretit1", "Great Tit", "Mesange charbonniere", 0.92)

    cache.store(image, "model-v1", "location-v1", result)

    assert cache.clear() == 1
    assert cache.lookup(image, "model-v1", "location-v1") is None


def test_lightroom_service_empty_prediction_returns_ok_with_no_keywords(tmp_path: Path) -> None:
    image = tmp_path / "bird.jpg"
    image.write_bytes(b"image-data")
    service = LightroomPredictionService(lambda _request: {"birds": []})

    result = service.process_file(str(image), "fr", 0.5, False)

    assert result["state"] == "ok"
    assert result["keywords"] == []


def test_lightroom_service_uses_species_id_keyword_name(tmp_path: Path) -> None:
    image = tmp_path / "bird.jpg"
    image.write_bytes(b"image-data")
    service = LightroomPredictionService(lambda _request: prediction("gretit1", "Great Tit", "Mesange charbonniere", 0.92))

    result = service.process_file(str(image), "en", 0.5, False)

    assert result["keywords"] == ["Aves Caesar|gretit1"]


def test_lightroom_service_uses_gpx_when_photo_has_no_coordinates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image = tmp_path / "bird.jpg"
    image.write_bytes(b"image-data")
    gpx = tmp_path / "track.gpx"
    gpx.write_text("<gpx></gpx>", encoding="utf-8")
    requests = []
    monkeypatch.setattr(ImageLoader, "read_metadata", lambda _path: ImageMetadata(None, None, "2026:05:23 12:00:00"))
    monkeypatch.setattr(GpxService, "match_many", lambda _paths, _datetime, _tolerance=None: GpxMatch(45.5, -73.6, "2026-05-23T12:00:00Z", 0))

    def predictor(request):
        requests.append(request)
        return prediction("gretit1", "Great Tit", "Mesange charbonniere", 0.92)

    service = LightroomPredictionService(predictor)

    service.process_file(str(image), "fr", 0.5, False, [str(gpx)])

    assert requests[0]["latitude"] == "45.5"
    assert requests[0]["longitude"] == "-73.6"


def test_lightroom_service_uses_multiple_gpx_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image = tmp_path / "bird.jpg"
    image.write_bytes(b"image-data")
    first_gpx = tmp_path / "first.gpx"
    second_gpx = tmp_path / "second.gpx"
    first_gpx.write_text("<gpx></gpx>", encoding="utf-8")
    second_gpx.write_text("<gpx></gpx>", encoding="utf-8")
    seen_paths = []
    monkeypatch.setattr(ImageLoader, "read_metadata", lambda _path: ImageMetadata(None, None, "2026:05:23 12:00:00"))

    def match_many(paths, _datetime, _tolerance=None):
        seen_paths.extend(str(path) for path in paths)
        return GpxMatch(45.5, -73.6, "2026-05-23T12:00:00Z", 0)

    monkeypatch.setattr(GpxService, "match_many", match_many)
    service = LightroomPredictionService(lambda _request: prediction("gretit1", "Great Tit", "Mesange charbonniere", 0.92))

    service.process_file(str(image), "fr", 0.5, False, [str(first_gpx), str(second_gpx)])

    assert seen_paths == [str(first_gpx), str(second_gpx)]


def test_lightroom_service_keeps_photo_coordinates_before_gpx(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image = tmp_path / "bird.jpg"
    image.write_bytes(b"image-data")
    gpx = tmp_path / "track.gpx"
    gpx.write_text("<gpx></gpx>", encoding="utf-8")
    requests = []
    monkeypatch.setattr(ImageLoader, "read_metadata", lambda _path: ImageMetadata(46.0, -72.0, "2026:05:23 12:00:00"))
    monkeypatch.setattr(GpxService, "match_many", lambda _paths, _datetime, _tolerance=None: GpxMatch(45.5, -73.6, "2026-05-23T12:00:00Z", 0))

    def predictor(request):
        requests.append(request)
        return prediction("gretit1", "Great Tit", "Mesange charbonniere", 0.92)

    service = LightroomPredictionService(predictor)

    service.process_file(str(image), "fr", 0.5, False, [str(gpx)])

    assert requests[0]["latitude"] == "46.0"
    assert requests[0]["longitude"] == "-72.0"


def prediction(species_id: str, _english_name: str, _french_name: str, confidence: float, source: str = "prediction") -> dict:
    return {"source": source, "birds": [{"classification": [{"species_id": species_id, "confidence": confidence}]}]}

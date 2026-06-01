from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from bird_desktop.organization.services import BatchFileOrganizer, renamed_file_name, sanitize_folder_name
from bird_desktop.media.exiftool import ExifTool
from bird_desktop.runtime.worker_process import WorkerProcessCommand


def test_destination_must_be_empty(tmp_path: Path) -> None:
    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "existing.txt").write_text("data", encoding="utf-8")

    with pytest.raises(ValueError, match="must be empty"):
        BatchFileOrganizer.validate_empty_destination(destination)


def test_non_empty_destination_can_be_allowed(tmp_path: Path) -> None:
    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "existing.txt").write_text("data", encoding="utf-8")

    assert BatchFileOrganizer.prepare_destination(destination, True) == destination


def test_destination_has_entries(tmp_path: Path) -> None:
    destination = tmp_path / "destination"
    destination.mkdir()

    assert BatchFileOrganizer.has_entries(destination) is False

    (destination / "existing.txt").write_text("data", encoding="utf-8")

    assert BatchFileOrganizer.has_entries(destination) is True


def test_scan_images_ignores_hidden_directories(tmp_path: Path) -> None:
    source = tmp_path / "source"
    hidden = source / ".hidden"
    nested = source / "nested"
    hidden.mkdir(parents=True)
    nested.mkdir()
    (hidden / "ignored.jpg").write_text("x", encoding="utf-8")
    (nested / "used.NEF").write_text("x", encoding="utf-8")
    (source / "notes.txt").write_text("x", encoding="utf-8")

    assert BatchFileOrganizer.scan_images(source) == [nested / "used.NEF"]


def test_scan_images_can_skip_nested_directories(tmp_path: Path) -> None:
    source = tmp_path / "source"
    nested = source / "nested"
    nested.mkdir(parents=True)
    (source / "root.jpg").write_text("x", encoding="utf-8")
    (nested / "nested.jpg").write_text("x", encoding="utf-8")

    assert BatchFileOrganizer.scan_images(source, recursive=False) == [source / "root.jpg"]


def test_scan_images_includes_heic_and_heif(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    heic = source / "bird.HEIC"
    heif = source / "bird.heif"
    text = source / "notes.txt"
    heic.write_text("x", encoding="utf-8")
    heif.write_text("x", encoding="utf-8")
    text.write_text("x", encoding="utf-8")

    assert BatchFileOrganizer.scan_images(source) == [heic, heif]


def test_species_targets_deduplicate_species_and_use_localized_name() -> None:
    birds = [
        {"classification": [{"species_id": "amecro", "confidence": 0.91, "name": "American Crow"}]},
        {"classification": [{"species_id": "amecro", "confidence": 0.88, "name": "American Crow"}]},
        {"classification": [{"species_id": "norcar", "confidence": 0.75, "name": "Northern/Cardinal"}]},
    ]

    targets = BatchFileOrganizer.species_targets(birds, 0.5)

    assert [target.folder_name for target in targets] == ["American Crow", "Northern_Cardinal"]


def test_species_targets_skip_low_confidence_classifications() -> None:
    birds = [
        {"classification": [{"species_id": "amecro", "confidence": 0.49, "name": "American Crow"}]},
        {"classification": [{"species_id": "norcar", "confidence": 0.5, "name": "Northern Cardinal"}]},
    ]

    targets = BatchFileOrganizer.species_targets(birds, 0.5)

    assert [target.folder_name for target in targets] == ["Northern Cardinal"]


def test_copy_to_folder_can_copy_same_file_to_multiple_species(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    source.write_text("x", encoding="utf-8")
    destination = tmp_path / "destination"

    BatchFileOrganizer.copy_to_folder(source, destination, "Species A", False)
    BatchFileOrganizer.copy_to_folder(source, destination, "Species B", False)

    assert (destination / "Species A" / "source.jpg").exists()
    assert (destination / "Species B" / "source.jpg").exists()


def test_copy_to_folder_overwrites_existing_file(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "destination"
    species = destination / "Species A"
    species.mkdir(parents=True)
    existing = species / "source.jpg"
    existing.write_text("old", encoding="utf-8")

    copied = BatchFileOrganizer.copy_to_folder(source, destination, "Species A", False)

    assert copied == existing
    assert existing.read_text(encoding="utf-8") == "new"


def test_renamed_file_name_adds_missing_date_and_time(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ExifTool, "read_tags", lambda _path: {"DateTimeOriginal": "2026:05:21 14:30:12"})

    assert renamed_file_name(tmp_path / "bird.jpg") == "bird_20260521_143012.jpg"
    assert renamed_file_name(tmp_path / "bird_20260521.jpg") == "bird_20260521_143012.jpg"
    assert renamed_file_name(tmp_path / "bird_143012.jpg") == "bird_143012_20260521.jpg"
    assert renamed_file_name(tmp_path / "bird_20260521_143012.jpg") == "bird_20260521_143012.jpg"


def test_renamed_file_name_keeps_original_when_datetime_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ExifTool, "read_tags", lambda _path: {})

    assert renamed_file_name(tmp_path / "bird.jpg") == "bird.jpg"


def test_exiftool_read_tags_hides_process_window(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = []
    monkeypatch.setattr(ExifTool, "find", lambda: "exiftool.exe")
    monkeypatch.setattr(WorkerProcessCommand, "hidden_window_options", lambda: {"creationflags": 123})

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout='[{"DateTimeOriginal":"2026:05:21 14:30:12"}]', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    tags = ExifTool.read_tags(tmp_path / "bird.jpg")

    assert tags["DateTimeOriginal"] == "2026:05:21 14:30:12"
    assert calls[0][1]["creationflags"] == 123


def test_exiftool_extract_preview_hides_process_window(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = []
    monkeypatch.setattr(ExifTool, "find", lambda: "exiftool.exe")
    monkeypatch.setattr(WorkerProcessCommand, "hidden_window_options", lambda: {"creationflags": 123})

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        Image.new("RGB", (16, 12), "white").save(kwargs["stdout"], format="JPEG")
        return subprocess.CompletedProcess(command, 0, stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    preview = ExifTool.extract_preview(tmp_path / "bird.NEF")

    try:
        assert preview.exists()
        assert calls[0][1]["creationflags"] == 123
    finally:
        preview.unlink(missing_ok=True)


def test_sanitize_folder_name_handles_reserved_and_invalid_names() -> None:
    assert sanitize_folder_name("Northern/Cardinal") == "Northern_Cardinal"
    assert sanitize_folder_name("CON") == "_CON"

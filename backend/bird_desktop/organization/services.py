from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..data.gpx import GpxService
from ..media.exiftool import ExifTool
from ..media.image_io import HEIF_EXTENSIONS, ImageLoader


SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff",
    *HEIF_EXTENSIONS,
    *ExifTool.RAW_EXTENSIONS,
}

FOLDER_NO_BIRDS = "_No birds detected"
FOLDER_UNCLASSIFIED = "_Unclassified"
FOLDER_ERRORS = "_Errors"
INVALID_FOLDER_CHARS = '<>:"/\\|?*'
DATE_IN_NAME = re.compile(r"(^|[^0-9])[0-9]{8}([^0-9]|$)")
TIME_IN_NAME = re.compile(r"(^|[^0-9])[0-9]{6}([^0-9]|$)")
RESERVED_FOLDER_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


@dataclass(frozen=True)
class BatchSpeciesTarget:
    species_id: str
    folder_name: str


class BatchFileOrganizer:
    @staticmethod
    def validate_empty_destination(path: str | Path) -> Path:
        return BatchFileOrganizer.prepare_destination(path, False)


    @staticmethod
    def prepare_destination(path: str | Path, allow_non_empty: bool) -> Path:
        destination = Path(path)
        if not destination.exists():
            destination.mkdir(parents=True)

        if not destination.is_dir():
            raise ValueError("Destination path is not a directory.")

        if not allow_non_empty and BatchFileOrganizer.has_entries(destination):
            raise ValueError("Destination directory must be empty before running batch sorting.")

        return destination


    @staticmethod
    def has_entries(path: str | Path) -> bool:
        directory = Path(path)
        if not directory.exists() or not directory.is_dir():
            return False

        return any(directory.iterdir())


    @staticmethod
    def scan_images(source_path: str | Path, recursive: bool = True) -> list[Path]:
        source = Path(source_path)
        if not source.exists() or not source.is_dir():
            raise ValueError("Source path is not a directory.")

        candidates = BatchFileOrganizer._scan_candidates(source, recursive)
        images = [path for path in candidates if BatchFileOrganizer._is_supported_source_file(path)]
        return sorted(images, key=lambda item: str(item).casefold())


    @staticmethod
    def species_targets(birds: Iterable[dict[str, Any]], confidence_threshold: float) -> list[BatchSpeciesTarget]:
        targets: dict[str, BatchSpeciesTarget] = {}
        for bird in birds:
            classification = BatchFileOrganizer._primary_classification(bird)
            if classification is None:
                continue

            if BatchFileOrganizer._classification_confidence(classification) < confidence_threshold:
                continue

            species_id = str(classification.get("species_id") or "").strip()
            if not species_id or species_id in targets:
                continue

            label = BatchFileOrganizer._classification_label(classification)
            targets[species_id] = BatchSpeciesTarget(species_id=species_id, folder_name=sanitize_folder_name(label or species_id))

        return list(targets.values())


    @staticmethod
    def copy_to_folder(source: Path, destination_root: Path, folder_name: str, rename_files: bool) -> Path:
        folder = destination_root / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        file_name = renamed_file_name(source) if rename_files else source.name
        destination = folder / file_name
        shutil.copy2(source, destination)
        return destination


    @staticmethod
    def _is_supported_source_file(path: Path) -> bool:
        if path.name.startswith("."):
            return False

        if not path.is_file() or path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            return False

        return True


    @staticmethod
    def _scan_candidates(source: Path, recursive: bool) -> Iterable[Path]:
        if source.name.startswith("."):
            return iter(())

        if not recursive:
            return (path for path in source.iterdir() if not path.name.startswith("."))

        def walk() -> Iterable[Path]:
            for root, directory_names, file_names in os.walk(source):
                directory_names[:] = [name for name in directory_names if not name.startswith(".")]
                root_path = Path(root)
                for file_name in file_names:
                    if not file_name.startswith("."):
                        yield root_path / file_name

        return walk()


    @staticmethod
    def _primary_classification(bird: dict[str, Any]) -> dict[str, Any] | None:
        classifications = bird.get("classification")
        if not isinstance(classifications, list) or not classifications:
            return None

        first = classifications[0]
        return first if isinstance(first, dict) else None


    @staticmethod
    def _classification_label(classification: dict[str, Any]) -> str:
        localized = classification.get("name")
        return str(localized or classification.get("species_id") or "").strip()


    @staticmethod
    def _classification_confidence(classification: dict[str, Any]) -> float:
        try:
            return float(classification.get("confidence", 0))
        except (TypeError, ValueError):
            return 0


class BatchGpxResolver:
    def __init__(self, gpx_paths: list[str] | None, match_tolerance_seconds: int | None = None):
        self._gpx_paths = gpx_paths or []
        self._match_tolerance_seconds = match_tolerance_seconds


    def coordinates_for(self, image_path: Path) -> tuple[float | None, float | None, str | None]:
        metadata = ImageLoader.read_metadata(image_path)
        if not self._gpx_paths:
            return metadata.latitude, metadata.longitude, metadata.datetime_text

        match = GpxService.match_many(self._gpx_paths, metadata.datetime_text, self._match_tolerance_seconds)
        if match is None:
            return metadata.latitude, metadata.longitude, metadata.datetime_text

        return match.latitude, match.longitude, metadata.datetime_text


def sanitize_folder_name(value: str) -> str:
    cleaned = "".join("_" if char in INVALID_FOLDER_CHARS or ord(char) < 32 else char for char in value)
    cleaned = " ".join(cleaned.split()).strip(" .")
    if not cleaned:
        return FOLDER_UNCLASSIFIED

    if cleaned.upper() in RESERVED_FOLDER_NAMES:
        return f"_{cleaned}"

    return cleaned


def renamed_file_name(path: Path) -> str:
    has_date = DATE_IN_NAME.search(path.stem) is not None
    has_time = TIME_IN_NAME.search(path.stem) is not None
    if has_date and has_time:
        return path.name

    tags = ExifTool.read_tags(path)
    datetime_text = _tag_text(tags.get("DateTimeOriginal")) or _tag_text(tags.get("CreateDate"))
    if not datetime_text:
        return path.name

    date_value, time_value = _format_datetime_parts(datetime_text)
    missing_parts = []
    if not has_date and date_value:
        missing_parts.append(date_value)

    if not has_time and time_value:
        missing_parts.append(time_value)

    if not missing_parts:
        return path.name

    return f"{path.stem}_{'_'.join(missing_parts)}{path.suffix}"


def _tag_text(value: Any) -> str:
    if value in (None, "-"):
        return ""

    return str(value).strip()


def _format_datetime_parts(value: str) -> tuple[str | None, str | None]:
    cleaned = value.split("+", 1)[0].split(".", 1)[0].strip()
    parts = cleaned.split(" ", 1)
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else ""
    date_value = date_part.replace(":", "").replace("-", "")
    if len(date_value) != 8 or not date_value.isdigit():
        date_value = ""

    time_value = time_part.replace(":", "")
    if len(time_value) != 6 or not time_value.isdigit():
        time_value = ""

    return date_value or None, time_value or None

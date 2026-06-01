from __future__ import annotations

import base64
import json
import sqlite3
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from ..inference.cache import PredictionCache
from ..inference.corrections import ManualCorrectionStore
from ..inference.result_filter import PredictionResultFilter
from ..media.exiftool import ExifTool
from ..media.image_io import HEIF_EXTENSIONS, ImageLoader
from ..organization.services import BatchFileOrganizer
from ..runtime.paths import AppPaths


COLLECTION_SCAN_MODE_RAW = "raw"
COLLECTION_SCAN_MODE_JPEG = "jpeg"
COLLECTION_SCAN_MODE_RAW_JPEG = "raw_jpeg"
COLLECTION_SCAN_MODES = {COLLECTION_SCAN_MODE_RAW, COLLECTION_SCAN_MODE_JPEG, COLLECTION_SCAN_MODE_RAW_JPEG}
RENDERED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", *HEIF_EXTENSIONS}


class CollectionIndexer:
    def __init__(self, thumbnail_lookup: Callable[[str], str | None] | None = None, generate_missing_thumbnails: bool = True):
        self._thumbnail_lookup = thumbnail_lookup
        self._generate_missing_thumbnails = generate_missing_thumbnails
        self._species: dict[str, dict[str, Any]] = {}
        self._species_images: dict[str, set[str]] = {}


    def add_prediction(self, image_path: Path, result: dict[str, Any], confidence_threshold: float) -> None:
        candidates = self._valid_occurrences(image_path, result, confidence_threshold)
        if not candidates:
            return

        thumbnails = self._thumbnails(image_path, [candidate["box"] for candidate in candidates])
        for candidate, thumbnail in zip(candidates, thumbnails):
            candidate["thumbnailKey"] = thumbnail.get("thumbnailKey") if thumbnail else None
            candidate["thumbnailDataUrl"] = thumbnail.get("thumbnailDataUrl") if thumbnail else None
            self._add_occurrence(candidate)


    def species(self) -> list[dict[str, Any]]:
        items = []
        for species in self._species.values():
            item = dict(species)
            item["occurrences"] = list(species["occurrences"])
            item["occurrenceCount"] = len(item["occurrences"])
            item["imageCount"] = len(self._species_images.get(item["speciesId"], set()))
            items.append(item)

        return sorted(items, key=lambda item: str(item.get("speciesId", "")).casefold())


    def _valid_occurrences(self, image_path: Path, result: dict[str, Any], confidence_threshold: float) -> list[dict[str, Any]]:
        birds = result.get("birds", [])
        if not isinstance(birds, list):
            return []

        occurrences = []
        for bird_index, bird in enumerate(birds):
            if not isinstance(bird, dict):
                continue

            classification = self._primary_classification(bird)
            if classification is None:
                continue

            confidence = self._confidence(classification)
            if classification.get("manual") is not True and confidence < confidence_threshold:
                continue

            species_id = str(classification.get("species_id") or "").strip()
            if not species_id:
                continue

            occurrences.append({"imagePath": str(image_path), "birdIndex": bird_index, "box": self._box(bird.get("box")), "confidence": confidence, "usedLatitude": result.get("usedLatitude"), "usedLongitude": result.get("usedLongitude"), "usedDatetime": result.get("usedDatetime"), "classification": dict(classification)})

        return occurrences


    def _add_occurrence(self, occurrence: dict[str, Any]) -> None:
        classification = occurrence["classification"]
        species_id = str(classification.get("species_id") or "")
        species = self._species.get(species_id)
        if species is None:
            species = {
                "speciesId": species_id,
                "thumbnailDataUrl": occurrence.get("thumbnailDataUrl"),
                "occurrences": [],
            }
            self._species[species_id] = species
            self._species_images[species_id] = set()

        species["occurrences"].append(occurrence)
        self._species_images[species_id].add(str(occurrence.get("imagePath") or ""))


    def _thumbnails(self, image_path: Path, boxes: list[list[float]]) -> list[dict[str, str] | None]:
        records = [self._cached_thumbnail_record(image_path, box) for box in boxes]
        missing_indexes = [index for index, record in enumerate(records) if record is None]
        if not missing_indexes or not self._generate_missing_thumbnails:
            return records

        try:
            loaded = ImageLoader.load(image_path)
        except Exception:
            return records

        try:
            for index in missing_indexes:
                records[index] = self._thumbnail_record(loaded.image, image_path, boxes[index])

            return records
        finally:
            ImageLoader.cleanup(loaded)


    def _cached_thumbnail_record(self, image_path: Path, box: list[float]) -> dict[str, str] | None:
        thumbnail_key = self._thumbnail_key(image_path, box)
        if self._thumbnail_lookup is None:
            return None

        data_url = self._thumbnail_lookup(thumbnail_key)
        if data_url is None:
            return None

        return {"thumbnailKey": thumbnail_key, "thumbnailDataUrl": data_url}


    def _thumbnail_record(self, image: Image.Image, image_path: Path, box: list[float]) -> dict[str, str]:
        return {"thumbnailKey": self._thumbnail_key(image_path, box), "thumbnailDataUrl": self._thumbnail_data_url(image, box)}


    def _thumbnail_data_url(self, image: Image.Image, box: list[float]) -> str:
        crop = self._crop_around_box(image, box)
        output = BytesIO()
        try:
            crop.thumbnail((180, 180))
            crop.save(output, format="JPEG", quality=84)
            encoded = base64.b64encode(output.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}"
        finally:
            crop.close()


    def _crop_around_box(self, image: Image.Image, box: list[float]) -> Image.Image:
        x0, y0, x1, y1 = box
        width = max(1.0, x1 - x0)
        height = max(1.0, y1 - y0)
        size = max(width, height) * 1.35
        center_x = (x0 + x1) / 2
        center_y = (y0 + y1) / 2
        left = max(0, int(round(center_x - size / 2)))
        top = max(0, int(round(center_y - size / 2)))
        right = min(image.width, int(round(center_x + size / 2)))
        bottom = min(image.height, int(round(center_y + size / 2)))

        if right <= left or bottom <= top:
            return image.copy()

        return image.crop((left, top, right, bottom))


    def _thumbnail_key(self, image_path: Path, box: list[float]) -> str:
        stat = image_path.stat()
        return json.dumps({"path": str(image_path.resolve()).casefold(), "size": stat.st_size, "mtimeNs": stat.st_mtime_ns, "box": box}, sort_keys=True, separators=(",", ":"))


    def _primary_classification(self, bird: dict[str, Any]) -> dict[str, Any] | None:
        classifications = bird.get("classification")
        if not isinstance(classifications, list) or not classifications:
            return None

        first = classifications[0]
        return first if isinstance(first, dict) else None


    def _confidence(self, classification: dict[str, Any]) -> float:
        try:
            return float(classification.get("confidence", 0))
        except (TypeError, ValueError):
            return 0


    def _box(self, value: Any) -> list[float]:
        if not isinstance(value, list) or len(value) != 4:
            return [0, 0, 1, 1]

        try:
            return [float(item) for item in value]
        except (TypeError, ValueError):
            return [0, 0, 1, 1]


class CollectionScanner:
    @staticmethod
    def scan_images(base_directory: str | Path, scan_mode: str = COLLECTION_SCAN_MODE_RAW_JPEG) -> list[Path]:
        extensions = CollectionScanner._extensions(scan_mode)
        return [path for path in BatchFileOrganizer.scan_images(base_directory, True) if path.suffix.lower() in extensions]


    @staticmethod
    def _extensions(scan_mode: str) -> set[str]:
        if scan_mode == COLLECTION_SCAN_MODE_RAW:
            return set(ExifTool.RAW_EXTENSIONS)

        if scan_mode == COLLECTION_SCAN_MODE_JPEG:
            return set(RENDERED_IMAGE_EXTENSIONS)

        return set(ExifTool.RAW_EXTENSIONS) | set(RENDERED_IMAGE_EXTENSIONS)


class CollectionStore:
    def __init__(self, path: Path | None = None, prediction_cache: PredictionCache | None = None, corrections: ManualCorrectionStore | None = None):
        self.path = path or AppPaths.cache_dir() / "collection-index.sqlite3"
        self._prediction_cache = prediction_cache or PredictionCache(self.path.parent / "prediction-cache.sqlite3")
        self._corrections = corrections or ManualCorrectionStore(self.path.parent / "manual-corrections.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()


    def load(self, base_directory: str | Path, threshold: float, model_fingerprint: str, min_classification_confidence: float, scan_mode: str = COLLECTION_SCAN_MODE_RAW_JPEG) -> dict[str, Any] | None:
        entries_by_image = self._prediction_cache.lookup_under_directory_for_model(base_directory, model_fingerprint)
        entries = [(Path(str(entry["path"])), entry) for entry in entries_by_image.values() if self._matches_scan_mode(Path(str(entry["path"])), scan_mode)]
        if not entries:
            return None

        result_filter = PredictionResultFilter(min_classification_confidence)
        indexer = CollectionIndexer(self.thumbnail_data_url, generate_missing_thumbnails=False)
        for image_path, entry in entries:
            result = entry.get("result")
            if isinstance(result, dict):
                filtered_result = result_filter.apply(result)
                indexer.add_prediction(image_path, self._corrections.apply(image_path, filtered_result), threshold)

        return {"state": "done", "total": len(entries), "completed": len(entries), "errors": 0, "currentFile": "", "message": "Loaded cached collection predictions.", "species": indexer.species()}


    def save_thumbnails(self, status: dict[str, Any]) -> None:
        species = status.get("species") if isinstance(status.get("species"), list) else []
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            for item in species:
                if not isinstance(item, dict):
                    continue

                for occurrence in item.get("occurrences", []):
                    if isinstance(occurrence, dict):
                        self._save_thumbnail(connection, occurrence, now)


    def thumbnail_data_url(self, thumbnail_key: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute("select data_url from collection_thumbnails where thumbnail_key = ?", (thumbnail_key,)).fetchone()

        return row["data_url"] if row is not None else None


    def clear_thumbnails(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute("delete from collection_thumbnails")
            deleted_count = cursor.rowcount

        try:
            self._vacuum()
        except (OSError, sqlite3.Error):
            pass

        return deleted_count


    def image_key(self, image_path: Path) -> str:
        return str(image_path.resolve()).casefold()


    def _save_thumbnail(self, connection: sqlite3.Connection, occurrence: dict[str, Any], now: str) -> None:
        thumbnail_key = occurrence.get("thumbnailKey")
        thumbnail_data_url = occurrence.get("thumbnailDataUrl")
        if isinstance(thumbnail_key, str) and isinstance(thumbnail_data_url, str):
            connection.execute(
                """
                insert into collection_thumbnails (thumbnail_key, data_url, generated_at)
                values (?, ?, ?)
                on conflict(thumbnail_key) do update set
                    data_url = excluded.data_url,
                    generated_at = excluded.generated_at
                """,
                (thumbnail_key, thumbnail_data_url, now),
            )


    def _matches_scan_mode(self, image_path: Path, scan_mode: str) -> bool:
        return image_path.suffix.lower() in CollectionScanner._extensions(scan_mode)


    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                create table if not exists collection_thumbnails (
                    thumbnail_key text primary key,
                    data_url text not null,
                    generated_at text not null
                )
                """
            )


    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection


    def _vacuum(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute("vacuum")
        except (OSError, sqlite3.Error):
            return

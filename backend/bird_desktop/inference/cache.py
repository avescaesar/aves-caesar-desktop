from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..runtime.config import RuntimeConfig
from ..runtime.file_fingerprint import FileContentFingerprint
from ..runtime.paths import AppPaths


@dataclass(frozen=True)
class PredictionFileIdentity:
    path: str
    size: int
    mtime_ns: int


class PredictionCache:
    def __init__(self, path: Path | None = None):
        self.path = path or AppPaths.cache_dir() / "prediction-cache.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()


    def lookup(self, image_path: Path, model_fingerprint: str, location_fingerprint: str) -> dict[str, Any] | None:
        identity = self.identity(image_path)
        path_key = self._path_key(image_path)
        entry = self._lookup_by_path(path_key)
        if self._is_valid_entry(entry, identity, model_fingerprint, location_fingerprint):
            return entry

        return None


    def lookup_for_model(self, image_path: Path, model_fingerprint: str) -> dict[str, Any] | None:
        identity = self.identity(image_path)
        path_key = self._path_key(image_path)
        entry = self._lookup_by_path(path_key)
        if self._is_valid_model_entry(entry, identity, model_fingerprint):
            return entry

        return None


    def lookup_many_for_model(self, image_paths: list[Path], model_fingerprint: str) -> dict[str, dict[str, Any]]:
        identities = {self._path_key(image_path): self.identity(image_path) for image_path in image_paths}
        entries: dict[str, dict[str, Any]] = {}
        with self._connect() as connection:
            for path_keys in self._chunks(list(identities.keys()), 800):
                placeholders = ",".join("?" for _ in path_keys)
                rows = connection.execute(f"select * from prediction_cache where model_fingerprint = ? and path_key in ({placeholders})", (model_fingerprint, *path_keys)).fetchall()
                for row in rows:
                    entry = self._row_to_entry(row)
                    if entry is None:
                        continue

                    path_key = str(entry["pathKey"])
                    identity = identities.get(path_key)
                    if identity is not None and self._is_valid_model_entry(entry, identity, model_fingerprint):
                        entries[path_key] = entry

        return entries


    def lookup_under_directory_for_model(self, base_directory: str | Path, model_fingerprint: str) -> dict[str, dict[str, Any]]:
        base_key = self._directory_key(base_directory)
        entries: dict[str, dict[str, Any]] = {}
        with self._connect() as connection:
            rows = connection.execute("select * from prediction_cache where model_fingerprint = ? and path_key like ? escape '\\'", (model_fingerprint, f"{self._like_escape(base_key)}%")).fetchall()

        for row in rows:
            entry = self._row_to_entry(row)
            if entry is None:
                continue

            path_key = str(entry["pathKey"])
            if not self._is_under_directory_key(path_key, base_key):
                continue

            image_path = Path(str(entry["path"]))
            try:
                identity = self.identity(image_path)
            except OSError:
                continue

            if self._is_valid_model_entry(entry, identity, model_fingerprint):
                entries[path_key] = entry

        return entries


    def store(self, image_path: Path, model_fingerprint: str, location_fingerprint: str, result: dict[str, Any]) -> dict[str, Any]:
        identity = self.identity(image_path)
        entry = {
            "path": identity.path,
            "pathKey": self._path_key(image_path),
            "size": identity.size,
            "mtimeNs": identity.mtime_ns,
            "modelFingerprint": model_fingerprint,
            "locationFingerprint": location_fingerprint,
            "result": result,
            "processedAt": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as connection:
            connection.execute(
                """
                insert into prediction_cache (
                    path_key, path, size, mtime_ns, model_fingerprint,
                    location_fingerprint, result_json, processed_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(path_key) do update set
                    path = excluded.path,
                    size = excluded.size,
                    mtime_ns = excluded.mtime_ns,
                    model_fingerprint = excluded.model_fingerprint,
                    location_fingerprint = excluded.location_fingerprint,
                    result_json = excluded.result_json,
                    processed_at = excluded.processed_at
                """,
                (
                    entry["pathKey"],
                    entry["path"],
                    entry["size"],
                    entry["mtimeNs"],
                    entry["modelFingerprint"],
                    entry["locationFingerprint"],
                    json.dumps(entry["result"], ensure_ascii=False),
                    entry["processedAt"],
                ),
            )

        return dict(entry)


    def clear(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute("delete from prediction_cache")
            deleted_count = cursor.rowcount

        try:
            self._vacuum()
        except (OSError, sqlite3.Error):
            pass

        return deleted_count


    def identity(self, image_path: Path) -> PredictionFileIdentity:
        stat = image_path.stat()
        return PredictionFileIdentity(path=str(image_path), size=stat.st_size, mtime_ns=stat.st_mtime_ns)


    @staticmethod
    def model_fingerprint(config: RuntimeConfig) -> str:
        files = {
            "detector": FileContentFingerprint.onnx_model(config.detector_model),
            "classifier": FileContentFingerprint.onnx_model(config.classifier_model),
            "labels": FileContentFingerprint.file(config.labels_path),
        }
        payload = {
            "files": files,
            "detectionThreshold": config.detection_threshold,
            "classificationTopK": config.classification_top_k,
            "cropSize": config.crop_size,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


    @staticmethod
    def location_fingerprint(latitude: float | None, longitude: float | None, datetime_text: str | None) -> str:
        return json.dumps({"latitude": latitude, "longitude": longitude, "datetime": datetime_text}, sort_keys=True, separators=(",", ":"))


    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                create table if not exists prediction_cache (
                    path_key text primary key,
                    path text not null,
                    size integer not null,
                    mtime_ns integer not null,
                    model_fingerprint text not null,
                    location_fingerprint text not null,
                    result_json text not null,
                    processed_at text not null
                )
                """
            )
            connection.execute("create index if not exists idx_prediction_cache_context on prediction_cache(model_fingerprint, location_fingerprint)")


    def _lookup_by_path(self, path_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("select * from prediction_cache where path_key = ?", (path_key,)).fetchone()

        return self._row_to_entry(row)


    def _row_to_entry(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None

        return {
            "path": row["path"],
            "pathKey": row["path_key"],
            "size": row["size"],
            "mtimeNs": row["mtime_ns"],
            "modelFingerprint": row["model_fingerprint"],
            "locationFingerprint": row["location_fingerprint"],
            "result": json.loads(row["result_json"]),
            "processedAt": row["processed_at"],
        }


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


    def _is_valid_entry(self, entry: dict[str, Any] | None, identity: PredictionFileIdentity, model_fingerprint: str, location_fingerprint: str) -> bool:
        return self._is_valid_model_entry(entry, identity, model_fingerprint) and self._has_valid_prediction_location(entry, location_fingerprint)


    def _is_valid_model_entry(self, entry: dict[str, Any] | None, identity: PredictionFileIdentity, model_fingerprint: str) -> bool:
        if not isinstance(entry, dict):
            return False

        return entry.get("size") == identity.size and entry.get("mtimeNs") == identity.mtime_ns and entry.get("modelFingerprint") == model_fingerprint


    def _has_valid_prediction_location(self, entry: dict[str, Any], location_fingerprint: str) -> bool:
        return entry.get("locationFingerprint") == location_fingerprint


    def _path_key(self, image_path: Path) -> str:
        return str(image_path.resolve()).casefold()


    def _directory_key(self, base_directory: str | Path) -> str:
        return str(Path(base_directory).resolve()).casefold().rstrip("\\/")


    def _is_under_directory_key(self, path_key: str, base_key: str) -> bool:
        return path_key == base_key or path_key.startswith(f"{base_key}\\") or path_key.startswith(f"{base_key}/")


    def _chunks(self, values: list[str], size: int) -> list[list[str]]:
        return [values[index:index + size] for index in range(0, len(values), size)]


    def _like_escape(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

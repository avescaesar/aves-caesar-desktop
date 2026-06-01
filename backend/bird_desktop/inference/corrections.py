from __future__ import annotations

import copy
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..data.bird_names import BirdNamesLoader
from ..runtime.paths import AppPaths


class ManualCorrectionStore:
    def __init__(self, path: Path | None = None, names: BirdNamesLoader | None = None):
        self.path = path or AppPaths.cache_dir() / "manual-corrections.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._names = names or BirdNamesLoader()
        self._ensure_schema()


    def bird_names(self, language: str = "en") -> list[dict[str, str]]:
        names_by_species = self._names.all(language)
        options = [{"species_id": species_id, "name": names.localized(), "name_language": names.language, "name_lat": names.name_lat} for species_id, names in names_by_species.items()]
        return sorted(options, key=lambda item: ((item.get("name") or item["species_id"]).casefold(), item["species_id"].casefold()))


    def set(self, image_path: str | Path, bird_index: int, species_id: str) -> dict[str, Any]:
        path = Path(image_path)
        species_id = species_id.strip()
        if not species_id:
            raise ValueError("Missing species id.")

        if self._name_for(species_id, "en") is None:
            raise ValueError("Unknown species id.")

        if bird_index < 0:
            raise ValueError("Invalid bird index.")

        identity = self._identity(path)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                insert into manual_corrections (
                    path_key, path, size, mtime_ns, bird_index, species_id, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(path_key, size, mtime_ns, bird_index) do update set
                    path = excluded.path,
                    species_id = excluded.species_id,
                    updated_at = excluded.updated_at
                """,
                (identity["pathKey"], identity["path"], identity["size"], identity["mtimeNs"], bird_index, species_id, now, now),
            )

        return {"imagePath": identity["path"], "birdIndex": bird_index, "speciesId": species_id}


    def clear(self, image_path: str | Path, bird_index: int) -> dict[str, Any]:
        path = Path(image_path)
        identity = self._identity(path)
        with self._connect() as connection:
            connection.execute("delete from manual_corrections where path_key = ? and size = ? and mtime_ns = ? and bird_index = ?", (identity["pathKey"], identity["size"], identity["mtimeNs"], bird_index))

        return {"imagePath": identity["path"], "birdIndex": bird_index}


    def apply(self, image_path: str | Path, result: dict[str, Any]) -> dict[str, Any]:
        corrected = copy.deepcopy(result)
        birds = corrected.get("birds")
        if not isinstance(birds, list):
            return corrected

        corrections = self._corrections_for_image(Path(image_path))
        if not corrections:
            return corrected

        for bird_index, bird in enumerate(birds):
            if not isinstance(bird, dict):
                continue

            species_id = corrections.get(bird_index)
            if species_id is None:
                continue

            self._apply_to_bird(bird, species_id)

        return corrected


    def _apply_to_bird(self, bird: dict[str, Any], species_id: str) -> None:
        classifications = bird.get("classification")
        if not isinstance(classifications, list) or not classifications:
            return

        original = classifications[0] if isinstance(classifications[0], dict) else {}
        replacement = self._replacement_classification(species_id, classifications)
        if replacement is None:
            return

        replacement["manual"] = True
        bird["manualCorrection"] = {"speciesId": species_id, "originalClassification": dict(original)}
        remaining = [item for item in classifications if not (isinstance(item, dict) and item.get("species_id") == species_id)]
        bird["classification"] = [replacement, *remaining]


    def _replacement_classification(self, species_id: str, classifications: list[Any]) -> dict[str, Any] | None:
        source = next((item for item in classifications if isinstance(item, dict) and item.get("species_id") == species_id), None)
        if source is None:
            source = next((item for item in classifications if isinstance(item, dict)), None)

        if source is None:
            return None

        replacement = dict(source)
        replacement["species_id"] = species_id
        return replacement


    def _name_for(self, species_id: str, language: str) -> Any:
        try:
            return self._names.get(species_id, language)
        except TypeError:
            return self._names.get(species_id)


    def _corrections_for_image(self, image_path: Path) -> dict[int, str]:
        try:
            identity = self._identity(image_path)
        except OSError:
            return {}

        with self._connect() as connection:
            rows = connection.execute("select bird_index, species_id from manual_corrections where path_key = ? and size = ? and mtime_ns = ?", (identity["pathKey"], identity["size"], identity["mtimeNs"])).fetchall()

        return {int(row["bird_index"]): str(row["species_id"]) for row in rows}


    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                create table if not exists manual_corrections (
                    path_key text not null,
                    path text not null,
                    size integer not null,
                    mtime_ns integer not null,
                    bird_index integer not null,
                    species_id text not null,
                    created_at text not null,
                    updated_at text not null,
                    primary key(path_key, size, mtime_ns, bird_index)
                )
                """
            )


    def _identity(self, image_path: Path) -> dict[str, Any]:
        stat = image_path.stat()
        return {"path": str(image_path), "pathKey": str(image_path.resolve()).casefold(), "size": stat.st_size, "mtimeNs": stat.st_mtime_ns}


    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

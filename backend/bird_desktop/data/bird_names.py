from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from ..runtime.config import RuntimeConfig


DEFAULT_LANGUAGE = "en"


@dataclass(frozen=True)
class BirdNames:
    name_lat: str
    name: str
    language: str = DEFAULT_LANGUAGE


    def localized(self) -> str:
        return self.name or self.name_lat


class BirdNamesLoader:
    def __init__(self, labels_path: Path | None = None):
        self._labels_path = labels_path
        self._names_by_language: dict[str, dict[str, BirdNames]] = {}
        self._languages: list[str] | None = None


    def all(self, language: str = DEFAULT_LANGUAGE) -> dict[str, BirdNames]:
        return dict(self._load(self.normalize_language(language)))


    def get(self, species_id: str, language: str = DEFAULT_LANGUAGE) -> BirdNames | None:
        return self._load(self.normalize_language(language)).get(species_id)


    def available_languages(self) -> list[str]:
        if self._languages is not None:
            return list(self._languages)

        self._languages = self._csv_languages(self._resolve_labels_path())
        return list(self._languages)


    def normalize_language(self, language: str | None) -> str:
        requested = str(language or DEFAULT_LANGUAGE).split("-", 1)[0].casefold()
        languages = self.available_languages()
        if requested in languages:
            return requested

        if DEFAULT_LANGUAGE in languages:
            return DEFAULT_LANGUAGE

        return languages[0] if languages else DEFAULT_LANGUAGE


    def _load(self, language: str) -> dict[str, BirdNames]:
        cached = self._names_by_language.get(language)
        if cached is not None:
            return cached

        names = self._load_csv(self._resolve_labels_path(), language)
        self._names_by_language[language] = names
        return names


    def _load_csv(self, path: Path, language: str) -> dict[str, BirdNames]:
        names: dict[str, BirdNames] = {}
        if not path.exists():
            return names

        localized_key = f"name_{language}"
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for class_index, record in enumerate(reader):
                self._add_csv_species_record(names, record, class_index, localized_key, language)

        return names


    def _resolve_labels_path(self) -> Path:
        if self._labels_path is not None:
            return self._labels_path

        return RuntimeConfig.load().labels_path


    def _csv_languages(self, path: Path) -> list[str]:
        if not path.exists():
            return [DEFAULT_LANGUAGE]

        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])

        languages = [column.removeprefix("name_") for column in header if column.startswith("name_")]
        if DEFAULT_LANGUAGE not in languages:
            languages.insert(0, DEFAULT_LANGUAGE)

        return languages


    def _add_csv_species_record(self, names: dict[str, BirdNames], record: dict[str, str], class_index: int, localized_key: str, language: str) -> None:
        species_id = str(record.get("species_id") or class_index).strip()
        if not species_id:
            return

        scientific_name = str(record.get("scientific_name") or species_id).strip()
        localized_name = str(record.get(localized_key) or record.get("name_en") or scientific_name).strip()
        names[species_id] = BirdNames(name_lat=scientific_name, name=localized_name, language=language)

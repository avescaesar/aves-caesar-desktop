from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from ..data.gpx import GpxService
from ..media.image_io import ImageLoader


Predictor = Callable[[dict[str, Any]], dict[str, Any]]
BatchPredictor = Callable[[list[dict[str, Any]]], Iterable[dict[str, Any]]]
LIGHTROOM_KEYWORD_ROOT = "Aves Caesar"


class LightroomPredictionService:
    def __init__(self, predictor: Predictor, batch_predictor: BatchPredictor | None = None):
        self._predictor = predictor
        self._batch_predictor = batch_predictor


    def process_file(self, path: str, language: str, threshold: float, reprocess: bool, gpx_paths: list[str] | None = None, gpx_match_tolerance_seconds: int | None = None) -> dict[str, Any]:
        return self.process_files([path], language, threshold, reprocess, gpx_paths, gpx_match_tolerance_seconds)[0]


    def process_files(self, paths: list[str], language: str, threshold: float, reprocess: bool, gpx_paths: list[str] | None = None, gpx_match_tolerance_seconds: int | None = None) -> list[dict[str, Any]]:
        return list(self.iter_process_files(paths, language, threshold, reprocess, gpx_paths, gpx_match_tolerance_seconds))


    def iter_process_files(self, paths: list[str], language: str, threshold: float, reprocess: bool, gpx_paths: list[str] | None = None, gpx_match_tolerance_seconds: int | None = None) -> Iterator[dict[str, Any]]:
        pending: list[tuple[int, str, dict[str, Any]]] = []
        for index, path in enumerate(paths):
            prepared = self._prepare_file(path, reprocess, gpx_paths, gpx_match_tolerance_seconds)
            if prepared.get("state") == "error":
                yield prepared
            else:
                pending.append((index, path, prepared))

        completed = 0
        for (_index, path, request), prediction in zip(pending, self._iter_predict_many([request for _index, _path, request in pending])):
            completed += 1
            if prediction.get("state") == "error":
                yield prediction
                continue

            species = self._species_from_prediction(prediction, language, threshold)
            keywords = [f"{LIGHTROOM_KEYWORD_ROOT}|{item['name']}" for item in species]
            yield self._ok(path, keywords, species, str(prediction.get("source") or "prediction"))

        for _index, path, _request in pending[completed:]:
            yield self._error(path, "Prediction failed.")


    def _prepare_file(self, path: str, reprocess: bool, gpx_paths: list[str] | None, gpx_match_tolerance_seconds: int | None) -> dict[str, Any]:
        image_path = Path(path)
        if not image_path.exists():
            return self._error(path, "File does not exist.")

        if not image_path.is_file():
            return self._error(path, "Path is not a file.")

        try:
            prediction_request = self._prediction_request(image_path, gpx_paths, gpx_match_tolerance_seconds)
            prediction_request["reprocess"] = reprocess
        except Exception as exc:
            return self._error(path, str(exc), traceback.format_exc())

        return prediction_request


    def _predict_many(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return list(self._iter_predict_many(requests))


    def _iter_predict_many(self, requests: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        if not requests:
            return

        completed = 0
        if self._batch_predictor is not None:
            try:
                for result in self._batch_predictor(requests):
                    completed += 1
                    yield result

                return
            except Exception:
                pass

        for request in requests[completed:]:
            try:
                yield self._predictor(request)
            except Exception as exc:
                path = str(request.get("imagePath") or "")
                yield self._error(path, str(exc), traceback.format_exc())



    def _species_from_prediction(self, result: dict[str, Any], language: str, threshold: float) -> list[dict[str, Any]]:
        species: dict[str, dict[str, Any]] = {}
        for bird in result.get("birds", []):
            if not isinstance(bird, dict):
                continue

            classifications = bird.get("classification")
            if not isinstance(classifications, list) or not classifications:
                continue

            best = classifications[0]
            if not isinstance(best, dict):
                continue

            confidence = self._confidence(best)
            if confidence < threshold:
                continue

            species_id = str(best.get("species_id") or "").strip()
            if not species_id or species_id in species:
                continue

            name = self._localized_name(best, language)
            if not name:
                continue

            species[species_id] = {"id": species_id, "name": name, "confidence": confidence}

        return list(species.values())


    def _prediction_request(self, image_path: Path, gpx_paths: list[str] | None, gpx_match_tolerance_seconds: int | None) -> dict[str, Any]:
        metadata = ImageLoader.read_metadata(image_path)
        latitude = metadata.latitude
        longitude = metadata.longitude
        datetime_text = metadata.datetime_text
        location_source = "metadata" if latitude is not None and longitude is not None else "none"
        gpx_files = [Path(path) for path in gpx_paths or [] if isinstance(path, str) and path.strip()]
        existing_gpx_files = [path for path in gpx_files if path.exists()]
        if location_source == "none" and existing_gpx_files:
            match = GpxService.match_many(existing_gpx_files, datetime_text, gpx_match_tolerance_seconds)
            if match is not None:
                latitude = match.latitude
                longitude = match.longitude
                location_source = "gpx"

        request = {
            "imagePath": str(image_path),
            "latitude": "" if latitude is None else str(latitude),
            "longitude": "" if longitude is None else str(longitude),
            "datetime": datetime_text,
            "includePreview": False,
        }
        return request


    def _localized_name(self, classification: dict[str, Any], language: str) -> str:
        localized = classification.get("name") or classification.get(f"name_{language}")
        return str(localized or classification.get("species_id") or "").strip()


    def _confidence(self, classification: dict[str, Any]) -> float:
        try:
            return float(classification.get("confidence", 0))
        except (TypeError, ValueError):
            return 0


    def _ok(self, path: str, keywords: Any, species: Any, source: str) -> dict[str, Any]:
        return {"path": path, "state": "ok", "keywords": self._dedupe_strings(keywords), "species": species if isinstance(species, list) else [], "source": source}


    def _error(self, path: str, message: str, traceback_text: str = "") -> dict[str, Any]:
        return {"path": path, "state": "error", "keywords": [], "species": [], "message": message, "traceback": traceback_text}


    def _dedupe_strings(self, values: Any) -> list[str]:
        deduped = []
        seen = set()
        if not isinstance(values, list):
            return deduped

        for value in values:
            text = str(value).strip()
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                deduped.append(text)

        return deduped

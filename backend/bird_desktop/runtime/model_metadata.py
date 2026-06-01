from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import RuntimeConfig
from .paths import AppPaths


class ModelMetadata:
    def __init__(self, config: RuntimeConfig):
        self.config = config


    def version_details(self) -> dict[str, Any]:
        return {
            "appExecutableDate": self._modified_at(self._executable_path()),
            "classifierModelPerformance": self._classifier_model_performance(),
            "modelBuildInfo": self._model_build_info(),
        }


    def _model_build_info(self) -> dict[str, Any] | None:
        path = AppPaths.model_build_info()
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(data, dict):
            return None

        files = data.get("files")
        return {
            "repository": self._string(data.get("repository")),
            "repositoryUrl": self._string(data.get("repositoryUrl")),
            "revision": self._string(data.get("revision")),
            "downloadedAt": self._string(data.get("downloadedAt")),
            "files": files if isinstance(files, list) else [],
        }


    def _classifier_model_performance(self) -> dict[str, Any] | None:
        performance_path = AppPaths.models_dir() / "model_performance.json"
        if not performance_path.exists():
            return None

        try:
            data = json.loads(performance_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(data, dict):
            return None

        classification_model = data.get("classification_model")
        if not isinstance(classification_model, dict):
            return None

        evaluation = classification_model.get("evaluation")
        if not isinstance(evaluation, dict):
            return None

        return {
            "withGps": self._performance_block(evaluation.get("with_gps")),
            "withoutGps": self._performance_block(evaluation.get("without_gps")),
        }


    def _performance_block(self, value: object) -> dict[str, float] | None:
        if not isinstance(value, dict):
            return None

        return {
            "speciesTop1Percent": self._float(value.get("species_top1_percent")),
            "speciesTop5Percent": self._float(value.get("species_top5_percent")),
        }


    def _executable_path(self) -> Path | None:
        if getattr(sys, "frozen", False):
            return Path(sys.executable)

        root = AppPaths.app_root()
        candidates = [
            root / "dist" / "AvesCaesar" / "AvesCaesar.exe",
            root / "dist" / "AvesCaesar.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None


    def _modified_at(self, path: Path | None) -> str | None:
        if path is None or not path.exists():
            return None

        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")

    def _float(self, value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


    def _string(self, value: object) -> str:
        return value if isinstance(value, str) else ""

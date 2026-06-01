from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .paths import AppPaths


@dataclass(frozen=True)
class RuntimeConfig:
    detector_model: Path
    classifier_model: Path
    labels_path: Path
    detection_threshold: float = 0.7
    classification_top_k: int = 5
    low_confidence_threshold: float = 0.5
    min_classification_confidence: float = 0.01
    crop_size: int = 224
    detector_batch_size: int = 4
    classifier_batch_size: int = 32
    provider_preference: str = "auto"

    @staticmethod
    def load(path: Path | None = None) -> "RuntimeConfig":
        models_base = AppPaths.models_dir()
        config_path = path or AppPaths.app_root() / "runtime_config.json"
        data = {}
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))

        resolver = RuntimeConfigResolver(models_base, data)
        return RuntimeConfig(detector_model=resolver.path("detector_model", "bird_detector.onnx"), classifier_model=resolver.path("classifier_model", "bird_classifier.onnx"), labels_path=resolver.path("labels_path", "species_mapping_v2.csv"), detection_threshold=float(data.get("detection_threshold", 0.7)), classification_top_k=int(data.get("classification_top_k", 5)), low_confidence_threshold=float(data.get("low_confidence_threshold", 0.5)), min_classification_confidence=float(data.get("min_classification_confidence", 0.01)), crop_size=int(data.get("crop_size", 224)), detector_batch_size=max(1, int(data.get("detector_batch_size", 4))), classifier_batch_size=max(1, int(data.get("classifier_batch_size", 32))), provider_preference=str(data.get("provider_preference", "auto")))


    def validate(self) -> None:
        missing = [str(path) for path in (self.detector_model, self.classifier_model, self.labels_path) if not path.exists()]
        if missing:
            raise FileNotFoundError("Missing runtime artifact(s): " + ", ".join(missing))


class RuntimeConfigResolver:
    def __init__(self, base: Path, data: dict):
        self.base = base
        self.data = data


    def path(self, name: str, default_name: str) -> Path:
        path = Path(self.data.get(name, str(self.base / default_name)))
        if not path.is_absolute():
            path = self.base / path

        return path

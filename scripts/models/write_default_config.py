from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"
CONFIG_PATH = ROOT / "runtime_config.json"

config = {
    "detector_model": "bird_detector.onnx",
    "classifier_model": "bird_classifier.onnx",
    "labels_path": "species_mapping_v2.csv",
    "detection_threshold": 0.7,
    "classification_top_k": 5,
    "low_confidence_threshold": 0.5,
    "min_classification_confidence": 0.1,
    "crop_size": 224,
    "detector_batch_size": 4,
    "classifier_batch_size": 32,
    "provider_preference": "auto"
}

MODELS.mkdir(exist_ok=True)
CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
print(CONFIG_PATH)

from __future__ import annotations

from typing import Any


class PredictionResultFilter:
    def __init__(self, min_classification_confidence: float):
        self.min_classification_confidence = min_classification_confidence


    def apply(self, result: dict[str, Any]) -> dict[str, Any]:
        filtered = dict(result)
        birds = result.get("birds")
        if not isinstance(birds, list):
            filtered["birds"] = []
            return filtered

        filtered_birds = []
        for bird in birds:
            filtered_bird = self._filtered_bird(bird)
            if filtered_bird is not None:
                filtered_birds.append(filtered_bird)

        filtered["birds"] = filtered_birds
        return filtered


    def _filtered_bird(self, bird: Any) -> dict[str, Any] | None:
        if not isinstance(bird, dict):
            return None

        classifications = bird.get("classification")
        if not isinstance(classifications, list):
            return None

        filtered_classifications = [dict(classification) for classification in classifications if self._keeps_classification(classification)]
        if not filtered_classifications:
            return None

        filtered_bird = dict(bird)
        filtered_bird["classification"] = filtered_classifications
        return filtered_bird


    def _keeps_classification(self, classification: Any) -> bool:
        if not isinstance(classification, dict):
            return False

        if classification.get("manual") is True:
            return True

        return self._confidence(classification) >= self.min_classification_confidence


    def _confidence(self, classification: dict[str, Any]) -> float:
        try:
            return float(classification.get("confidence", 0))
        except (TypeError, ValueError):
            return 0

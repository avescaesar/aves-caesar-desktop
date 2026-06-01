from bird_desktop.inference.result_filter import PredictionResultFilter


def test_prediction_result_filter_removes_low_confidence_classifications() -> None:
    result = {
        "provider": ["CPUExecutionProvider"],
        "birds": [
            {
                "box": [1, 2, 3, 4],
                "classification": [
                    {"species_id": "amecro", "confidence": 0.91},
                    {"species_id": "norcar", "confidence": 0.22},
                ],
            },
            {"box": [5, 6, 7, 8], "classification": [{"species_id": "low", "confidence": 0.12}]},
        ],
    }

    filtered = PredictionResultFilter(0.5).apply(result)

    assert filtered["birds"] == [{"box": [1, 2, 3, 4], "classification": [{"species_id": "amecro", "confidence": 0.91}]}]


def test_prediction_result_filter_keeps_manual_classifications() -> None:
    result = {"birds": [{"classification": [{"species_id": "manual", "confidence": 0.0, "manual": True}]}]}

    filtered = PredictionResultFilter(0.5).apply(result)

    assert filtered["birds"][0]["classification"][0]["species_id"] == "manual"

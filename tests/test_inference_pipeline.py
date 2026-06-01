from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bird_desktop.inference.pipeline import BirdOnnxPipeline


def test_pipeline_prepares_onnxruntime_before_session_import(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = []
    module = SimpleNamespace(InferenceSession=lambda path, providers: {"path": path, "providers": providers})
    pipeline = SimpleNamespace(provider_selection=SimpleNamespace(selected=["CPUExecutionProvider"]))
    model_path = tmp_path / "model.onnx"

    monkeypatch.setitem(sys.modules, "onnxruntime", module)
    monkeypatch.setattr("bird_desktop.inference.pipeline.OnnxRuntimeLoader.prepare", lambda: calls.append("prepared"))

    session = BirdOnnxPipeline._create_session(pipeline, model_path)

    assert calls == ["prepared"]
    assert session == {"path": str(model_path), "providers": ["CPUExecutionProvider"]}

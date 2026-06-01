from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from bird_desktop.media.image_io import ImageLoader


def test_image_loader_registers_heif_opener_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    module = SimpleNamespace(register_heif_opener=lambda: calls.append("registered"))
    monkeypatch.setitem(sys.modules, "pillow_heif", module)
    monkeypatch.setattr(ImageLoader, "_heif_opener_registered", False)

    ImageLoader._register_heif_opener()
    ImageLoader._register_heif_opener()

    assert calls == ["registered"]

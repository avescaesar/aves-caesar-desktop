from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.models.download_release_models import ModelReleaseDownloader, format_size


def test_model_release_downloader_writes_build_info(monkeypatch, tmp_path: Path) -> None:
    version_path = tmp_path / "model-version.json"
    output_dir = tmp_path / "resources" / "models"
    version_path.write_text(json.dumps({"repository": "avescaesar/bird-detect-classify", "revision": "7a957a1208b5b59cb57663cef390ea4f2386e094", "files": ["nested/model.onnx"]}), encoding="utf-8")
    downloader = ModelReleaseDownloader(version_path, output_dir)

    def fake_download(url: str, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(url.encode("utf-8"))

    monkeypatch.setattr(downloader, "_download_file", fake_download)

    build_info_path = downloader.run()

    target_path = output_dir / "nested" / "model.onnx"
    expected_url = "https://huggingface.co/avescaesar/bird-detect-classify/resolve/7a957a1208b5b59cb57663cef390ea4f2386e094/nested/model.onnx?download=true"
    build_info = json.loads(build_info_path.read_text(encoding="utf-8"))
    assert target_path.read_text(encoding="utf-8") == expected_url
    assert build_info["repository"] == "avescaesar/bird-detect-classify"
    assert build_info["revision"] == "7a957a1208b5b59cb57663cef390ea4f2386e094"
    assert build_info["files"] == [{
        "path": "nested/model.onnx",
        "size": len(expected_url),
        "sha256": hashlib.sha256(expected_url.encode("utf-8")).hexdigest(),
        "url": expected_url,
    }]


def test_model_release_downloader_formats_file_sizes() -> None:
    assert format_size(12) == "12 B"
    assert format_size(1536) == "1.50 KB"
    assert format_size(2 * 1024 * 1024) == "2.00 MB"

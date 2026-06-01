from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.packaging.write_release_manifest import ReleaseManifestWriter


def write_model_performance(path: Path, *, include_family: bool = True) -> None:
    with_gps = {
        "species_top1_percent": 95.94,
        "species_top5_percent": 99.17,
        "species_f1_percent": 91.86,
    }
    without_gps = {
        "species_top1_percent": 91.48,
        "species_top5_percent": 97.84,
        "species_f1_percent": 78.43,
    }
    if include_family:
        with_gps["family_top1_percent"] = 99.33
        without_gps["family_top1_percent"] = 99.04

    path.write_text(json.dumps({"classification_model": {"evaluation": {"with_gps": with_gps, "without_gps": without_gps}}}), encoding="utf-8")


def test_release_manifest_writer_generates_installer_manifest(tmp_path: Path) -> None:
    installer = tmp_path / "AvesCaesarSetup-1.2.3-x64.exe"
    installer.write_bytes(b"installer")
    performance_path = tmp_path / "model_performance.json"
    output_path = tmp_path / "version.json"
    write_model_performance(performance_path)

    result = ReleaseManifestWriter(
        installer_path=installer,
        version="1.2.3",
        tag_name="v1.2.3",
        output_path=output_path,
        model_performance_path=performance_path,
        published_at=1779926400000,
    ).run()

    manifest = json.loads(result.read_text(encoding="utf-8"))
    assert manifest["version"] == "1.2.3"
    assert manifest["platform"] == "windows-x64"
    assert manifest["url"] == "https://github.com/avescaesar/aves-caesar-desktop/releases/download/v1.2.3/AvesCaesarSetup-1.2.3-x64.exe"
    assert manifest["sha256"] == hashlib.sha256(b"installer").hexdigest()
    assert manifest["publishedAt"] == 1779926400000
    assert manifest["size"] == len(b"installer")
    assert manifest["modelPerformance"] == {
        "withGps": {"top1": 95.94, "top5": 99.17, "family": 99.33, "f1": 91.86},
        "withoutGps": {"top1": 91.48, "top5": 97.84, "family": 99.04, "f1": 78.43},
    }


def test_release_manifest_writer_rejects_missing_required_metric(tmp_path: Path) -> None:
    installer = tmp_path / "AvesCaesarSetup-1.2.3-x64.exe"
    installer.write_bytes(b"installer")
    performance_path = tmp_path / "model_performance.json"
    write_model_performance(performance_path, include_family=False)

    with pytest.raises(RuntimeError, match="family_top1_percent"):
        ReleaseManifestWriter(installer_path=installer, version="1.2.3", tag_name="v1.2.3", output_path=tmp_path / "version.json", model_performance_path=performance_path).run()

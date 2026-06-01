from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


class FileContentFingerprint:
    SAMPLE_SIZE = 4 * 1024 * 1024
    STRATEGY = "sha256-head-middle-tail-v1"


    @staticmethod
    def file(path: Path) -> dict[str, Any]:
        try:
            stat = path.stat()
        except OSError:
            return {"path": str(path), "missing": True}

        return {
            "size": stat.st_size,
            "sampleSize": FileContentFingerprint.SAMPLE_SIZE,
            "strategy": FileContentFingerprint.STRATEGY,
            "sampleSha256": FileContentFingerprint._sample_hash(path, stat.st_size),
        }


    @staticmethod
    def onnx_model(path: Path) -> dict[str, Any]:
        fingerprint = {"model": FileContentFingerprint.file(path)}
        external_data_path = path.with_name(f"{path.name}.data")
        if external_data_path.exists():
            fingerprint["externalData"] = FileContentFingerprint.file(external_data_path)

        return fingerprint


    @staticmethod
    def _sample_hash(path: Path, file_size: int) -> str:
        digest = hashlib.sha256()
        for offset, size in FileContentFingerprint._sample_ranges(file_size):
            with path.open("rb") as handle:
                handle.seek(offset)
                digest.update(handle.read(size))

        return digest.hexdigest()


    @staticmethod
    def _sample_ranges(file_size: int) -> list[tuple[int, int]]:
        if file_size <= FileContentFingerprint.SAMPLE_SIZE * 3:
            return [(0, file_size)]

        sample_size = FileContentFingerprint.SAMPLE_SIZE
        middle_offset = (file_size - sample_size) // 2
        end_offset = file_size - sample_size
        return [(0, sample_size), (middle_offset, sample_size), (end_offset, sample_size)]

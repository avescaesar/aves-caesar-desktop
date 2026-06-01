from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..runtime.paths import AppPaths
from ..runtime.worker_process import WorkerProcessCommand


class ExifTool:
    RAW_EXTENSIONS = {
        ".3fr", ".ari", ".arw", ".bay", ".cr2", ".cr3", ".crw", ".dcr", ".dng", ".erf",
        ".fff", ".iiq", ".k25", ".kdc", ".mef", ".mos", ".mrw", ".nef", ".nrw", ".orf",
        ".pef", ".raf", ".raw", ".rw2", ".rwl", ".sr2", ".srf", ".srw", ".x3f",
    }


    @classmethod
    def is_raw_file(cls, path: Path) -> bool:
        return path.suffix.lower() in cls.RAW_EXTENSIONS


    @classmethod
    def find(cls) -> str | None:
        candidates = []
        if AppPaths.resources_dir().exists():
            candidates.extend(AppPaths.resources_dir().glob("exiftool/exiftool*"))

        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)

        return shutil.which("exiftool")


    @classmethod
    def extract_preview(cls, raw_path: Path) -> Path:
        exiftool = cls.find()
        if not exiftool:
            raise RuntimeError("ExifTool is required to extract RAW embedded previews. Run python scripts/setup/install_exiftool.py.")

        candidates = []
        for tag in ("JpgFromRaw", "PreviewImage", "OtherImage", "ThumbnailImage"):
            output_handle, output_name = tempfile.mkstemp(prefix="aves-caesar-preview-", suffix=".jpg")
            os.close(output_handle)
            output = Path(output_name)
            command = [exiftool, "-b", f"-{tag}", str(raw_path)]
            with output.open("wb") as handle:
                result = subprocess.run(command, stdout=handle, stderr=subprocess.PIPE, check=False, **WorkerProcessCommand.hidden_window_options())
            if result.returncode == 0 and output.stat().st_size > 0:
                candidates.append(output)
            else:
                output.unlink(missing_ok=True)

        best = cls._largest_image(candidates)
        for candidate in candidates:
            if candidate != best:
                candidate.unlink(missing_ok=True)

        if best is not None:
            return best

        raise RuntimeError("No embedded RAW preview could be extracted.")


    @staticmethod
    def _largest_image(paths: list[Path]) -> Path | None:
        from PIL import Image

        best_path = None
        best_pixels = 0
        for path in paths:
            try:
                with Image.open(path) as image:
                    pixels = image.width * image.height
            except Exception:
                path.unlink(missing_ok=True)
                continue

            if pixels > best_pixels:
                best_path = path
                best_pixels = pixels

        return best_path


    @classmethod
    def read_tags(cls, path: Path) -> dict[str, Any]:
        exiftool = cls.find()
        if not exiftool:
            return {}

        command = [exiftool, "-json", "-n", "-GPSLatitude", "-GPSLatitudeRef", "-GPSLongitude", "-GPSLongitudeRef", "-DateTimeOriginal", "-CreateDate", "-DateTimeCreated", str(path)]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", check=False, **WorkerProcessCommand.hidden_window_options())
        if result.returncode != 0:
            return {}

        try:
            records = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {}

        if not isinstance(records, list) or not records:
            return {}

        record = records[0]
        return record if isinstance(record, dict) else {}

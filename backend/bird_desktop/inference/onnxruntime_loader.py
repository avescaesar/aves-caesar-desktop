from __future__ import annotations

import importlib.util
import os
import platform
import sys
from pathlib import Path


class OnnxRuntimeLoader:
    _dll_directory_handles = []
    _loaded = False


    @classmethod
    def prepare(cls) -> None:
        if cls._loaded or platform.system() != "Windows":
            return

        capi_dir = cls._capi_dir()
        if capi_dir is None or not capi_dir.exists():
            return

        system32_dir = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32"
        if hasattr(os, "add_dll_directory"):
            cls._dll_directory_handles.append(os.add_dll_directory(str(capi_dir)))
            if system32_dir.exists():
                cls._dll_directory_handles.append(os.add_dll_directory(str(system32_dir)))

        os.environ["PATH"] = str(capi_dir) + os.pathsep + os.environ.get("PATH", "")
        cls._loaded = True


    @staticmethod
    def _capi_dir() -> Path | None:
        bundle_root = Path(getattr(sys, "_MEIPASS", ""))
        bundled_capi_dir = bundle_root / "onnxruntime" / "capi"
        if bundled_capi_dir.exists():
            return bundled_capi_dir

        spec = importlib.util.find_spec("onnxruntime")
        if spec is None or spec.submodule_search_locations is None:
            return None

        return Path(next(iter(spec.submodule_search_locations))) / "capi"

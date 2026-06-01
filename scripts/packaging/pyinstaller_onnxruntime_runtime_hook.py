from __future__ import annotations

import os
import sys
from pathlib import Path


DLL_DIRECTORY_HANDLES = []


def add_onnxruntime_dll_directory() -> None:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    capi_dir = bundle_root / "onnxruntime" / "capi"
    if not capi_dir.exists():
        return

    system32_dir = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32"
    if hasattr(os, "add_dll_directory"):
        DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(capi_dir)))
        if system32_dir.exists():
            DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(system32_dir)))

    os.environ["PATH"] = str(capi_dir) + os.pathsep + os.environ.get("PATH", "")


add_onnxruntime_dll_directory()

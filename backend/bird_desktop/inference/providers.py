from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .onnxruntime_loader import OnnxRuntimeLoader
from ..runtime.file_fingerprint import FileContentFingerprint


@dataclass(frozen=True)
class ProviderSelection:
    requested: list[str]
    available: list[str]
    selected: list[str]


@dataclass(frozen=True)
class RuntimeResolution:
    selection: ProviderSelection


class ProviderSelector:
    @staticmethod
    def select(preference: str = "auto") -> ProviderSelection:
        OnnxRuntimeLoader.prepare()
        import onnxruntime as ort

        available = ort.get_available_providers()
        requested = ProviderSelector._requested(preference)
        selected = [provider for provider in requested if provider in available]
        if "CPUExecutionProvider" not in selected:
            selected.append("CPUExecutionProvider")

        return ProviderSelection(requested=requested, available=available, selected=selected)


    @staticmethod
    def cpu_selection(selection: ProviderSelection) -> ProviderSelection:
        return ProviderSelection(requested=selection.requested, available=selection.available, selected=["CPUExecutionProvider"])


    @staticmethod
    def from_dict(data: dict[str, Any]) -> ProviderSelection:
        return ProviderSelection(requested=list(data.get("requested", [])), available=list(data.get("available", [])), selected=list(data.get("selected", [])))


    @staticmethod
    def _requested(preference: str) -> list[str]:
        system = platform.system().lower()
        if preference == "cpu":
            return ["CPUExecutionProvider"]

        if preference == "directml":
            return ["DmlExecutionProvider", "CPUExecutionProvider"]

        if preference == "coreml":
            return ["CoreMLExecutionProvider", "CPUExecutionProvider"]

        if system == "windows":
            return ["DmlExecutionProvider", "CPUExecutionProvider"]

        if system == "darwin":
            return ["CoreMLExecutionProvider", "CPUExecutionProvider"]

        return ["CPUExecutionProvider"]


class RuntimeResolver:
    @staticmethod
    def resolve(config) -> RuntimeResolution:
        selection = ProviderSelector.select(config.provider_preference)
        preferred = RuntimeResolver._preferred_provider(selection)
        if preferred == "CPUExecutionProvider":
            return RuntimeResolution(selection=ProviderSelector.cpu_selection(selection))

        try:
            effective = RuntimeResolver._effective_selection(config, selection)
            return RuntimeResolution(selection=effective)
        except Exception:
            return RuntimeResolution(selection=ProviderSelector.cpu_selection(selection))


    @staticmethod
    def encode(runtime: RuntimeResolution) -> str:
        return json.dumps({"selection": asdict(runtime.selection)}, ensure_ascii=True)


    @staticmethod
    def decode(value: str) -> RuntimeResolution:
        data = json.loads(value)
        return RuntimeResolution(selection=ProviderSelector.from_dict(data["selection"]))


    @staticmethod
    def _effective_selection(config, selection: ProviderSelection) -> ProviderSelection:
        detector_session = RuntimeResolver._create_session(config.detector_model, selection.selected)
        classifier_session = RuntimeResolver._create_session(config.classifier_model, selection.selected)
        RuntimeResolver._smoke_detector(detector_session, max(1, int(getattr(config, "detector_batch_size", 1))))
        RuntimeResolver._smoke_classifier(classifier_session, config.crop_size, max(1, int(getattr(config, "classifier_batch_size", 1))))
        providers = RuntimeResolver._session_providers([detector_session, classifier_session])
        selected = [provider for provider in selection.selected if provider in providers]
        if "CPUExecutionProvider" not in selected:
            selected.append("CPUExecutionProvider")

        return ProviderSelection(requested=selection.requested, available=selection.available, selected=selected)


    @staticmethod
    def _session_providers(sessions: list) -> list[str]:
        providers = []
        for session in sessions:
            for provider in session.get_providers():
                if provider not in providers:
                    providers.append(provider)

        return providers


    @staticmethod
    def _create_session(path: Path, providers: list[str]):
        OnnxRuntimeLoader.prepare()
        import onnxruntime as ort

        return ort.InferenceSession(str(path), providers=providers)


    @staticmethod
    def _smoke_detector(session, batch_size: int) -> None:
        feeds = RuntimeResolver._feeds(session, 640, RuntimeResolver._smoke_batch_size(session, batch_size))
        session.run(None, feeds)


    @staticmethod
    def _smoke_classifier(session, crop_size: int, batch_size: int) -> None:
        feeds = RuntimeResolver._feeds(session, crop_size, RuntimeResolver._smoke_batch_size(session, batch_size))
        session.run(None, feeds)


    @staticmethod
    def _feeds(session, image_size: int, batch_size: int) -> dict[str, np.ndarray]:
        feeds = {}
        for item in session.get_inputs():
            shape = RuntimeResolver._shape(item.shape, item.name, image_size, batch_size)
            feeds[item.name] = np.zeros(shape, dtype=RuntimeResolver._dtype(item.type))

        return feeds


    @staticmethod
    def _shape(shape: list[Any], name: str, image_size: int, batch_size: int) -> tuple[int, ...]:
        if name in ("lat", "lon", "day"):
            return (batch_size,)

        resolved = []
        for index, value in enumerate(shape):
            if index == 0:
                resolved.append(batch_size)
            elif isinstance(value, int) and value > 0:
                resolved.append(value)
            elif len(shape) == 4 and index == 1:
                resolved.append(3)
            elif len(shape) == 4 and index in (2, 3):
                resolved.append(image_size)
            else:
                resolved.append(1)

        return tuple(resolved)


    @staticmethod
    def _smoke_batch_size(session, configured: int) -> int:
        inputs = session.get_inputs()
        if not inputs:
            return configured

        batch_axis = inputs[0].shape[0] if inputs[0].shape else 1
        if isinstance(batch_axis, int) and batch_axis > 0:
            return min(configured, batch_axis)

        return configured


    @staticmethod
    def _dtype(value: str):
        if value == "tensor(double)":
            return np.float64

        if value == "tensor(int64)":
            return np.int64

        if value == "tensor(int32)":
            return np.int32

        return np.float32


    @staticmethod
    def _preferred_provider(selection: ProviderSelection) -> str:
        return selection.selected[0] if selection.selected else "CPUExecutionProvider"


class RuntimeProbe:
    def __init__(self, config):
        self.config = config
        self._process: subprocess.Popen[str] | None = None
        self._runtime: RuntimeResolution | None = RuntimeCache.load(config)


    def start(self) -> None:
        if self._process is not None or self._runtime is not None:
            return

        from ..runtime.paths import AppPaths
        from ..runtime.worker_process import WorkerProcessCommand

        log_path = AppPaths.logs_dir() / "runtime-probe.log"
        command = WorkerProcessCommand("inference.runtime_probe_worker").with_log_path(log_path)
        self._process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", **WorkerProcessCommand.hidden_window_options())


    def refresh(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()

        RuntimeCache.clear()
        self._process = None
        self._runtime = None
        self.start()


    def runtime_if_ready(self) -> RuntimeResolution | None:
        if self._runtime is not None:
            return self._runtime

        if self._process is None or self._process.poll() is None:
            return None

        self._runtime = self._read_runtime()
        return self._runtime


    def runtime(self) -> RuntimeResolution:
        if self._runtime is not None:
            return self._runtime

        if self._process is None:
            self.start()

        if self._process is None:
            self._runtime = RuntimeResolver.resolve(self.config)
        else:
            self._process.wait()
            self._runtime = self._read_runtime()

        return self._runtime


    def _read_runtime(self) -> RuntimeResolution:
        if self._process is None or self._process.stdout is None:
            return RuntimeResolution(selection=ProviderSelection(requested=[], available=[], selected=["CPUExecutionProvider"]))

        output = self._process.stdout.read()
        for line in reversed(output.splitlines()):
            if line.startswith("{"):
                runtime = RuntimeResolver.decode(line)
                RuntimeCache.save(self.config, runtime)
                return runtime

        return RuntimeResolution(selection=ProviderSelection(requested=[], available=[], selected=["CPUExecutionProvider"]))


class RuntimeCache:
    VERSION = 4

    @staticmethod
    def load(config) -> RuntimeResolution | None:
        path = RuntimeCache._path()
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if data.get("key") != RuntimeCache._key(config):
            return None

        runtime_data = data.get("runtime")
        if not isinstance(runtime_data, str):
            return None

        try:
            return RuntimeResolver.decode(runtime_data)
        except (KeyError, TypeError, json.JSONDecodeError):
            return None


    @staticmethod
    def save(config, runtime: RuntimeResolution) -> None:
        path = RuntimeCache._path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"key": RuntimeCache._key(config), "runtime": RuntimeResolver.encode(runtime)}
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            return


    @staticmethod
    def clear() -> None:
        try:
            RuntimeCache._path().unlink(missing_ok=True)
        except OSError:
            return


    @staticmethod
    def _path() -> Path:
        from ..runtime.settings import UserSettingsStore

        return UserSettingsStore.settings_path().parent / "runtime-cache.json"


    @staticmethod
    def _key(config) -> dict[str, Any]:
        return {
            "version": RuntimeCache.VERSION,
            "provider_preference": config.provider_preference,
            "detector_model": RuntimeCache._file_key(config.detector_model),
            "classifier_model": RuntimeCache._file_key(config.classifier_model),
        }


    @staticmethod
    def _file_key(path: Path) -> dict[str, Any]:
        return FileContentFingerprint.onnx_model(path)

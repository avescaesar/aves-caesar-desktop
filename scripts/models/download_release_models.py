from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_VERSION_PATH = ROOT / "model-version.json"
DEFAULT_OUTPUT_DIR = ROOT / "resources" / "models"
MODEL_BUILD_INFO_NAME = "model-build-info.json"


@dataclass(frozen=True)
class ModelReleaseFile:
    path: str
    url: str


@dataclass(frozen=True)
class ModelReleaseVersion:
    repository: str
    revision: str
    files: list[ModelReleaseFile]


class ModelReleaseDownloader:
    def __init__(self, version_path: Path = DEFAULT_MODEL_VERSION_PATH, output_dir: Path = DEFAULT_OUTPUT_DIR):
        self.version_path = version_path
        self.output_dir = output_dir


    def run(self) -> Path:
        version = self._load_version()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        downloaded_files = []
        for file in version.files:
            target_path = self.output_dir / file.path
            self._download_file(file.url, target_path)
            downloaded_files.append({
                "path": file.path,
                "size": target_path.stat().st_size,
                "sha256": self._sha256(target_path),
                "url": file.url,
            })

        build_info_path = self.output_dir / MODEL_BUILD_INFO_NAME
        build_info_path.write_text(json.dumps({
            "repository": version.repository,
            "repositoryUrl": f"https://huggingface.co/{version.repository}",
            "revision": version.revision,
            "downloadedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": str(self.version_path.relative_to(ROOT)) if self.version_path.is_relative_to(ROOT) else str(self.version_path),
            "files": downloaded_files,
        }, indent=2) + "\n", encoding="utf-8")
        return build_info_path


    def _load_version(self) -> ModelReleaseVersion:
        data = json.loads(self.version_path.read_text(encoding="utf-8"))
        repository = self._required_string(data, "repository")
        revision = self._required_string(data, "revision")
        raw_files = data.get("files")
        if not isinstance(raw_files, list) or not raw_files:
            raise RuntimeError(f"{self.version_path} must contain a non-empty files list.")

        files = []
        for raw_file in raw_files:
            if not isinstance(raw_file, str) or not raw_file.strip():
                raise RuntimeError(f"{self.version_path} contains an invalid model file entry.")

            file_path = raw_file.strip().replace("\\", "/")
            if file_path.startswith("/") or ".." in Path(file_path).parts:
                raise RuntimeError(f"{self.version_path} contains an unsafe model file path: {raw_file}")

            files.append(ModelReleaseFile(path=file_path, url=self._download_url(repository, revision, file_path)))

        return ModelReleaseVersion(repository=repository, revision=revision, files=files)


    def _required_string(self, data: dict[str, Any], name: str) -> str:
        value = data.get(name)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"{self.version_path} must contain a non-empty {name} string.")

        return value.strip()


    def _download_url(self, repository: str, revision: str, file_path: str) -> str:
        return f"https://huggingface.co/{repository}/resolve/{quote(revision, safe='')}/{quote(file_path, safe='/')}?download=true"


    def _download_file(self, url: str, target_path: Path) -> None:
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
        headers = {"User-Agent": "aves-caesar-release-build"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        target_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = target_path.with_name(f"{target_path.name}.download")
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                request = Request(url, headers=headers)
                with urlopen(request, timeout=120) as response, temporary_path.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break

                        handle.write(chunk)

                temporary_path.replace(target_path)
                return
            except Exception as exc:
                last_error = exc
                if temporary_path.exists():
                    temporary_path.unlink()

                if attempt < 3:
                    time.sleep(attempt * 2)

        raise RuntimeError(f"Could not download {url}") from last_error


    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break

                digest.update(chunk)

        return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version-file", type=Path, default=DEFAULT_MODEL_VERSION_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_info_path = ModelReleaseDownloader(args.version_file, args.output_dir).run()
    build_info = json.loads(build_info_path.read_text(encoding="utf-8"))
    print(f"Model build info: {build_info_path}")
    print("Downloaded model files:")
    for file in build_info.get("files", []):
        if not isinstance(file, dict):
            continue

        print(f"- {file.get('path', '')}: {format_size(int(file.get('size', 0)))}")


def format_size(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    size = float(max(0, size_bytes))
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"

            return f"{size:.2f} {unit}"

        size /= 1024

    return f"{size_bytes} B"


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PERFORMANCE_PATH = ROOT / "resources" / "models" / "model_performance.json"
DEFAULT_OUTPUT_PATH = ROOT / "version.json"
DEFAULT_GITHUB_REPOSITORY = "avescaesar/aves-caesar-desktop"
PLATFORM = "windows-x64"


class ReleaseManifestWriter:
    def __init__(
        self,
        installer_path: Path,
        version: str,
        tag_name: str,
        output_path: Path = DEFAULT_OUTPUT_PATH,
        model_performance_path: Path = DEFAULT_MODEL_PERFORMANCE_PATH,
        github_repository: str = DEFAULT_GITHUB_REPOSITORY,
        published_at: int | None = None,
    ):
        self.installer_path = installer_path
        self.version = version
        self.tag_name = tag_name
        self.output_path = output_path
        self.model_performance_path = model_performance_path
        self.github_repository = github_repository
        self.published_at = published_at


    def run(self) -> Path:
        if not self.installer_path.is_file():
            raise RuntimeError(f"Installer not found: {self.installer_path}")

        manifest = {
            "version": self._required_version(self.version),
            "platform": PLATFORM,
            "url": self._installer_url(),
            "sha256": self._sha256(self.installer_path),
            "publishedAt": self.published_at if self.published_at is not None else int(time.time() * 1000),
            "size": self.installer_path.stat().st_size,
            "modelPerformance": self._model_performance(),
        }
        self.output_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return self.output_path


    def _installer_url(self) -> str:
        repository = self.github_repository.strip().strip("/")
        if not repository or "/" not in repository:
            raise RuntimeError("GitHub repository must be in owner/name format.")

        return f"https://github.com/{repository}/releases/download/{quote(self.tag_name)}/{quote(self.installer_path.name)}"


    def _model_performance(self) -> dict[str, dict[str, float]]:
        if not self.model_performance_path.is_file():
            raise RuntimeError(f"Model performance file not found: {self.model_performance_path}")

        data = json.loads(self.model_performance_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("model_performance.json must contain an object.")

        classification_model = data.get("classification_model")
        if not isinstance(classification_model, dict):
            raise RuntimeError("model_performance.json is missing classification_model.")

        evaluation = classification_model.get("evaluation")
        if not isinstance(evaluation, dict):
            raise RuntimeError("model_performance.json is missing classification_model.evaluation.")

        return {
            "withGps": self._performance_block(evaluation.get("with_gps"), "with_gps"),
            "withoutGps": self._performance_block(evaluation.get("without_gps"), "without_gps"),
        }


    def _performance_block(self, value: object, name: str) -> dict[str, float]:
        if not isinstance(value, dict):
            raise RuntimeError(f"model_performance.json is missing {name}.")

        return {
            "top1": self._required_float(value, "species_top1_percent", name),
            "top5": self._required_float(value, "species_top5_percent", name),
            "family": self._required_float(value, "family_top1_percent", name),
            "f1": self._required_float(value, "species_f1_percent", name),
        }


    def _required_float(self, data: dict[str, Any], key: str, block_name: str) -> float:
        value = data.get(key)
        if isinstance(value, bool):
            raise RuntimeError(f"model_performance.json {block_name}.{key} must be a number.")

        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"model_performance.json {block_name}.{key} must be a number.") from exc

        if not math.isfinite(number):
            raise RuntimeError(f"model_performance.json {block_name}.{key} must be finite.")

        return number


    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break

                digest.update(chunk)

        return digest.hexdigest()


    def _required_version(self, version: str) -> str:
        normalized = version.strip()
        parts = normalized.split(".")
        if len(parts) != 3 or any(not part.isdigit() for part in parts):
            raise RuntimeError(f"Release version must be X.Y.Z. Got: {version}")

        return normalized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--model-performance", type=Path, default=DEFAULT_MODEL_PERFORMANCE_PATH)
    parser.add_argument("--github-repository", default=DEFAULT_GITHUB_REPOSITORY)
    parser.add_argument("--published-at", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = ReleaseManifestWriter(
        installer_path=args.installer,
        version=args.version,
        tag_name=args.tag,
        output_path=args.output,
        model_performance_path=args.model_performance,
        github_repository=args.github_repository,
        published_at=args.published_at,
    ).run()
    print(f"Release manifest written to {output_path}")


if __name__ == "__main__":
    main()

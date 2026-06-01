from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
I18N_DIR = ROOT / "frontend" / "src" / "i18n"
PLACEHOLDER_PATTERN = re.compile(r"\{[^}]+\}")
EXPECTED_UI_LANGUAGES = {"de", "en", "es", "fr"}


def test_frontend_i18n_files_match_ui_languages() -> None:
    available_languages = {path.stem for path in I18N_DIR.glob("*.json")}

    assert available_languages == EXPECTED_UI_LANGUAGES


def test_frontend_i18n_files_have_same_keys() -> None:
    reference_keys = set(json.loads((I18N_DIR / "en.json").read_text(encoding="utf-8")))

    for path in I18N_DIR.glob("*.json"):
        keys = set(json.loads(path.read_text(encoding="utf-8")))
        assert keys == reference_keys, path.name


def test_frontend_i18n_files_preserve_placeholders() -> None:
    reference = json.loads((I18N_DIR / "en.json").read_text(encoding="utf-8"))

    for path in I18N_DIR.glob("*.json"):
        translations = json.loads(path.read_text(encoding="utf-8"))
        for key, text in translations.items():
            assert "ZXQ" not in text, f"{path.name}:{key}"
            assert PLACEHOLDER_PATTERN.findall(text) == PLACEHOLDER_PATTERN.findall(reference[key]), f"{path.name}:{key}"


def test_frontend_i18n_non_english_files_are_not_english_copies() -> None:
    reference = json.loads((I18N_DIR / "en.json").read_text(encoding="utf-8"))

    for path in I18N_DIR.glob("*.json"):
        if path.name == "en.json":
            continue

        translations = json.loads(path.read_text(encoding="utf-8"))
        assert translations != reference, path.name

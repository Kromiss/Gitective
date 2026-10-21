"""Tests of the French / English texts (5.9, LG-05)."""

from __future__ import annotations

import ast
import string
import unittest
from pathlib import Path

from gitective.settings.config_file import RULE_FIELDS, RULE_MODES
from gitective.shared import i18n
from gitective.shared.i18n import t
from gitective.shared.translations_en import EN

SOURCES = Path(__file__).resolve().parents[2] / "gitective"


def translated_texts() -> dict[str, str]:
    """Every literal text passed to t() in the application, with where it is."""
    found: dict[str, str] = {}
    for path in SOURCES.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "t" and node.args
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.setdefault(node.args[0].value, f"{path.name}:{node.lineno}")
    # Labels of config_file, read before the language is chosen and translated where shown.
    for label in [*RULE_FIELDS.values(), *RULE_MODES.values()]:
        found.setdefault(label, "config_file.py")
    return found


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


class TranslationTests(unittest.TestCase):
    def tearDown(self) -> None:
        i18n.use("fr")

    def test_every_text_has_an_english_version(self) -> None:
        missing = {text: where for text, where in translated_texts().items() if text not in EN}
        self.assertEqual(missing, {})

    def test_no_unused_english_text(self) -> None:
        self.assertEqual(sorted(set(EN) - set(translated_texts())), [])

    def test_same_placeholders_in_both_languages(self) -> None:
        self.assertEqual([k for k, v in EN.items() if placeholders(k) != placeholders(v)], [])

    def test_french_by_default_english_on_demand(self) -> None:
        self.assertEqual(i18n.current(), "fr")
        self.assertEqual(t("Moi ({name})", name="Ana"), "Moi (Ana)")
        i18n.use("en")
        self.assertEqual(t("Moi ({name})", name="Ana"), "Me (Ana)")
        self.assertEqual(t("Texte inconnu"), "Texte inconnu")  # missing: stays French
        i18n.use("de")
        self.assertEqual(i18n.current(), "fr")

    def test_text_without_params_keeps_its_braces(self) -> None:
        self.assertEqual(t("{count} MR mergée(s)"), "{count} MR mergée(s)")


if __name__ == "__main__":
    unittest.main()

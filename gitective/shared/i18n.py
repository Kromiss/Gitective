"""French / English texts of the interface (5.9).

French is the source language: every text is written in French in the code
and looked up in the English dictionary when English is chosen. A text
missing from that dictionary stays in French (LG-05). The language is set
once at start-up, before the interface modules are imported (LG-02).
"""

from __future__ import annotations

from typing import Any

from gitective.shared.translations_en import EN

LANGUAGES = {"fr": "Français", "en": "English"}
DEFAULT = "fr"

_language = DEFAULT


def use(language: str) -> None:
    """Choose the language of the texts; unknown codes fall back to French."""
    global _language
    _language = language if language in LANGUAGES else DEFAULT


def current() -> str:
    return _language


def t(text: str, **params: Any) -> str:
    """Text in the current language; named `params` fill its {placeholders}."""
    if _language == "en":
        text = EN.get(text, text)
    return text.format(**params) if params else text

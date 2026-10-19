"""Translation lookup for English and Arabic UI strings."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
LANGUAGES = ("en", "ar")
_current = "en"


@lru_cache(maxsize=None)
def _table(lang: str) -> dict[str, str]:
    return json.loads((HERE / f"{lang}.json").read_text(encoding="utf-8"))


def set_language(lang: str) -> None:
    global _current
    _current = lang if lang in LANGUAGES else "en"


def current_language() -> str:
    return _current


def is_rtl() -> bool:
    return _current == "ar"


def t(key: str, **kwargs) -> str:
    """Translate a key; falls back to English, then to the key itself."""
    text = _table(_current).get(key) or _table("en").get(key) or key
    return text.format(**kwargs) if kwargs else text

"""Syllable-based name builder used by Brandable Mode."""
from __future__ import annotations

import json
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[2] / "assets"


def load_syllables(path: Path | None = None) -> list[str]:
    """Load the editable syllable list from assets/syllables.json."""
    path = path or ASSETS / "syllables.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [s.lower() for s in data["syllables"] if s.strip()]


def load_dictionary(path: Path | None = None) -> frozenset[str]:
    """Optional English word list; returns an empty set if the file is missing."""
    path = path or ASSETS / "dictionary_en.txt"
    if not path.exists():
        return frozenset()
    return frozenset(w.strip().lower() for w in path.read_text(encoding="utf-8").splitlines() if w.strip())

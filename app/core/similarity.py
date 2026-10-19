"""Near-duplicate detection for saved usernames."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

SIMILARITY_THRESHOLD = 0.85


@dataclass(frozen=True)
class SimilarMatch:
    """A saved username that looks too much like the candidate."""

    other: str
    ratio: float
    anagram: bool


def similarity_ratio(a: str, b: str) -> float:
    """Case-insensitive similarity in [0, 1]."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def is_anagram(a: str, b: str) -> bool:
    """True if two different names use exactly the same letters."""
    a_l, b_l = a.lower(), b.lower()
    return a_l != b_l and sorted(a_l) == sorted(b_l)


def find_similar(
    name: str, existing: list[str], threshold: float = SIMILARITY_THRESHOLD
) -> list[SimilarMatch]:
    """Return saved names that are near-duplicates of the candidate."""
    matches = []
    for other in existing:
        if other.lower() == name.lower():
            continue
        ratio = similarity_ratio(name, other)
        anagram = is_anagram(name, other)
        if ratio >= threshold or anagram:
            matches.append(SimilarMatch(other=other, ratio=round(ratio, 2), anagram=anagram))
    return sorted(matches, key=lambda m: m.ratio, reverse=True)

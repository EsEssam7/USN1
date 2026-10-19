"""Candidate filters applied before any network check."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

LEET_MAP = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a"})

# Reason codes returned by check_filters(); used for "why was this removed" messages.
REASON_START = "start"
REASON_END = "end"
REASON_CONTAINS = "contains"
REASON_EXCLUDED_CHAR = "excluded_char"
REASON_BLOCKED_WORD = "blocked_word"
REASON_REPEAT = "repeat"
REASON_CONSECUTIVE_DIGITS = "consecutive_digits"


@dataclass
class FilterOptions:
    """User-selected filters."""

    starts_with: str = ""
    ends_with: str = ""
    contains: str = ""
    exclude_chars: set[str] = field(default_factory=set)
    no_repeated_chars: bool = False
    no_consecutive_digits: bool = False
    blocklist: frozenset[str] = frozenset()


def parse_char_set(text: str) -> set[str]:
    """Characters typed by the user: 'q x z', 'q,x,z' and 'qxz' all give {q, x, z}."""
    return {c.lower() for c in text if c.isalnum()}


def normalize_leet(name: str) -> str:
    """Lowercase and map common leetspeak digits to letters."""
    return name.lower().translate(LEET_MAP)


def is_blocked(name: str, blocklist: Iterable[str]) -> bool:
    """True if the raw or leetspeak-normalized name contains a blocked word."""
    raw = name.lower()
    norm = normalize_leet(name)
    for word in blocklist:
        if word and (word in raw or word in norm):
            return True
    return False


def check_filters(name: str, opts: FilterOptions) -> str | None:
    """Return the reason the name was rejected, or None if it passes."""
    if opts.starts_with and not name.lower().startswith(opts.starts_with.lower()):
        return REASON_START
    if opts.ends_with and not name.lower().endswith(opts.ends_with.lower()):
        return REASON_END
    if opts.contains and opts.contains.lower() not in name.lower():
        return REASON_CONTAINS
    if opts.exclude_chars and any(c.lower() in opts.exclude_chars for c in name):
        return REASON_EXCLUDED_CHAR
    if opts.blocklist and is_blocked(name, opts.blocklist):
        return REASON_BLOCKED_WORD
    if opts.no_repeated_chars and _has_repeat(name):
        return REASON_REPEAT
    if opts.no_consecutive_digits and _has_consecutive_digits(name):
        return REASON_CONSECUTIVE_DIGITS
    return None


def _has_repeat(name: str) -> bool:
    return any(a == b for a, b in zip(name, name[1:]))


def _has_consecutive_digits(name: str) -> bool:
    return any(a.isdigit() and b.isdigit() for a, b in zip(name, name[1:]))


def parse_blocklist(text: str) -> frozenset[str]:
    """Parse a blocklist text (one word per line, '#' comments allowed)."""
    words = set()
    for line in text.splitlines():
        line = line.strip().lower()
        if line and not line.startswith("#"):
            words.add(line)
    return frozenset(words)

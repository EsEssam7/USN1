"""Pattern parsing and candidate generation."""
from __future__ import annotations

import random
from dataclasses import dataclass

CONSONANTS = "bcdfghjklmnpqrstvwxyz"
VOWELS = "aeiou"
LETTERS = "abcdefghijklmnopqrstuvwxyz"
DIGITS = "0123456789"

PRESETS: dict[str, str] = {
    "CVCV": "CVCV",
    "CVCVC": "CVCVC",
    "LLLL": "LLLL",
    "LLLLL": "LLLLL",
    "LLLDD": "LLLDD",
    "LLLL_D": "LLLL_D",
    "CVCVDD": "CVCVDD",
}


class PatternError(ValueError):
    """Raised when a pattern string is invalid."""


@dataclass(frozen=True)
class Pattern:
    """A parsed pattern. Each token is a character class or a literal."""

    source: str
    tokens: tuple[str, ...]

    @property
    def length(self) -> int:
        return len(self.tokens)

    def alphabet_size(self) -> int:
        """Number of distinct values across all tokens (product)."""
        total = 1
        for tok in self.tokens:
            total *= len(_alphabet_for(tok))
        return total


def _alphabet_for(token: str) -> str:
    if token == "L":
        return LETTERS
    if token == "C":
        return CONSONANTS
    if token == "V":
        return VOWELS
    if token == "D":
        return DIGITS
    return token


def parse_pattern(source: str) -> Pattern:
    """Parse a pattern string such as 'CVCV' or 'LLLDD'."""
    if not source or not source.strip():
        raise PatternError("empty pattern")
    if len(source) > 32:
        raise PatternError("pattern too long (max 32)")
    tokens = tuple(source.strip())
    return Pattern(source=source.strip(), tokens=tokens)


def fit_to_length(pattern: Pattern, length: int) -> Pattern:
    """Return the pattern stretched or cut to `length` tokens by repeating its tokens.

    CVCV fitted to 6 gives CVCVCV; fitted to 3 gives CVC.
    """
    if length < 1:
        raise PatternError("length must be at least 1")
    tokens = tuple(pattern.tokens[i % pattern.length] for i in range(length))
    return Pattern(source=pattern.source, tokens=tokens)


def generate_raw(pattern: Pattern, rng: random.Random) -> str:
    """Generate one random string that matches the pattern shape."""
    return "".join(rng.choice(_alphabet_for(t)) for t in pattern.tokens)


def estimate_space(pattern: Pattern) -> int:
    """Estimate the number of distinct candidates a pattern can produce."""
    return pattern.alphabet_size()


def format_count(n: int) -> str:
    """Human-readable large number, e.g. 2100000 -> '2.1M'."""
    for unit, div in (("B", 10**9), ("M", 10**6), ("K", 10**3)):
        if n >= div:
            return f"{n / div:.1f}{unit}".replace(".0", "")
    return str(n)

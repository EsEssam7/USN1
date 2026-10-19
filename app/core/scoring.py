"""Name Score: a 0-100 quality estimate for a username."""
from __future__ import annotations

from dataclasses import dataclass

VOWELS = set("aeiou")
CONFUSING_PAIRS = [("rn", 15), ("vv", 10), ("cl", 5)]
WEIGHTS = {
    "pronounceability": 0.35,
    "length_fit": 0.20,
    "readability": 0.20,
    "visual_balance": 0.15,
    "brand_feel": 0.10,
}


@dataclass(frozen=True)
class NameScore:
    """Total score and the per-factor breakdown."""

    total: int
    factors: dict[str, int]

    def top_reasons(self, n: int = 2) -> list[str]:
        """The factors that pulled the score down the most."""
        ordered = sorted(self.factors.items(), key=lambda kv: kv[1])
        return [name for name, _ in ordered[:n]]


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def _max_run(text: str, predicate) -> int:
    best = current = 0
    for ch in text:
        if predicate(ch):
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def score_name(name: str, dictionary: frozenset[str] = frozenset()) -> NameScore:
    """Score a username on five weighted factors."""
    lower = name.lower()
    letters = [c for c in lower if c.isalpha()]
    digits = [c for c in lower if c.isdigit()]

    # Pronounceability: penalize long consonant/vowel runs and digits.
    consonant_run = _max_run(lower, lambda c: c.isalpha() and c not in VOWELS)
    vowel_run = _max_run(lower, lambda c: c in VOWELS)
    pron = 100.0
    pron -= 25 * max(0, consonant_run - 2)
    pron -= 15 * max(0, vowel_run - 2)
    pron -= min(30, 5 * len(digits))
    if not letters:
        pron = 40
    pronounceability = _clamp(pron)

    # Length fit: 5-8 characters is ideal.
    n = len(lower)
    if 5 <= n <= 8:
        length_fit = 100
    elif n < 5:
        length_fit = 100 - 20 * (5 - n)
    else:
        length_fit = 100 - 10 * (n - 8)
    length_fit = _clamp(length_fit)

    # Readability: confusing letter pairs and look-alike digits.
    read = 100.0
    for pair, penalty in CONFUSING_PAIRS:
        if pair in lower:
            read -= penalty
    if "0" in lower and "o" in lower:
        read -= 10
    if "1" in lower and "l" in lower:
        read -= 10
    readability = _clamp(read)

    # Visual balance: long same-class runs and repeated characters.
    longest_class_run = max(
        _max_run(lower, str.isalpha), _max_run(lower, str.isdigit)
    )
    longest_repeat = _max_run_same_char(lower)
    balance = 100.0
    balance -= 15 * max(0, longest_class_run - 3)
    balance -= 20 * max(0, longest_repeat - 1)
    visual_balance = _clamp(balance)

    # Brand feel: alternating consonant/vowel structure or a known word.
    alt = _alternation_ratio(lower)
    brand = 50 + 50 * alt
    if lower in dictionary:
        brand = 100
    brand_feel = _clamp(brand)

    factors = {
        "pronounceability": pronounceability,
        "length_fit": length_fit,
        "readability": readability,
        "visual_balance": visual_balance,
        "brand_feel": brand_feel,
    }
    total = sum(factors[k] * WEIGHTS[k] for k in WEIGHTS)
    return NameScore(total=_clamp(total), factors=factors)


def _max_run_same_char(text: str) -> int:
    best = current = 0
    prev = None
    for ch in text:
        current = current + 1 if ch == prev else 1
        best = max(best, current)
        prev = ch
    return best


def _alternation_ratio(text: str) -> float:
    """Fraction of adjacent letter pairs that switch between vowel and consonant."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 2:
        return 0.5
    switches = sum(
        1
        for a, b in zip(letters, letters[1:])
        if (a in VOWELS) != (b in VOWELS)
    )
    return switches / (len(letters) - 1)

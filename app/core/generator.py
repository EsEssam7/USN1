"""Combines patterns, brandable syllables, filters and platform rules into candidates."""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field

from app.core.filters import FilterOptions, check_filters
from app.core.patterns import Pattern, fit_to_length, generate_raw, parse_pattern
from app.core.platform_rules import get_rule, valid_on_all

MODE_PATTERN = "pattern"
MODE_BRANDABLE = "brandable"
MAX_ATTEMPT_FACTOR = 60  # attempts per requested candidate before giving up
REASON_PLATFORM = "platform"
REASON_DUPLICATE = "duplicate"
REASON_LENGTH = "length"


@dataclass
class GenerationRequest:
    """Everything needed to generate one batch of candidates."""

    mode: str = MODE_PATTERN
    pattern: str = "CVCV"
    min_length: int = 4
    max_length: int = 8
    platforms: list[str] = field(default_factory=list)
    filters: FilterOptions = field(default_factory=FilterOptions)
    count: int = 50
    syllables: list[str] = field(default_factory=list)
    seed: int | None = None
    exclude: set[str] = field(default_factory=set)  # already shown, skipped on "Load more"
    words_only: bool = False  # brandable mode: draw real English words instead of syllables


@dataclass
class GenerationResult:
    """Output of a generation run."""

    usernames: list[str]
    rejected: Counter
    space_estimate: int | None
    warnings: list[tuple[str, dict]] = field(default_factory=list)  # (translation key, values)


def explain_problems(request: GenerationRequest) -> list[tuple[str, dict]]:
    """Find inputs that can never produce a name, and say which platform causes it.

    A name must pass every selected platform, so one platform that forbids a character
    makes that character impossible everywhere.
    """
    rules = [get_rule(k) for k in request.platforms]
    problems: list[tuple[str, dict]] = []

    def blocked_by(ch: str, position: str) -> list[str]:
        return [r.name for r in rules if not r.allows_char(ch, position)]

    for key, text, position in (
        ("gen.problem.start", request.filters.starts_with, "start"),
        ("gen.problem.end", request.filters.ends_with, "end"),
        ("gen.problem.contains", request.filters.contains, "middle"),
    ):
        seen = set()
        for ch in text:
            if ch in seen:
                continue
            seen.add(ch)
            bad = blocked_by(ch, position)
            if bad:
                problems.append((key, {"char": ch, "platforms": ", ".join(bad)}))

    if request.mode == MODE_PATTERN and request.pattern.strip():
        pattern = parse_pattern(request.pattern)
        literals = {t for t in pattern.tokens if t not in "LCVD"}
        for ch in sorted(literals):
            bad = blocked_by(ch, "middle")
            if bad:
                problems.append(("gen.problem.literal", {"char": ch, "platforms": ", ".join(bad)}))
    return problems


def _length_window(min_len: int, max_len: int, platforms: list[str]) -> tuple[int, int]:
    """Lengths allowed by both the user range and every selected platform."""
    from app.core.platform_rules import get_rule

    lo, hi = min_len, max_len
    for key in platforms:
        rule = get_rule(key)
        lo, hi = max(lo, rule.min_length), min(hi, rule.max_length)
    return lo, hi


def _space_estimate(pattern: Pattern, lo: int, hi: int) -> int:
    """Possible combinations across every length in the window."""
    return sum(fit_to_length(pattern, n).alphabet_size() for n in range(lo, hi + 1))


def generate(
    request: GenerationRequest,
    rng: random.Random | None = None,
    dictionary: frozenset[str] = frozenset(),
) -> GenerationResult:
    """Generate up to request.count unique usernames that pass every rule.

    Random sampling with rejection: cheap for large spaces, and it never
    enumerates the full pattern space.
    """
    rng = rng or random.Random(request.seed)
    if request.min_length > request.max_length:
        raise ValueError("min length is larger than max length")
    rejected: Counter = Counter()
    warnings: list[tuple[str, dict]] = explain_problems(request)
    if warnings:  # impossible inputs: stop before sampling thousands of names
        return GenerationResult(usernames=[], rejected=rejected, space_estimate=None, warnings=warnings)
    seen: set[str] = set(request.exclude)
    results: list[str] = []
    lo, hi = _length_window(request.min_length, request.max_length, request.platforms)
    if lo > hi:
        warnings.append(("gen.warn.window", {"min": request.min_length, "max": request.max_length}))
        return GenerationResult(usernames=[], rejected=rejected, space_estimate=None, warnings=warnings)

    if request.mode == MODE_BRANDABLE and request.words_only:
        words = [w for w in dictionary if lo <= len(w) <= hi]
        if not words:
            warnings.append(("gen.warn.no_words", {}))
            return GenerationResult(usernames=[], rejected=rejected, space_estimate=None, warnings=warnings)
        space = len(words)
        sampler = lambda: rng.choice(words)  # noqa: E731
    elif request.mode == MODE_BRANDABLE:
        if not request.syllables:
            raise ValueError("brandable mode needs syllables")
        space = None
        sampler = lambda: _brandable(rng, request.syllables)  # noqa: E731
    else:
        pattern = parse_pattern(request.pattern)
        space = _space_estimate(pattern, lo, hi)
        # Each attempt picks a length in the window and stretches the pattern to it.
        sampler = lambda: generate_raw(fit_to_length(pattern, rng.randint(lo, hi)), rng)  # noqa: E731

    max_attempts = max(request.count, 1) * MAX_ATTEMPT_FACTOR
    attempts = 0
    while len(results) < request.count and attempts < max_attempts:
        attempts += 1
        name = sampler()
        if not lo <= len(name) <= hi:
            rejected[REASON_LENGTH] += 1
            continue
        if name in seen:
            rejected[REASON_DUPLICATE] += 1
            continue
        reason = check_filters(name, request.filters)
        if reason:
            rejected[reason] += 1
            continue
        if request.platforms and not valid_on_all(name, request.platforms):
            rejected[REASON_PLATFORM] += 1
            continue
        seen.add(name)
        results.append(name)

    if len(results) < request.count:
        warnings.append(("gen.warn.not_enough", {"found": len(results), "wanted": request.count}))
    if lo != request.min_length or hi != request.max_length:
        warnings.append(("gen.warn.window_adjusted", {"min": lo, "max": hi}))
    return GenerationResult(usernames=results, rejected=rejected, space_estimate=space, warnings=warnings)


def _brandable(rng: random.Random, syllables: list[str]) -> str:
    """Join two or three syllables. The caller rejects names outside the length window."""
    parts = rng.randint(2, 3)
    return "".join(rng.choice(syllables) for _ in range(parts)).lower()

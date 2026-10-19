"""Platform username rules: loading and validation."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

RULES_PATH = Path(__file__).with_name("platform_rules.json")


@dataclass(frozen=True)
class PlatformRule:
    """Validation rules for one platform."""

    key: str
    name: str
    min_length: int
    max_length: int
    allowed_chars: str
    must_start_with_letter: bool = False
    forbidden_edges: tuple[str, ...] = ()
    forbidden_sequences: tuple[str, ...] = ()
    case_sensitive: bool = False
    reserved_words: tuple[str, ...] = ()
    profile_url: str | None = None
    soft_404_markers: tuple[str, ...] = ()
    last_verified: str = ""
    _pattern: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_pattern", re.compile(rf"^[{self.allowed_chars}]+$"))

    def violations(self, username: str) -> list[str]:
        """Return the list of violated rule names (empty means valid)."""
        problems: list[str] = []
        if not self.min_length <= len(username) <= self.max_length:
            problems.append("length")
        if not self._pattern.match(username):
            problems.append("chars")
        if self.must_start_with_letter and not username[:1].isalpha():
            problems.append("start")
        if username and (username[0] in self.forbidden_edges or username[-1] in self.forbidden_edges):
            problems.append("edge")
        if any(seq in username for seq in self.forbidden_sequences):
            problems.append("sequence")
        check = username if self.case_sensitive else username.lower()
        if check in self.reserved_words:
            problems.append("reserved")
        return problems

    def is_valid(self, username: str) -> bool:
        """True if the username satisfies every rule."""
        return not self.violations(username)

    def allows_char(self, ch: str, position: str = "middle") -> bool:
        """Can this single character appear at position 'start', 'end' or 'middle'?"""
        if len(ch) != 1:
            return False
        check = ch if self.case_sensitive else ch.lower()
        if not self._pattern.match(check):
            return False
        if position in ("start", "end") and check in self.forbidden_edges:
            return False
        if position == "start" and self.must_start_with_letter and not check.isalpha():
            return False
        return True

    def profile_link(self, username: str) -> str | None:
        """Public profile URL for this username, if the platform has one."""
        return self.profile_url.format(username=username) if self.profile_url else None


@lru_cache(maxsize=1)
def load_rules() -> dict[str, PlatformRule]:
    """Load every platform rule from the bundled JSON file."""
    raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    rules: dict[str, PlatformRule] = {}
    for key, data in raw.items():
        rules[key] = PlatformRule(
            key=key,
            name=data["name"],
            min_length=data["min_length"],
            max_length=data["max_length"],
            allowed_chars=data["allowed_chars"],
            must_start_with_letter=data.get("must_start_with_letter", False),
            forbidden_edges=tuple(data.get("forbidden_edges", [])),
            forbidden_sequences=tuple(data.get("forbidden_sequences", [])),
            case_sensitive=data.get("case_sensitive", False),
            reserved_words=tuple(data.get("reserved_words", [])),
            profile_url=data.get("profile_url"),
            soft_404_markers=tuple(m.lower() for m in data.get("soft_404_markers", [])),
            last_verified=data.get("last_verified", ""),
        )
    return rules


def get_rule(key: str) -> PlatformRule:
    """Return the rule for a platform key (KeyError if unknown)."""
    return load_rules()[key]


def valid_on_all(username: str, platform_keys: list[str]) -> bool:
    """True if the username is valid on every selected platform."""
    return all(get_rule(k).is_valid(username) for k in platform_keys)

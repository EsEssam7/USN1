"""Availability checks: taken / likely available / unknown / invalid, with a 24h cache."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Callable

import requests

from app.core.platform_rules import PlatformRule, get_rule
from app.services.storage import JsonStore

CACHE_TTL_SECONDS = 24 * 3600
MAX_PER_PLATFORM = 4
TIMEOUT_SECONDS = 5
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MAX_BODY_CHARS = 200_000


class Status(str, Enum):
    TAKEN = "taken"
    LIKELY_AVAILABLE = "likely_available"
    UNKNOWN = "unknown"          # blocked, rate limited, timeout, or ambiguous
    NOT_CHECKABLE = "not_checkable"  # platform has no public profile page to check
    INVALID = "invalid"


@dataclass(frozen=True)
class CheckResult:
    """Outcome of checking one username on one platform."""

    platform: str
    username: str
    status: Status
    detail: str
    checked_at: float
    url: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        return data


Fetcher = Callable[..., requests.Response]


class AvailabilityChecker:
    """Checks usernames against public profile pages."""

    def __init__(
        self,
        cache: JsonStore | None = None,
        fetch: Fetcher = requests.get,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._cache_store = cache
        self._cache: dict[str, dict] = cache.load() if cache else {}
        self._fetch = fetch
        self._clock = clock
        self._lock = threading.Lock()
        self._semaphores = {}

    # ---- cache -------------------------------------------------------------
    def _cache_get(self, key: str) -> CheckResult | None:
        entry = self._cache.get(key)
        if not entry or self._clock() - entry["checked_at"] > CACHE_TTL_SECONDS:
            return None
        return CheckResult(
            platform=entry["platform"], username=entry["username"],
            status=Status(entry["status"]), detail=entry["detail"],
            checked_at=entry["checked_at"], url=entry.get("url"),
        )

    def _cache_put(self, key: str, result: CheckResult) -> None:
        with self._lock:
            self._cache[key] = result.to_dict()
            if self._cache_store:
                self._cache_store.save(self._cache)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache = {}
            if self._cache_store:
                self._cache_store.save(self._cache)

    # ---- checks ------------------------------------------------------------
    def check_one(self, username: str, platform_key: str, use_cache: bool = True) -> CheckResult:
        """Check a single username on a single platform."""
        rule = get_rule(platform_key)
        now = self._clock()
        if not rule.is_valid(username):
            return CheckResult(platform_key, username, Status.INVALID,
                               "rule violation: " + ", ".join(rule.violations(username)), now)

        key = f"{platform_key}:{username.lower()}"
        if use_cache:
            cached = self._cache_get(key)
            if cached:
                return cached

        result = self._fetch_status(rule, username, now)
        if result.status is not Status.UNKNOWN or "rate" not in result.detail:
            self._cache_put(key, result)
        return result

    def _fetch_status(self, rule: PlatformRule, username: str, now: float) -> CheckResult:
        url = rule.profile_link(username)
        if url is None:
            return CheckResult(rule.key, username, Status.NOT_CHECKABLE,
                               "no public profile page", now)
        try:
            response = self._fetch(
                url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
                timeout=TIMEOUT_SECONDS, allow_redirects=True,
            )
        except requests.RequestException as exc:
            return CheckResult(rule.key, username, Status.UNKNOWN,
                               f"network error: {type(exc).__name__}", now, url)

        code = response.status_code
        if code == 429:
            return CheckResult(rule.key, username, Status.UNKNOWN, "rate limited, try later", now, url)
        if code == 404:
            return CheckResult(rule.key, username, Status.LIKELY_AVAILABLE, "profile not found", now, url)
        if code == 200:
            body = (response.text or "")[:MAX_BODY_CHARS].lower()
            if any(marker in body for marker in rule.soft_404_markers):
                return CheckResult(rule.key, username, Status.LIKELY_AVAILABLE,
                                   "soft 404 page", now, url)
            return CheckResult(rule.key, username, Status.TAKEN, "profile exists", now, url)
        return CheckResult(rule.key, username, Status.UNKNOWN, f"HTTP {code}", now, url)

    def check_many(self, username: str, platform_keys: list[str]) -> list[CheckResult]:
        """Check one username on several platforms in parallel (max 4 per platform)."""
        if not platform_keys:
            return []
        results: dict[str, CheckResult] = {}

        def run(key: str) -> None:
            sem = self._semaphores.setdefault(key, threading.Semaphore(MAX_PER_PLATFORM))
            with sem:
                results[key] = self.check_one(username, key)

        with ThreadPoolExecutor(max_workers=min(8, len(platform_keys))) as pool:
            list(pool.map(run, platform_keys))
        return [results[k] for k in platform_keys]

"""Availability checker tests using a fake HTTP fetcher (no real network)."""
from types import SimpleNamespace

import requests

from app.services.availability import AvailabilityChecker, Status


class FakeResponse(SimpleNamespace):
    pass


def make_fetch(status=404, text=""):
    calls = []

    def fetch(url, **kwargs):
        calls.append(url)
        return FakeResponse(status_code=status, text=text)

    fetch.calls = calls
    return fetch


def test_404_means_likely_available():
    checker = AvailabilityChecker(fetch=make_fetch(404))
    res = checker.check_one("kenoro", "github", use_cache=False)
    assert res.status is Status.LIKELY_AVAILABLE


def test_200_means_taken():
    checker = AvailabilityChecker(fetch=make_fetch(200, "<html>profile</html>"))
    assert checker.check_one("kenoro", "github", use_cache=False).status is Status.TAKEN


def test_soft_404_marker_on_200_is_available():
    checker = AvailabilityChecker(fetch=make_fetch(200, "Sorry, this page isn't available."))
    assert checker.check_one("kenoro", "instagram", use_cache=False).status is Status.LIKELY_AVAILABLE


def test_429_is_unknown_and_not_cached():
    fetch = make_fetch(429)
    checker = AvailabilityChecker(fetch=fetch)
    res = checker.check_one("kenoro", "github")
    assert res.status is Status.UNKNOWN and "rate" in res.detail
    checker.check_one("kenoro", "github")
    assert len(fetch.calls) == 2  # rate-limited answers are never cached


def test_network_error_is_unknown():
    def boom(url, **kwargs):
        raise requests.ConnectionError("down")

    checker = AvailabilityChecker(fetch=boom)
    assert checker.check_one("kenoro", "github", use_cache=False).status is Status.UNKNOWN


def test_invalid_username_never_hits_network():
    fetch = make_fetch(404)
    checker = AvailabilityChecker(fetch=fetch)
    res = checker.check_one("bad name!", "github")
    assert res.status is Status.INVALID and fetch.calls == []


def test_platform_without_profile_page_is_unknown():
    fetch = make_fetch(404)
    checker = AvailabilityChecker(fetch=fetch)
    res = checker.check_one("kenoro", "discord", use_cache=False)
    assert res.status is Status.NOT_CHECKABLE and fetch.calls == []


def test_cache_hit_within_ttl_and_expiry():
    now = [1000.0]
    fetch = make_fetch(404)
    checker = AvailabilityChecker(fetch=fetch, clock=lambda: now[0])
    checker.check_one("kenoro", "github")
    checker.check_one("kenoro", "github")
    assert len(fetch.calls) == 1
    now[0] += 25 * 3600
    checker.check_one("kenoro", "github")
    assert len(fetch.calls) == 2


def test_check_many_returns_one_result_per_platform():
    checker = AvailabilityChecker(fetch=make_fetch(404))
    results = checker.check_many("kenoro", ["github", "reddit", "x"])
    assert [r.platform for r in results] == ["github", "reddit", "x"]

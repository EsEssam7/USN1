"""Unit tests for the pure core logic (no UI, no network)."""
import random

import pytest

from app.core.brandable import load_syllables
from app.core.export import favorites_from_csv, favorites_to_csv
from app.core.filters import (
    REASON_BLOCKED_WORD, REASON_CONSECUTIVE_DIGITS, REASON_END, REASON_REPEAT, REASON_START,
    FilterOptions, check_filters, normalize_leet, parse_blocklist,
)
from app.core.generator import MODE_BRANDABLE, GenerationRequest, generate
from app.core.patterns import PatternError, generate_raw, parse_pattern
from app.core.phonetics import arabic_reading, speech_text
from app.core.platform_rules import get_rule, valid_on_all
from app.core.scoring import score_name
from app.core.similarity import find_similar, is_anagram


# ---- patterns ----------------------------------------------------------------
def test_pattern_cvcv_produces_alternating_classes():
    p = parse_pattern("CVCV")
    rng = random.Random(1)
    for _ in range(200):
        name = generate_raw(p, rng)
        assert name[0] not in "aeiou" and name[1] in "aeiou"
        assert name[2] not in "aeiou" and name[3] in "aeiou"


def test_pattern_digits_and_literals():
    p = parse_pattern("LLL_D")
    name = generate_raw(p, random.Random(2))
    assert name[3] == "_" and name[4].isdigit()


def test_empty_pattern_rejected():
    with pytest.raises(PatternError):
        parse_pattern("   ")


def test_alphabet_size_for_cvcv():
    assert parse_pattern("CVCV").alphabet_size() == 21 * 5 * 21 * 5


# ---- platform rules ---------------------------------------------------------
def test_x_length_limits():
    assert get_rule("x").is_valid("abcd")
    assert not get_rule("x").is_valid("abc")
    assert not get_rule("x").is_valid("a" * 16)


def test_instagram_rules():
    rule = get_rule("instagram")
    assert rule.is_valid("my.name_1")
    assert not rule.is_valid("name.")
    assert not rule.is_valid("na..me")


def test_telegram_must_start_with_letter():
    rule = get_rule("telegram")
    assert rule.is_valid("hello1")
    assert "start" in rule.violations("1hello")


def test_github_hyphen_rules():
    rule = get_rule("github")
    assert rule.is_valid("my-name")
    assert not rule.is_valid("-myname")
    assert not rule.is_valid("my--name")


def test_intersection_across_platforms():
    assert valid_on_all("abcdef", ["x", "github"])
    assert not valid_on_all("abc_def", ["github"])


def test_reserved_word_blocked():
    assert "reserved" in get_rule("x").violations("admin")


# ---- filters -----------------------------------------------------------------
def test_start_and_end_filters():
    opts = FilterOptions(starts_with="ka", ends_with="o")
    assert check_filters("kario", opts) is None
    assert check_filters("ariso", opts) == REASON_START
    assert check_filters("karis", opts) == REASON_END


def test_leetspeak_blocklist():
    assert normalize_leet("S4T") == "sat"
    opts = FilterOptions(blocklist=frozenset({"kill"}))
    assert check_filters("k1ll3r", opts) == REASON_BLOCKED_WORD


def test_repeat_and_digit_filters():
    assert check_filters("aaron", FilterOptions(no_repeated_chars=True)) == REASON_REPEAT
    assert check_filters("ab11c", FilterOptions(no_consecutive_digits=True)) == REASON_CONSECUTIVE_DIGITS


def test_parse_blocklist_ignores_comments_and_blanks():
    assert parse_blocklist("# c\n\nFoo\n bar \n") == frozenset({"foo", "bar"})


def test_shipped_blocklist_loads():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "assets" / "blocklist.txt").read_text(encoding="utf-8")
    assert "kill" in parse_blocklist(text)


# ---- generator ---------------------------------------------------------------
def test_generate_unique_and_valid_for_platforms():
    req = GenerationRequest(pattern="CVCVC", min_length=5, max_length=5,
                            platforms=["x", "github"], count=30, seed=7)
    res = generate(req)
    assert len(res.usernames) == 30
    assert len(set(res.usernames)) == 30
    assert all(valid_on_all(n, ["x", "github"]) for n in res.usernames)


def test_generate_respects_filters():
    req = GenerationRequest(pattern="LLLL", min_length=4, max_length=4, count=20, seed=3,
                            filters=FilterOptions(starts_with="a", exclude_chars={"q", "x", "z"}))
    res = generate(req)
    assert res.usernames and all(n.startswith("a") and not set(n) & {"q", "x", "z"} for n in res.usernames)


def test_length_range_stretches_pattern():
    req = GenerationRequest(pattern="CVCV", min_length=5, max_length=8, platforms=["x", "discord"],
                            count=50, seed=4)
    res = generate(req)
    assert len(res.usernames) == 50
    assert all(5 <= len(n) <= 8 for n in res.usernames)


def test_length_range_with_no_platform_overlap_warns():
    req = GenerationRequest(pattern="LLLL", min_length=2, max_length=3, platforms=["telegram"], count=5, seed=1)
    res = generate(req)
    assert res.usernames == [] and res.warnings and res.warnings[0][0] == "gen.warn.window"


def test_fit_to_length_repeats_tokens():
    from app.core.patterns import fit_to_length
    assert "".join(fit_to_length(parse_pattern("CVCV"), 6).tokens) == "CVCVCV"
    assert "".join(fit_to_length(parse_pattern("CVCV"), 3).tokens) == "CVC"


def test_exclude_parsing_accepts_spaces_commas_and_plain_text():
    from app.core.filters import parse_char_set
    assert parse_char_set("q x z") == parse_char_set("q,x,z") == parse_char_set("qxz") == {"q", "x", "z"}


def test_brandable_mode_uses_syllables():
    req = GenerationRequest(mode=MODE_BRANDABLE, min_length=4, max_length=9, count=15,
                            syllables=load_syllables(), seed=5)
    res = generate(req)
    assert len(res.usernames) == 15
    assert all(4 <= len(n) <= 9 for n in res.usernames)


# ---- scoring -----------------------------------------------------------------
def test_score_prefers_pronounceable_names():
    good = score_name("kenoro").total
    bad = score_name("xkqzrtpx").total
    assert good > bad


def test_score_returns_factor_breakdown():
    s = score_name("kenoro")
    assert set(s.factors) == {"pronounceability", "length_fit", "readability", "visual_balance", "brand_feel"}
    assert 0 <= s.total <= 100
    assert len(s.top_reasons()) == 2


# ---- similarity ---------------------------------------------------------------
def test_similar_name_detected():
    matches = find_similar("kenorro", ["kenoro"])
    assert matches and matches[0].other == "kenoro"


def test_anagram_detected():
    assert is_anagram("silent", "listen")
    assert find_similar("listen", ["silent"])


def test_unrelated_names_not_flagged():
    assert find_similar("zephyrus", ["kenoro", "tavi"]) == []


# ---- phonetics ----------------------------------------------------------------
def test_arabic_reading_digraphs():
    assert arabic_reading("sharo") == "شارو"


def test_speech_text_spells_digits_and_separators():
    assert speech_text("a_1") == "a underscore one"


# ---- export -------------------------------------------------------------------
def test_csv_round_trip():
    favs = [{"username": "kenoro", "note": "nice", "score": 88, "date": "2026-10-01"}]
    back = favorites_from_csv(favorites_to_csv(favs))
    assert back[0]["username"] == "kenoro" and back[0]["note"] == "nice"


# ---- diagnosis of impossible inputs (the "name starts with a dot" bug) -------
from app.core.generator import explain_problems  # noqa: E402


def test_leading_dot_is_explained_not_silently_empty():
    req = GenerationRequest(pattern="CVCV", min_length=4, max_length=8, platforms=["instagram", "x"],
                            count=10, seed=1, filters=FilterOptions(starts_with="."))
    res = generate(req)
    assert res.usernames == []
    keys = [(k, kw.get("char")) for k, kw in res.warnings]
    assert ("gen.problem.start", ".") in keys
    # the message names the platforms that forbid it, and the search stops early
    kw = next(kw for k, kw in res.warnings if k == "gen.problem.start")
    assert "Instagram" in kw["platforms"] and "X" in kw["platforms"]
    assert sum(res.rejected.values()) == 0


def test_dot_start_is_allowed_when_every_platform_allows_it():
    req = GenerationRequest(pattern="CVCV", min_length=4, max_length=8, platforms=["discord"],
                            count=5, seed=1, filters=FilterOptions(starts_with="."))
    assert explain_problems(req)  # Discord forbids a leading period too
    req2 = GenerationRequest(pattern="CVCV", min_length=4, max_length=8, platforms=["reddit"],
                             count=5, seed=1, filters=FilterOptions(starts_with="_"))
    assert explain_problems(req2) == []


def test_pattern_literal_not_allowed_is_explained():
    req = GenerationRequest(pattern="LLL.D", min_length=5, max_length=5, platforms=["x"], count=5, seed=1)
    problems = explain_problems(req)
    assert problems and problems[0][0] == "gen.problem.literal" and problems[0][1]["char"] == "."


def test_start_with_digit_on_telegram_is_explained():
    req = GenerationRequest(pattern="LLLLL", min_length=5, max_length=8, platforms=["telegram"],
                            count=5, seed=1, filters=FilterOptions(starts_with="1"))
    assert explain_problems(req)[0][0] == "gen.problem.start"


def test_allows_char_positions():
    from app.core.platform_rules import get_rule
    assert not get_rule("instagram").allows_char(".", "end")
    assert get_rule("instagram").allows_char(".", "middle")
    assert not get_rule("telegram").allows_char("1", "start")
    assert get_rule("telegram").allows_char("a", "start")


def test_double_underscore_is_allowed_on_discord_and_tiktok():
    from app.core.platform_rules import get_rule
    assert get_rule("discord").is_valid("a__b")
    assert get_rule("tiktok").is_valid("a__b")
    assert not get_rule("discord").is_valid("a..b")


# ---- real English words in Brandable mode -------------------------------------
def test_words_only_draws_dictionary_words_in_range():
    from app.core.brandable import load_dictionary
    words = load_dictionary()
    assert len(words) > 10000
    req = GenerationRequest(mode=MODE_BRANDABLE, words_only=True, min_length=5, max_length=6,
                            count=20, seed=9)
    res = generate(req, dictionary=words)
    assert len(res.usernames) == 20
    assert all(n in words and 5 <= len(n) <= 6 for n in res.usernames)


def test_words_only_without_dictionary_explains_itself():
    req = GenerationRequest(mode=MODE_BRANDABLE, words_only=True, min_length=5, max_length=6, count=5, seed=1)
    res = generate(req, dictionary=frozenset())
    assert res.usernames == [] and res.warnings[0][0] == "gen.warn.no_words"

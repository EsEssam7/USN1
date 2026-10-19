"""Approximate Arabic reading and speech-friendly text for usernames."""
from __future__ import annotations

# Multi-letter digraphs are matched first, then single letters.
DIGRAPHS = {
    "sh": "ش", "th": "ث", "kh": "خ", "gh": "غ", "ch": "تش",
    "ph": "ف", "ee": "ي", "oo": "و", "ou": "و", "ai": "اي", "ay": "اي",
}
SINGLE = {
    "a": "ا", "b": "ب", "c": "ك", "d": "د", "e": "ي", "f": "ف", "g": "ج",
    "h": "ه", "i": "ي", "j": "ج", "k": "ك", "l": "ل", "m": "م", "n": "ن",
    "o": "و", "p": "ب", "q": "ق", "r": "ر", "s": "س", "t": "ت", "u": "و",
    "v": "ف", "w": "و", "x": "كس", "y": "ي", "z": "ز",
}
DIGIT_WORDS_EN = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
SEPARATOR_WORDS = {"_": "underscore", ".": "dot", "-": "dash"}


def arabic_reading(name: str) -> str:
    """Approximate Arabic-script reading. Digits and separators are dropped."""
    out = []
    text = name.lower()
    i = 0
    while i < len(text):
        pair = text[i:i + 2]
        if pair in DIGRAPHS:
            out.append(DIGRAPHS[pair])
            i += 2
            continue
        ch = text[i]
        if ch in SINGLE:
            out.append(SINGLE[ch])
        i += 1
    return "".join(out)


def speech_text(name: str) -> str:
    """Text to speak: separators named, digits spelled out."""
    parts = []
    for ch in name:
        if ch.isdigit():
            parts.append(DIGIT_WORDS_EN[int(ch)])
        elif ch in SEPARATOR_WORDS:
            parts.append(SEPARATOR_WORDS[ch])
        else:
            parts.append(ch)
    return " ".join(parts)

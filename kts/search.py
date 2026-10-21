"""
The search of the portal (1.2.90): the words of a query, the matching of a text (every word must be in it, in any case,
whatever the invisible joiners of Indic scripts), a short passage around the first match, and the text with each match
marked; the text is escaped, the marks are the only markup.

A word in Latin letters matches at the start of a word ("rain" finds "rain" and "rainfall", not "brain"); a word in an
Indian script matches anywhere, since its words join in sandhi and take endings ("வான்" finds "வான்சிறப்பு").
"""
import re
import unicodedata
from functools import lru_cache

from markupsafe import Markup, escape

MAX_QUERY = 80        # characters of a query that are read
MAX_WORDS = 8
# the joiners that an Indic text may or may not carry: they take no part in a match
INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿"))


def norm(text):
    """The text as it is compared: NFC, without invisible joiners, case-folded, single spaces."""
    return " ".join(unicodedata.normalize("NFC", str(text or "")).translate(INVISIBLE).casefold().split())


def query_words(q):
    """The words of a query (at most eight); none when the query has fewer than two letters in all."""
    words = norm((q or "")[:MAX_QUERY]).split()[:MAX_WORDS]
    return words if len("".join(words)) >= 2 else []


def _word_pattern(word):
    """A word in Latin letters or digits begins a word of the text; any other is found anywhere."""
    if word.isascii():
        return r"(?<![0-9a-z])" + re.escape(word)
    return re.escape(word)


@lru_cache(maxsize=256)
def _compiled(words):
    return tuple(re.compile(_word_pattern(w), re.IGNORECASE) for w in words)


@lru_cache(maxsize=256)
def _alternation(words):
    ordered = sorted(set(words), key=len, reverse=True)
    return re.compile("|".join(_word_pattern(w) for w in ordered), re.IGNORECASE)


def matches(text, words):
    """Whether every word is in the text (the text normalised with norm())."""
    return bool(words) and all(p.search(text) for p in _compiled(tuple(words)))


def highlight(text, words):
    """The text, escaped, with each occurrence of the words in <mark>."""
    text = unicodedata.normalize("NFC", str(text or "")).translate(INVISIBLE)
    if not words:
        return escape(text)
    parts, pos = [], 0
    for m in _alternation(tuple(words)).finditer(text):
        parts.append(escape(text[pos:m.start()]))
        parts.append(Markup("<mark>{}</mark>").format(m.group(0)))
        pos = m.end()
    parts.append(escape(text[pos:]))
    return Markup("").join(parts)


def snippet(text, words, width=200):
    """A passage of about `width` characters around the first match, with the matches marked."""
    text = " ".join(unicodedata.normalize("NFC", str(text or "")).translate(INVISIBLE).split())
    if len(text) <= width:
        return highlight(text, words)
    m = _alternation(tuple(words)).search(text) if words else None
    start = max(0, (m.start() if m else 0) - width // 3)
    end = min(len(text), start + width)
    start = max(0, end - width)
    piece = text[start:end]
    return Markup("{}{}{}").format("… " if start else "", highlight(piece, words), " …" if end < len(text) else "")

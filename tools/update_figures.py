"""
The figures of the home page's banner "KTS 5.0 in numbers" that are not counted from the portal's own files
(data/figures.json, 1.2.129): the hours of the audio recordings, and the headline figures of CICT's Digital Archives
(https://www.digitalarchives.cict.in/) and of its lexical tools, read from that page. Run it again when the archives grow:

    python tools/update_figures.py                      # reads the live page
    python tools/update_figures.py path/to/saved.html   # reads a saved copy

The counts that the portal can count itself (couplets, recordings, videos, posters, seminars …) are counted at each
start (kts/public.py portal_figures) and are not in the file.
"""
import html
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = "https://www.digitalarchives.cict.in/"
OUT = ROOT / "data" / "figures.json"


def text_of(page):
    """The words of the page, in one line (its tags removed; the figures stand in markup that a script writes)."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def number(words, label):
    """The figure written right before a label of the page ("865 Manuscript Bundles"), as an int; None when absent."""
    m = re.search(r"([\d,]+)\+?\s*" + re.escape(label) + "(?![A-Za-z])", words)
    return int(m.group(1).replace(",", "")) if m else None


def first_after(words, heading, label):
    """The first figure that follows a heading and stands before a label ("Tamil Audio Lexicon … 59,170 Entries")."""
    m = re.search(re.escape(heading) + r"\D{0,120}?([\d,]+)\s*" + re.escape(label), words)
    return int(m.group(1).replace(",", "")) if m else None


def archives_figures(page):
    words = text_of(page)
    figures = {
        # the hero of the page: "865 Manuscript Bundles approx. 1,00,000 leaves … 41 Classical Texts … 15 Source Institutions
        # … 6 Critical Editions"; the lexical tools are counted in words ("Seventeen indispensable companion tools")
        "bundles": number(words, "Manuscript Bundles"),
        "leaves": number(words, "leaves"),
        "texts": number(words, "Classical Texts"),
        "institutions": number(words, "Source Institutions"),
        "editions": number(words, "Critical Editions"),
        "lexical_tools": 17 if "Seventeen indispensable companion tools" in words else None,
        # the lexical tools' own figures: the Classical Tamil lexicon ("1,08,655 Lexical Words Indexed … 2,75,262 Citations
        # Documented … 6,758 Lexicon Entries") and the Tamil Audio Lexicon ("59,170 Entries … 55,831 Headwords … 5,547
        # Sanskrit-origin")
        "lexical_words": number(words, "Lexical Words Indexed"),
        "citations": number(words, "Citations Documented"),
        "lexicon_entries": number(words, "Lexicon Entries"),
        "audio_lexicon_entries": first_after(words, "Tamil Audio Lexicon", "Entries"),
        "audio_lexicon_headwords": number(words, "Headwords"),
        "audio_lexicon_sanskrit": number(words, "Sanskrit-origin"),
    }
    m = re.search(r'"specimens"\s*:\s*\[', page)
    if m:  # the Tirukkural ground-truth corpus: its published specimens
        j = m.end(); depth = 1; k = j
        while depth and k < len(page):
            depth += {"[": 1, "]": -1}.get(page[k], 0); k += 1
        figures["gt_specimens"] = len(json.loads("[" + page[j:k - 1] + "]"))
    missing = [k for k, v in figures.items() if not v]
    assert not missing, f"not found on the page: {missing}"
    return figures


def audio_hours():
    """The hours of the portal's audio recordings (static/audio), from the MP3 frames (no library needed)."""
    seconds = 0.0
    for path in (ROOT / "static" / "audio").rglob("*.mp3"):
        seconds += mp3_seconds(path.read_bytes())
    return round(seconds / 3600, 1)


BITRATES = {1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320], 2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}
RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def mp3_seconds(data):
    """The length of an MP3 file: its frames walked one by one (the ID3 tag at the start skipped)."""
    i = 0
    if data[:3] == b"ID3":
        i = 10 + ((data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F))
    seconds = 0.0
    n = len(data)
    while i + 4 <= n:
        b1, b2, b3 = data[i + 1], data[i + 2], data[i + 3]
        if data[i] != 0xFF or (b1 & 0xE0) != 0xE0:
            i += 1
            continue
        version = (b1 >> 3) & 3            # 3 = MPEG-1, 2 = MPEG-2, 0 = MPEG-2.5
        layer = (b1 >> 1) & 3              # 1 = layer III
        if version == 1 or layer != 1:
            i += 1
            continue
        bitrate = BITRATES[1 if version == 3 else 2][(b2 >> 4) & 15]
        rate = RATES[version][(b2 >> 2) & 3] if ((b2 >> 2) & 3) != 3 else 0
        if not bitrate or not rate:
            i += 1
            continue
        samples = 1152 if version == 3 else 576
        length = (144 if version == 3 else 72) * bitrate * 1000 // rate + ((b2 >> 1) & 1)
        seconds += samples / rate
        i += length
    return seconds


def main(source=None):
    if source:
        page = Path(source).read_text(encoding="utf-8", errors="replace")
    else:
        with urllib.request.urlopen(urllib.request.Request(ARCHIVES, headers={"User-Agent": "Mozilla/5.0 (KTS 5.0 portal)"}), timeout=60) as r:
            page = r.read().decode("utf-8", errors="replace")
    figures = {"as_of": date.today().isoformat(), "audio_hours": audio_hours(),
               "archives": {"url": ARCHIVES, **archives_figures(page)}}
    OUT.write_text(json.dumps(figures, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(figures, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)

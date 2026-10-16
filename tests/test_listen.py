"""
Hear every couplet in Tamil (version 1.2.82): a clip for each of the 1,330 couplets (static/audio/ta/0001.mp3 to 1330.mp3),
read by a computer voice, and a Listen button with each couplet: on its own page, in the chapters of the Kural browser,
on the 108 page, with the daily couplet and the couplet of the day on the home page. Every page with the player says that
the voice is a computer's, in every language; the script plays the clip from the portal itself, with no media element in
the templates and no script in the page.

    python -m pytest tests -q
"""
import re
from pathlib import Path

from markupsafe import escape

from conftest import make_app

ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "static" / "audio" / "ta"
SCRIPT = (ROOT / "static" / "js" / "portal.js").read_text(encoding="utf-8")


def _client():
    return make_app(ADMIN_PASSWORD=None).test_client()


def _buttons(page):
    return [int(n) for n in re.findall(r'data-listen="/static/audio/ta/(\d{4})\.mp3"', page)]


def test_a_clip_for_every_couplet():
    clips = sorted(p.name for p in AUDIO.iterdir())
    assert clips == [f"{n:04d}.mp3" for n in range(1, 1331)]
    for p in AUDIO.iterdir():
        head = p.read_bytes()[:3]
        # an MP3 file: a tag, or a frame of sound at once
        assert head == b"ID3" or (head[0] == 0xFF and head[1] & 0xE0 == 0xE0), p.name
        assert 15_000 < p.stat().st_size < 60_000, p.name


def test_the_clip_is_served_by_the_portal():
    client = _client()
    r = client.get("/static/audio/ta/0001.mp3")
    assert r.status_code == 200 and r.mimetype == "audio/mpeg"
    assert r.data == (AUDIO / "0001.mp3").read_bytes()
    r.close()
    # a part of it, as a browser asks for it
    r = client.get("/static/audio/ta/1330.mp3", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.data) == 100
    r.close()


def test_the_page_of_a_couplet_in_every_language():
    from kts.i18n import CATALOG
    client = _client()
    for code, catalogue in CATALOG.items():
        page = client.get(f"/thirukkural/1?lang={code}").get_data(as_text=True)
        assert _buttons(page) == [1], code
        bar = page[page.index('<div class="listen-bar no-print">'):]
        bar = bar[:bar.index("</div>")]
        assert (f'data-play="{escape(catalogue["kural.listen"])}" data-pause="{escape(catalogue["kural.pause"])}">'
                f'<span class="ico" aria-hidden="true">🔊</span><span class="lbl">{escape(catalogue["kural.listen"])}</span></button>') in bar, code
        assert f'data-slower aria-pressed="false">{escape(catalogue["kural.slower"])}</button>' in bar, code
        assert f'<span class="listen-note small muted">{escape(catalogue["kural.voice_note"])}</span>' in bar, code
    # the button follows the couplet
    page = client.get("/thirukkural/1330?lang=en").get_data(as_text=True)
    assert _buttons(page) == [1330]
    assert page.index('<div class="big-kural ta couplet"') < page.index("data-listen=") < page.index("The Tamil is read by a computer voice.")


def test_the_chapters_and_the_108_couplets():
    from kts import kural as K
    client = _client()
    for ch in (1, 38, 133):
        page = client.get(f"/thirukkural?ch={ch}&lang=en").get_data(as_text=True)
        assert _buttons(page) == list(range(ch * 10 - 9, ch * 10 + 1)), ch
        assert page.count("The Tamil is read by a computer voice.") == 1 and page.count("data-slower") == 1
        # a small round button under the number of the couplet, named with the number for a screen reader
        n = ch * 10
        assert (f'<button class="btn sm listen-icon listen-btn no-print" type="button" data-listen="/static/audio/ta/{n:04d}.mp3" '
                f'data-play="Listen" data-pause="Pause" title="Listen · {n}"><span class="ico" aria-hidden="true">🔊</span>'
                f'<span class="lbl visually-hidden">Listen · {n}</span></button></div>') in page
    page = client.get("/thirukkural-108?lang=hi").get_data(as_text=True)
    numbers = _buttons(page)
    assert len(numbers) == 108 and numbers == sorted(numbers)
    assert all(K.kural(n)["adhigaram"] == i + 1 for i, n in enumerate(numbers))
    assert page.count(str(escape("तमिल पाठ कंप्यूटर की आवाज़ में पढ़ा जाता है।"))) == 1


def test_the_daily_couplet_and_the_couplet_of_the_day():
    import datetime

    from kts import kural as K
    client = _client()
    page = client.get("/daily-kural?d=2026-10-16&lang=ta").get_data(as_text=True)
    assert _buttons(page) == [K.daily(datetime.date(2026, 10, 16))["n"]]
    assert "தமிழ்க் குறளை வாசிப்பது கணினிக் குரல்." in page
    page = client.get("/?lang=en").get_data(as_text=True)
    card = page[page.index('<aside class="kural-card">'):]
    card = card[:card.index("</aside>")]
    n = int(re.search(r'href="/thirukkural/(\d+)"', card).group(1))
    assert _buttons(card) == [n] and _buttons(page) == [n]
    assert "The Tamil is read by a computer voice." in card


def test_no_media_element_and_no_script_in_the_page():
    client = _client()
    for path in ("/thirukkural/7", "/thirukkural?ch=2", "/thirukkural-108", "/daily-kural", "/"):
        page = client.get(path + ("&" if "?" in path else "?") + "lang=en").get_data(as_text=True)
        for gone in ("<audio", "<video", "onclick", "<script>"):
            assert gone not in page, (path, gone)


def test_the_script_plays_one_couplet_at_a_time():
    block = SCRIPT[SCRIPT.index("// Hear the couplet in Tamil (1.2.82)"):SCRIPT.index("// The Back button (1.2.77)")]
    assert 'document.querySelectorAll("[data-listen]")' in block
    assert 'new Audio(b.getAttribute("data-listen"))' in block
    assert "if (audio) audio.pause();" in block                         # another couplet stops the first
    assert "audio.playbackRate = slow ? 0.75 : 1;" in block              # slower: three quarters of the speed
    for event in ("playing", "pause", "ended", "error"):
        assert f'a.addEventListener("{event}"' in block
    assert 'x.setAttribute("aria-pressed", slow ? "true" : "false")' in block


def test_the_player_is_left_out_of_print():
    styles = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    assert ".no-print" in styles[styles.index("@media print {"):]
    page = _client().get("/thirukkural/5?lang=en").get_data(as_text=True)
    assert all("no-print" in tag for tag in re.findall(r"<button[^>]*data-(?:listen|slower)[^>]*>", page))
    assert '<div class="listen-bar no-print">' in page


def test_a_couplet_in_a_list_does_not_widen_the_page():
    # the column of the couplet may be narrower than its lines, so that the script makes the couplet smaller to fit a
    # phone (1.2.58) instead of the page growing sideways
    styles = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    assert ".kural-row > * { min-width: 0; }" in styles

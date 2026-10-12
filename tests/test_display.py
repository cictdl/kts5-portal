"""
Live banners for screens (version 1.2.61): full-screen pages that show the time of the portal, a couplet that
changes on a schedule (the same on every screen at the same moment) and the countdown to Kashi Tamil Sangamam
5.0; now.json gives the time and the couplet of the moment.

    python -m pytest tests -q
"""
import re

import pytest

from conftest import make_app

KINDS = ("welcome", "kural", "languages", "platform", "countdown", "thanks", "metro", "bus", "busstand")


@pytest.fixture(scope="module")
def client():
    return make_app(ADMIN_PASSWORD=None).test_client()


def test_the_couplet_of_the_moment_is_the_same_everywhere_and_changes_on_schedule():
    from kts import display
    opts = {"every": 15, "local": "", "n": 0}
    t = 1_791_800_000                                    # a moment in October 2026
    n1, slot1, left1 = display.moment("kural", opts, t)
    assert display.moment("kural", opts, t + 1)[0] == n1 and 0 < left1 <= 900
    n2, slot2, _ = display.moment("kural", opts, t + left1 + 1)
    assert slot2 == slot1 + 1 and n2 != n1
    # each banner draws from its own chapter
    for kind, chapter in (("welcome", range(81, 91)), ("platform", range(481, 491)), ("thanks", range(101, 111)),
                          ("countdown", range(391, 401)),
                          # metro trains and buses (1.2.63): chapters 62, 60, 67, 63; 16, 100, 10, 22; 54, 47
                          ("metro", [*range(611, 621), *range(591, 601), *range(661, 671), *range(621, 631)]),
                          ("bus", [*range(151, 161), *range(991, 1001), *range(91, 101), *range(211, 221)]),
                          ("busstand", [*range(531, 541), *range(461, 471)])):
        seen = {display.moment(kind, opts, t + i * 900)[0] for i in range(40)}
        assert seen == set(chapter), kind
    # all 1,330 couplets, each once in a round
    assert sorted(display.pool("kural")) == list(range(1, 1331))
    # a fixed couplet
    assert display.moment("kural", {"every": 15, "local": "", "n": 391}, t)[0] == 391


def test_the_options_of_a_link():
    from kts import display
    assert display.options("kural", {}) == {"every": 15, "local": "", "n": 0}
    assert display.options("metro", {}) == {"every": 5, "local": "", "n": 0} and display.options("busstand", {})["every"] == 10
    assert display.options("welcome", {"every": "999", "local": "bn", "n": "84"}) == {"every": 60, "local": "bn", "n": 84}
    assert display.options("kural", {"every": "x", "local": "hi", "n": "5000"}) == {"every": 15, "local": "", "n": 1330}


@pytest.mark.parametrize("kind", KINDS)
def test_every_banner_shows_the_time_and_a_couplet(client, kind):
    r = client.get(f"/display/{kind}")
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    assert '<link rel="stylesheet" href="/static/css/display.css?v=3">' in page and '<script src="/static/js/display.js?v=3" defer>' in page
    assert not re.search(r"<script>|onclick=", page)                 # the portal's policy: no inline script
    assert 'id="clock"' in page and "IST" in page and f'data-now="/display/now.json?kind={kind}' in page
    m = re.search(r'<p class="couplet" lang="ta" id="k-ta"><span>([^<]+)</span><span>([^<]+)</span></p>', page)
    assert m and [len(x.split()) for x in m.groups()] == [4, 3]
    assert 'class="qr-box"' in page and "kts.cict.in" in page
    # the logos of the Government of India, the Ministry of Education, CICT and Kashi Tamil Sangamam
    strip = page.split('class="logos-strip"')[1].split("</div>")[0]
    assert [s for s in ("img/logos/goi.png", "img/logos/moe.png", "img/cict-logo.png", "img/kts-logo.png") if s in strip] == [
        "img/logos/goi.png", "img/logos/moe.png", "img/cict-logo.png", "img/kts-logo.png"]
    # a screen's player may show it in a frame of its own; nothing is cached
    assert "X-Frame-Options" not in r.headers and "frame-ancestors *" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "no-store"


def test_the_banners_say_what_they_are(client):
    assert 'id="hand-s"' in client.get("/display/platform").get_data(as_text=True)
    count = client.get("/display/countdown").get_data(as_text=True)
    assert 'data-kts-start="2026-11-28T00:00:00+05:30"' in count and 'data-kts-end="2026-12-12"' in count
    assert "28 Nov – 12 Dec 2026" in count and 'data-u="d"' in count
    langs = client.get("/display/languages").get_data(as_text=True)
    assert langs.count('class="stream') == 22 and 'data-code="hi"' in langs and 'data-code="ur"' in langs and 'dir="rtl"' in langs
    local = client.get("/display/kural?local=bn&n=396").get_data(as_text=True)
    assert 'id="k-local"' in local and 'lang="bn"' in local and 'data-n="396"' in local
    assert "தொட்டனைத் தூறும் மணற்கேணி மாந்தர்க்குக்" in local
    assert client.get("/display/nothing").status_code == 404


def test_now_json_gives_the_time_and_the_couplet(client):
    import time
    before = time.time() * 1000
    r = client.get("/display/now.json?kind=welcome&every=10&local=ta")
    data = r.get_json()
    assert r.headers["Cache-Control"] == "no-store" and "X-Frame-Options" in r.headers
    assert before - 1000 <= data["epoch_ms"] <= time.time() * 1000 + 1000
    assert 0 < data["next_ms"] <= 600_000 and 81 <= data["kural"]["n"] <= 90
    k = data["kural"]
    assert len(k["ta"]) == 2 and k["hi"] and k["en"] and k["local"] is None and k["url"].endswith(f"/thirukkural/{k['n']}")
    langs = client.get("/display/now.json?kind=languages").get_json()["kural"]
    assert len(langs["streams"]) == 22
    assert client.get("/display/now.json?kind=other").status_code == 404


def test_the_page_of_links_and_the_programme(client):
    page = client.get("/display?lang=en").get_data(as_text=True)
    assert "Live banners for screens" in page and "X-Frame-Options" in client.get("/display").headers
    for kind in KINDS:
        assert f'data-base="http://localhost:8905/display/{kind}"' in page or f'/display/{kind}"' in page
    assert page.count("data-display-link") == 9 and page.count("data-copy") == 9
    # by where they are shown (1.2.63)
    assert page.index('id="for-air"') < page.index('id="welcome"') < page.index('id="for-metro"') < page.index('id="metro"')         < page.index('id="for-bus"') < page.index('id="bus"') < page.index('id="busstand"')
    assert "Metro trains" in page and "Bus transport" in page and "Kural Metro" in page and "Kural departures" in page
    assert '<option value="bn">' in page and '<option value="hi">' not in page
    programme = client.get("/programme?lang=en").get_data(as_text=True)
    assert programme.count('href="/display">📺 Live banners for screens</a>') == 2


def test_the_metro_line_the_bus_board_and_the_departures(client):
    """Metro: a chapter is a line, its ten couplets the stations; bus: a destination board; bus stand: departures (1.2.63)."""
    page = client.get("/display/metro").get_data(as_text=True)
    n = int(re.search(r'data-n="(\d+)"', page).group(1))
    chapter = (n + 9) // 10
    assert f'data-line="{chapter}"' in page and f'id="line-badge">{chapter}<' in page
    stations = re.findall(r'<li class="(past|here|ahead)"><i></i><b>(\d+)</b></li>', page)
    assert [int(s) for _, s in stations] == list(range(chapter * 10 - 9, chapter * 10 + 1))
    assert [c for c, s in stations if int(s) == n] == ["here"] and all((c == "past") == (int(s) < n) for c, s in stations)
    bus = client.get("/display/bus").get_data(as_text=True)
    assert '<div class="led-route">1330</div>' in bus and "KASHI" in bus and 'id="bus-days"' in bus
    stand = client.get("/display/busstand").get_data(as_text=True)
    rows = re.findall(r'<span class="t" dir="ltr">(\d\d:\d\d)</span><span class="n" dir="ltr">(\d+)</span>', stand)
    assert len(rows) == 5 and rows[0][1] == re.search(r'data-n="(\d+)"', stand).group(1)
    assert stand.count("board-row now") == 1 and stand.count("board-row soon") == 1
    data = client.get("/display/now.json?kind=busstand").get_json()
    board = data["board"]
    assert len(board) == 5 and board[0]["n"] == data["kural"]["n"]
    assert {b["at_ms"] - a["at_ms"] for a, b in zip(board, board[1:])} == {600_000}
    assert board[0]["at_ms"] <= data["epoch_ms"] < board[1]["at_ms"]
    assert all({"n", "chapter", "chapter_ta", "chapter_en", "at_ms"} <= set(b) for b in board)

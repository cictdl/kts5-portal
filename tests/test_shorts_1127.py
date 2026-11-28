"""
The shorts of KTS 5.0 on YouTube (1.2.231). CICT, 27 November 2026: "kts5.0 2026 ministry of education add all shorts in the
youtube"; asked where: "News page + play on portal"; asked of the Kashi Tamil Sangamam channel: "Both channels"; of the covers:
"Download the covers". The 23 shorts of the Ministry of Education's channel and the 44 of the Kashi Tamil Sangamam channel: on the
Gallery (each cover plays its short in the page; nothing of YouTube before that) and on the page "KTS 5.0 in the news".

    python -m pytest tests/test_shorts_1127.py -q
"""
import json
import re
from html import unescape

from conftest import ROOT, make_app
from test_reserve_1111 import LANGS

SHORTS = json.loads((ROOT / "data" / "shorts.json").read_text(encoding="utf-8"))
NEWS = json.loads((ROOT / "data" / "news.json").read_text(encoding="utf-8"))
MERGED = {"ktsangamam-2026-10-15-pm-reel": "u_WUxGSUFzY", "social-2026-10-22-08": "nlJ8vl1OPhU", "social-2026-10-28-15": "wo3Bi484Alg",
          "social-2026-10-29-16": "IrhZDS9yvHU", "social-2026-11-01-19": "k5ApJUWHuic", "social-2026-11-01-20": "HdQLq2EuUq4"}


def test_the_67_shorts_and_their_covers():
    from PIL import Image
    assert len(SHORTS) == 67 and len({s["id"] for s in SHORTS}) == 67
    assert [s["channel"] for s in SHORTS] == ["moe"] * 23 + ["kts"] * 44                   # the Ministry's first
    for channel in ("moe", "kts"):
        days = [(s["date"], s["time"]) for s in SHORTS if s["channel"] == channel]
        assert days == sorted(days, reverse=True), channel                                 # newest first
    assert min(s["date"] for s in SHORTS) == "2026-10-15" and max(s["date"] for s in SHORTS) <= "2026-11-27"
    for s in SHORTS:
        assert set(s) == {"id", "channel", "date", "time", "seconds", "title", "lang"} and re.fullmatch(r"[A-Za-z0-9_-]{11}", s["id"])
        assert re.fullmatch(r"[012]\d:[0-5]\d", s["time"])
        assert 0 < s["seconds"] <= 180 and s["title"] == s["title"].strip() and s["lang"] in ("en", "hi")
        assert not re.search("[\U0001D400-\U0001D7FF]", s["title"])                       # the bold letters of YouTube made plain
        assert (s["lang"] == "hi") == bool(re.search(r"[ऀ-ॿ]", s["title"]))
        path = ROOT / "static" / "img" / "shorts" / f"{s['id']}.webp"
        data = path.read_bytes()
        assert data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) < 60_000 and b"EXIF" not in data and b"XMP " not in data
        with Image.open(path) as im:
            assert im.size == (270, 480)
    assert sorted(p.stem for p in (ROOT / "static" / "img" / "shorts").glob("*")) == sorted(s["id"] for s in SHORTS)
    assert "KTS 5.0" in " ".join(s["title"] for s in SHORTS) and "Thirukkural" in " ".join(s["title"] for s in SHORTS)


def test_the_page_of_the_shorts():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    r = client.get("/gallery/shorts?lang=en")
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    main = page[page.index("<main"):page.index("</main>")]
    assert "<title>KTS 5.0 shorts on YouTube" in page and '<h2 class="gv-h" id="shorts-h"><span aria-hidden="true">▶</span> KTS 5.0 shorts on YouTube</h2>' in main
    # the tab of the shorts is the one shown; the tabs of the albums are there
    tabs = main[main.index('<div class="res-tabs">'):main.index("</div>", main.index('<div class="res-tabs">'))]
    assert re.search(r'<a href="/gallery/shorts" class="on"><span aria-hidden="true">▶ </span>KTS 5.0 shorts on YouTube <span class="muted">67</span></a>', tabs)
    assert '<a href="/gallery" class="">All albums</a>' in tabs
    # the two channels, the Ministry's first, each with its count and its shorts newest first
    heads = re.findall(r'<h3 id="shorts-(moe|kts)-h"[^>]*><span lang="en" dir="ltr">([^<]+)</span>.*?<bdi>(\d+) shorts</bdi>', main)
    assert heads == [("moe", "Ministry of Education, Government of India", "23"), ("kts", "Kashi Tamil Sangamam", "44")]
    assert 'href="https://www.youtube.com/@Eduminofindia/shorts"' in main and 'href="https://www.youtube.com/@KashiTamilSangamam/shorts"' in main
    ids = re.findall(r'data-yt="([A-Za-z0-9_-]{11})"', main)
    assert ids == [s["id"] for s in SHORTS]
    for s in SHORTS:
        assert f'<img src="/static/img/shorts/{s["id"]}.webp" alt="" width="270" height="480" loading="lazy">' in main
        assert main.count(f'href="https://www.youtube.com/shorts/{s["id"]}"') == 2                       # the cover and "Watch on YouTube"
    hindi = next(s for s in SHORTS if s["lang"] == "hi")
    assert f'<span class="gv-name" lang="hi" dir="auto">{hindi["title"]}</span>' in unescape(main)
    assert f'<a class="gv-poster" lang="hi" href="https://www.youtube.com/shorts/{hindi["id"]}"' in main          # its name in its language
    assert '<a href="/gallery" class="active">' in page                                                       # the menu: the Gallery
    # nothing of YouTube loads with the page: no frame, no script, no picture of theirs
    assert "<iframe" not in page and "youtube-nocookie" not in page and "ytimg" not in page and "youtube.com/embed" not in page
    assert "photo-grid" not in main
    csp = r.headers["Content-Security-Policy"]
    assert "img-src 'self' data:;" in csp and "https://www.youtube-nocookie.com" in csp


def test_the_six_latest_on_the_gallery():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/gallery?lang=en").get_data(as_text=True)
    main = page[page.index("<main"):page.index("</main>")]
    strip = main[main.index('<section class="gv-block sh-block sh-strip"'):main.index("</section>", main.index('<section class="gv-block sh-block sh-strip"'))]
    latest = sorted(SHORTS, key=lambda s: (s["date"], s["time"]), reverse=True)[:6]      # by the day and the hour, whichever channel
    assert {s["channel"] for s in latest} == {"moe", "kts"}
    assert re.findall(r'data-yt="([A-Za-z0-9_-]{11})"', strip) == [s["id"] for s in latest]
    assert '<a href="/gallery/shorts">All 67 shorts →</a>' in strip
    assert main.index("sh-strip") < main.index("photo-grid")                              # above the photographs
    assert page.count('<figure class="photo">') == 33 and "33 photographs" in page          # the photographs as they were
    album = client.get("/gallery?lang=en&album=KTS+5.0+in+the+news").get_data(as_text=True)
    assert "sh-strip" not in album and 'href="/gallery/shorts"' in album                    # an album: the tab only


def test_the_news_page():
    ids = {s["id"] for s in SHORTS}
    cards = [x for x in NEWS if any(l.get("url", "").rsplit("/", 1)[-1] in ids for l in x.get("links", []))]
    new = [x for x in cards if x["key"] not in MERGED]
    assert len(NEWS) == 163 and len(new) == 61 and len({x["key"] for x in NEWS}) == 163        # 159: the press release of 1.2.232; 160: DD National, 1.2.234
    assert [x["date"] for x in NEWS] == sorted(x["date"] for x in NEWS)
    import datetime as dt
    for day in {x["date"] for x in new}:                                                   # each day in the order of its hours
        times = [dt.datetime.strptime(x["versions"][0]["time"], "%I:%M %p") for x in NEWS if x["date"] == day and x["versions"][0].get("time")]
        assert times == sorted(times), day
    moe = [x for x in new if x["source"] == "Ministry of Education"]
    kts = [x for x in new if x["source"] == "Kashi Tamil Sangamam"]
    assert len(moe) == 23 and len(kts) == 38 and all(x.get("gov") is True for x in moe) and not any("gov" in x for x in kts)
    for x in new:
        assert x["kind"] == "social" and re.fullmatch(r"social-2026-1[01]-\d\d-\d+", x["key"]) and x["key"].startswith(f"social-{x['date']}-")
        (link,) = x["links"]
        assert link["site"] == "YouTube" and link["kind"] == "video" and link["date"] == x["date"]
        assert link["account"] == ("Eduminofindia" if x in moe else "KashiTamilSangamam")
        assert x["versions"] == [{"lang": "en", "title": x["title"], "url": link["url"], "time": x["versions"][0]["time"]}]
        assert x["title"] and x["title"][-1] not in ".!" and "#" not in x["title"] and (x in moe) == x["title"].startswith("The Ministry of Education: ")
        assert x["quote"] and "#" not in x["quote"] and "http" not in x["quote"] and x["quote_lang"] in ("en", "hi", "ta")
        assert re.fullmatch(r"\d{1,2}:\d\d [AP]M", x["versions"][0]["time"])
    # the six posts on the page already: their YouTube link added, no second card
    for key, vid in MERGED.items():
        item = next(x for x in NEWS if x["key"] == key)
        url = f"https://www.youtube.com/shorts/{vid}"
        assert (item.get("youtube") == url) if item["kind"] == "reel" else (item["links"][-1]["url"] == url and item["links"][-1]["site"] == "YouTube")
    for s in SHORTS:                                                                       # each short on one card
        assert sum(1 for x in NEWS if f"youtube.com/shorts/{s['id']}" in json.dumps(x)) == 1, s["id"]
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/in-the-news?lang=en").get_data(as_text=True)
    for s in SHORTS:
        assert f'href="https://www.youtube.com/shorts/{s["id"]}"' in page
    assert 'lang="en" dir="ltr" title="@Eduminofindia" href="https://www.youtube.com/shorts/' in page and "YouTube ▶" in page
    reel = page[page.index('href="https://www.youtube.com/shorts/u_WUxGSUFzY"') - 300:page.index('href="https://www.youtube.com/shorts/u_WUxGSUFzY"') + 200]
    assert 'class="btn sm reel-yt"' in reel and "Watch on YouTube" in reel


def test_the_four_texts_in_23_languages():
    from kts.i18n import CATALOG
    en = CATALOG["en"]
    assert en["sh.title"] == "KTS 5.0 shorts on YouTube" and en["sh.count"] == "{n} shorts" and en["sh.all"] == "All {n} shorts"
    assert en["sh.lead"].startswith("Short videos of Kashi Tamil Sangamam 5.0 from the YouTube channels of the Ministry of Education")
    assert sorted(CATALOG) == sorted(LANGS) and len(en) == 1557
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for code in LANGS:
        c = CATALOG[code]
        keys = list(c)
        assert keys[keys.index("gallery.back") + 1:][:4] == ["sh.title", "sh.lead", "sh.count", "sh.all"], code
        assert c["sh.count"].count("{n}") == 1 and c["sh.all"].count("{n}") == 1 and "▶" in c["sh.lead"], code
        assert "{" not in c["sh.title"] + c["sh.lead"] and c["sh.title"][-1] not in ".।॥؟۔", code
        assert code == "en" or all(c[k] != en[k] for k in ("sh.title", "sh.lead")), code
        page = client.get(f"/gallery/shorts?lang={code}").get_data(as_text=True)
        assert unescape(c["sh.title"]) in unescape(page) and unescape(c["sh.count"].replace("{n}", "23")) in unescape(page), code

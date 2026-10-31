"""
The video guide to the portal (version 1.2.128): four videos on CICT's YouTube channel, each shown by a poster kept on the
portal and played in the page, in YouTube's no-cookie player, when pressed (or opened on YouTube); all four under the hero of the home page and in the Digital repository, each part where its
readers are (Nodal Officers, institutions, students).

    python -m pytest tests -q
"""
import json
import re

from PIL import Image

from conftest import ROOT, make_app

DATA = json.loads((ROOT / "data" / "guide_videos.json").read_text(encoding="utf-8"))
IDS = {1: "V3JtCOfqIzo", 2: "Xmtf4A6oH7U", 3: "CxoeFOP-xBg", 4: "gYW8YlyL2Ro"}


def _url(n):
    return f"https://www.youtube.com/watch?v={IDS[n]}"


def _page(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def _parts(html):
    """The parts whose videos a piece of a page links to, in order."""
    return [n for vid in re.findall(r'<a class="gv-poster" href="https://www\.youtube\.com/watch\?v=([\w-]{11})" target="_blank" '
                                    r'rel="noopener" data-yt="\1"', html)
            for n, i in IDS.items() if i == vid]


def test_the_four_videos_and_their_posters():
    assert DATA["channel"] == "https://www.youtube.com/@CICT_Online"
    assert [(v["n"], v["youtube"]) for v in DATA["videos"]] == sorted(IDS.items())
    assert [v["duration"] for v in DATA["videos"]] == ["13:23", "11:55", "13:41", "12:39"]
    for v in DATA["videos"]:
        path = ROOT / "static" / v["poster"]
        assert path.stat().st_size < 40_000, path
        with Image.open(path) as im:
            assert im.format == "JPEG" and im.size == (640, 360), path


def test_the_home_page_has_all_four_under_the_hero():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = _page(client, "/?lang=en")
    hero = page[page.index('<section class="hero">'):page.index('<section class="hero">') + page[page.index('<section class="hero">'):].index("</section>")]
    assert '<a class="btn gv-btn" href="#video-guide"><span aria-hidden="true">▶</span> Video guide</a>' in hero
    block = page[page.index('id="video-guide"'):]
    block = block[:block.index("</section>")]
    assert '<h2 class="gv-h" id="video-guide-h"><span aria-hidden="true">▶</span> Video guide to the KTS 5.0 portal</h2>' in block
    assert _parts(block) == [1, 2, 3, 4]
    for n in IDS:
        assert f'<img src="/static/img/guide-video/kts5-guide-part{n}.jpg" alt="" width="640" height="360" loading="lazy">' in block
    # each poster plays its video, and its "Watch on YouTube" opens it there
    assert block.count('target="_blank" rel="noopener"') == 8 and block.count('class="gv-watch"') == 4
    for name in ("Part 1: For Nodal Officers", "Part 2: For Participating Institutions", "Part 3: For Students",
                 "Part 4: The resources of the portal"):
        assert name in block
    # right under the hero, before anything else of the page
    assert page.index('<section class="hero">') < page.index('id="video-guide"') < page.index('<section class="section')
    # nothing of YouTube enters the portal: no player, no pictures of YouTube, no tracking parameter
    # nothing of YouTube loads with the page: no player before a poster is pressed, no pictures of YouTube
    assert "youtube.com/embed" not in page and "ytimg" not in page and "<iframe" not in page
    assert not re.search(r'href="https://www\.youtube\.com/watch\?v=[\w-]{11}[&?]', page)


def test_every_language_has_the_guide():
    from kts.i18n import CATALOG
    client = make_app(ADMIN_PASSWORD=None).test_client()
    keys = ("gv.title", "gv.short", "gv.lead", "gv.p1", "gv.p2", "gv.p3", "gv.p4", "gv.all")
    for code, catalogue in CATALOG.items():
        assert all(catalogue.get(k) for k in keys), code
        if code != "en":
            assert all(catalogue[k] != CATALOG["en"][k] for k in keys if k not in ("gv.short",)), code
        page = _page(client, f"/?lang={code}")
        assert str(__import__("markupsafe").escape(catalogue["gv.title"])) in page, code
        assert _parts(page[page.index('id="video-guide"'):])[:4] == [1, 2, 3, 4], code


def test_each_part_where_its_readers_are():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    guide = _page(client, "/how-to-take-part?lang=en")
    for part, n in (("students", 3), ("institutions", 2), ("nodal", 1)):
        start = guide.index(f'<section id="{part}"')
        section = guide[start:guide.index("</section>", start)]
        assert _parts(section) == [n], part
        assert '<a href="/#video-guide">All four videos →</a>' in section
    assert _parts(_page(client, "/how-to-take-part/institutions?lang=en")) == [2]
    assert _parts(_page(client, "/register?lang=en")) == [3]
    assert _parts(_page(client, "/institutions/register?lang=en")) == [2]
    assert _parts(_page(client, "/institution/login?lang=en")) == [2]
    assert _parts(_page(client, "/nodal-institutions?lang=en")) == [1]
    assert _parts(_page(client, "/resources?lang=en")) == [1, 2, 3, 4]
    console = _page(client, "/console/login")
    assert f'<a href="{_url(1)}" target="_blank" rel="noopener">the video guide to the Console (YouTube, 13:23)</a>' in console


def test_the_registration_closed_page_has_the_students_video():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("reg.open", "0")
    page = _page(app.test_client(), "/register?lang=en")
    assert _parts(page) == [3]


def test_the_player_and_the_policy():
    # the policy allows pictures of the portal only, and as a frame YouTube's no-cookie player only
    client = make_app(ADMIN_PASSWORD=None).test_client()
    policy = client.get("/?lang=en").headers["Content-Security-Policy"]
    assert "img-src 'self' data:;" in policy and "frame-src https://www.youtube-nocookie.com;" in policy
    assert policy.count("youtube") == 1
    js = (ROOT / "static" / "js" / "portal.js").read_text(encoding="utf-8")
    assert 'document.querySelectorAll("a[data-yt]")' in js and '"https://www.youtube-nocookie.com/embed/" + id + "?autoplay=1&rel=0"' in js
    assert "/^[A-Za-z0-9_-]{11}$/.test(id)" in js and 'f.referrerPolicy = "strict-origin-when-cross-origin"' in js
    page = _page(client, "/?lang=en")
    assert "/static/js/portal.js?v=21" in page

"""
"KTS 5.0 in numbers" (version 1.2.129): the banner of figures on the home page, under the video guide: what the portal
holds (counted from its own files at each start) and the headline figures of CICT's Digital Archives (data/figures.json,
tools/update_figures.py), each figure a link, the figures counting up as they come into view.

    python -m pytest tests -q
"""
import json
import re

from markupsafe import escape

from conftest import ROOT, make_app

FIGURES = json.loads((ROOT / "data" / "figures.json").read_text(encoding="utf-8"))


def _page(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def _band(page):
    start = page.index('<section class="numbers"')
    return page[start:page.index("</section>", start)]


def _tiles(band):
    """[(href, number, label)] of the tiles of the band, in order."""
    return re.findall(r'<a class="num-tile[^"]*" href="([^"]+)"[^>]*>.*?<b class="num-n"[^>]*data-count="(\d+)"[^>]*>.*?'
                      r'<span class="num-l">([^<]*)</span>', band, re.S)


def test_the_figures_are_counted_from_the_portal_itself():
    from kts import public
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        f = public.portal_figures()
    assert f["langs"] == 23 and f["kurals"] == 1330 and f["versions"] == 29
    assert f["audio"] == 1330 + 29 and f["audio_hours"] == FIGURES["audio_hours"] > 7
    # the orientation lectures, the videos of the repository, the reels and shorts and the video guide
    assert f["videos"] >= 28 + 138 + 47 + 4 and f["video_parts"] == {"lectures": 28, "repository": 138, "reels": 47, "guide": 4}
    assert f["books"] == 11 and f["posters"] == 92 and f["events"] >= 253
    assert f["archives"] == FIGURES["archives"]
    assert FIGURES["archives"]["bundles"] == 865 and FIGURES["archives"]["gt_specimens"] == 133
    assert FIGURES["archives"]["audio_lexicon_entries"] == 59170 and FIGURES["archives"]["citations"] == 275262


def test_the_banner_on_the_home_page():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = _page(client, "/?lang=en")
    band = _band(page)
    # under the video guide, before the rest of the page
    assert page.index('id="video-guide"') < page.index('<section class="numbers"') < page.index("launch-video") if "launch-video" in page \
        else page.index('id="video-guide"') < page.index('<section class="numbers"')
    assert '<h2 class="num-h" id="numbers-h">KTS 5.0 in numbers</h2>' in band
    tiles = _tiles(band)
    labels = [t[2] for t in tiles]
    assert labels[:8] == ["Languages of the portal", "Thirukkural couplets", "Audio recordings", "Videos",
                          "Languages of the study book", "Posters", "Seminars and workshops of CICT", "Visitors to the portal"]
    # the Digital repository (1.2.130): its items, its six fullest categories, the lectures, the reels, the gallery
    assert labels[8:18] == ["Items in the repository", "Thiruvalluvar videos", "Thirukkural in sign language", "Thirukkural videos",
                            "PM eVidya CICT - Tamil", "Apps", "Music", "Orientation lectures", "Reels and shorts",
                            "Photographs in the gallery"]
    assert labels[18:] == ["Manuscript bundles", "Palm leaves", "Classical Tamil texts", "Source institutions",
                           "Tirukkural ground-truth specimens", "Lexical tools", "Lexical words indexed", "Citations documented",
                           "Lexicon entries", "Tamil Audio Lexicon entries"]
    numbers = [int(t[1]) for t in tiles]
    assert numbers[:7] == [23, 1330, 1359, numbers[3], 11, 92, numbers[6]] and numbers[3] >= 217 and numbers[6] >= 253
    assert numbers[8:18] == [156, 57, 44, 22, 15, 7, 6, 28, 47, 9]
    assert numbers[18:] == [865, 100000, 41, 15, 133, 17, 108655, 275262, 6758, 59170]
    hrefs = [t[0] for t in tiles]
    assert hrefs[:8] == ["/about", "/thirukkural", "/thirukkural", "/resources", "/syllabus", "/posters",
                         "/seminars-workshops", "/dashboard"]
    assert hrefs[8:18] == ["/resources", "/resources?cat=video_valluvar", "/resources?cat=video_sign", "/resources?cat=video_kural",
                           "/resources?cat=video_pmevidya", "/resources?cat=app", "/resources?cat=music", "/orientation",
                           "/programme#reels", "/gallery"]
    assert all(h.startswith("https://www.digitalarchives.cict.in/") for h in hrefs[18:]) and len(set(hrefs[18:])) >= 4
    assert "in 9 categories" in band and "in 14 languages" in band and "in 27 languages" in band
    assert '<h3 class="num-h3" id="numbers-res-h">Digital repository</h3>' in band
    assert band.index('id="numbers-res-h"') < band.index('id="numbers-da-h"')
    # the sub-lines
    assert "in 22 languages · 29 versions" in band and "7.8 hours of Tamil" in band and "4 designs in 23 languages" in band
    assert "since 2020" in band and "lectures, films, reels and shorts" in band
    assert "55,831 headwords · 5,547 of Sanskrit origin" in band
    # the archives' group, its link and the date of its figures
    assert '<h3 class="num-h3" id="numbers-da-h">CICT Digital Archives</h3>' in band
    assert ('<a class="btn saffron num-visit" href="https://www.digitalarchives.cict.in/" target="_blank" rel="noopener">'
            "Open the Digital Archives") in band
    assert "Figures as on 31 Oct 2026" in band or re.search(r"Figures as on \d\d \w{3} \d{4}", band)
    # the figures stand in their own direction, and the numbers count up (the figure itself is written for those without
    # scripts and for the search engines)
    assert band.count('<b class="num-n" dir="ltr" data-count=') == 28 and ">1,330<" in band and ">1,00,000<" in band
    assert ">1,08,655<" in band and ">2,75,262<" in band
    # nothing of the archives is loaded: the links open it, no picture or frame of it
    assert "digitalarchives.cict.in/" not in re.sub(r'href="[^"]*"', "", band)


def test_the_banner_in_every_language_and_its_social_links():
    from kts.i18n import CATALOG
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for code, catalogue in CATALOG.items():
        page = _page(client, f"/?lang={code}")
        band = _band(page)
        assert str(escape(catalogue["num.title"])) in band and str(escape(catalogue["num.da_title"])) in band, code
        assert len(_tiles(band)) == 28, code
        if code != "en":
            assert catalogue["num.kurals"] != CATALOG["en"]["num.kurals"], code
        for key in ("num.kurals_sub", "num.audio_sub", "num.visitors_sub", "num.as_of", "num.audio_lex_sub", "num.res_items_sub",
                    "num.in_langs"):
            left = str(escape(catalogue[key]))
            for ph in ("{n}", "{h}", "{today}", "{date}", "{a}", "{b}"):
                left = left.replace(ph, "")
            assert "{" not in left, (code, key)
        assert "{" not in band, code  # every placeholder of the banner is filled in
    # CICT's social media, as the footer has them
    band = _band(_page(client, "/?lang=en"))
    assert 'href="https://x.com/cictofficial"' in band and 'href="https://facebook.com/chennaicict"' in band


def test_the_repository_is_counted_as_it_stands():
    # an item added in the Console is counted at the next view; a category that empties loses its tile; a gallery without
    # photographs has no tile
    from kts.db import execute
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    with app.app_context():
        execute("INSERT INTO resources(title, description, category, lang, url, featured, sort_order, published, created_at, updated_at) "
                "VALUES('Added in the Console', '', 'music', 'ta', 'https://example.org/x', 0, 999, 1, '2026-10-31T00:00:00', "
                "'2026-10-31T00:00:00')")
        execute("UPDATE resources SET published = 0 WHERE category = 'app'")
        execute("UPDATE gallery_photos SET published = 0")
    band = _band(_page(client, "/?lang=en"))
    tiles = _tiles(band)
    labels = [t[2] for t in tiles]
    assert "Apps" not in labels and "Photographs in the gallery" not in labels
    assert [t for t in tiles if t[2] == "Music"][0][1] == "7" and [t for t in tiles if t[2] == "Items in the repository"][0][1] == "150"
    assert "in 8 categories" in band and len(tiles) == 27


def test_visitors_are_live_and_the_dashboard_tile_follows_the_setting():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    band = _band(_page(client, "/?lang=en"))
    m = re.search(r'href="/dashboard"[^>]*>.*?data-count="(\d+)".*?<span class="num-s">(\d[\d,]*) today</span>', band, re.S)
    assert m, band[:400]
    with app.app_context():
        set_setting("dashboard.public", "0")
    band = _band(_page(client, "/?lang=en"))
    assert 'href="/dashboard"' not in band and 'class="num-tile num-live"' in band  # the visitors stay, as a figure alone


def test_the_script_counts_up_and_respects_reduced_motion():
    js = (ROOT / "static" / "js" / "portal.js").read_text(encoding="utf-8")
    assert 'document.querySelectorAll("[data-count]")' in js and "IntersectionObserver" in js
    assert "prefers-reduced-motion: reduce" in js and 'Intl.NumberFormat("en-IN")' in js
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    assert ".numbers" in css and ".num-tile" in css and "@media (max-width: 599px)" in css

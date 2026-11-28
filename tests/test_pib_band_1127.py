"""
The press release of the Ministry of Education of 27 November 2026, linked on the home page (1.2.232). CICT, 27 November 2026:
"Link on the Home page: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2342468&reg=48&lang=1&v=sd" - PIB Delhi, 1:58 PM:
"Vice-President Shri C. P. Radhakrishnan to inaugurate the fifth edition of Kashi Tamil Sangamam 5.0". A band of its own at the top
of the home page - deep blue, large bold white letters, a blinking NEW - that opens the release on pib.gov.in; the headline as PIB
gives it, in English, the rest in the language of the page; the Console's switch home.pib takes it off.

    python -m pytest tests/test_pib_band_1127.py -q
"""
import json
import re

from conftest import ROOT, make_app
from test_quiz_band_1125 import _contrast
from test_reserve_1111 import LANGS

URL = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2342468&reg=48&lang=1&v=sd"
TITLE = "Vice-President Shri C. P. Radhakrishnan to inaugurate the fifth edition of Kashi Tamil Sangamam 5.0"
SUBTITLE = "KTS 5.0 to be held from November 28 to December 12, 2026 in Varanasi"


def _band(page):
    if '<div class="pib-band"' not in page:
        return None
    return page[page.index('<div class="pib-band"'):page.index('<div class="nodal-attention">')]


def test_the_release():
    press = json.loads((ROOT / "data" / "home_press.json").read_text(encoding="utf-8"))
    assert press == {"date": "2026-11-27", "time": "1:58 PM", "office": "PIB Delhi", "ministry": "Ministry of Education", "title": TITLE,
                     "subtitle": SUBTITLE, "release_id": "2342468", "url": URL}


def test_the_band_on_the_home_page():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/?lang=en").get_data(as_text=True)
    band = _band(page)
    assert band is not None
    # the headline of PIB, large and bold, leading to the release itself in a new tab
    link = re.search(r'<a class="pib-link" href="([^"]+)" target="_blank" rel="noopener" lang="en" dir="ltr" style="([^"]+)">(.*?)</a>', band, flags=re.S)
    assert link and link.group(1) == URL.replace("&", "&amp;") and TITLE in link.group(3) and "↗" in link.group(3)
    assert "color:#fff;font-weight:800;font-size:1.4rem" in link.group(2)
    # what it is: a press release of the Ministry, its day; and the days of the Sangamam as the release gives them
    assert '<span aria-hidden="true">📰 </span>Press release · Ministry of Education, Government of India · <bdi>27 Nov 2026</bdi> · <span lang="en" dir="ltr">PIB Delhi</span></span>' in band
    assert f'<span class="pib-sub" lang="en" dir="ltr"' in band and SUBTITLE in band
    # deep blue, on which the white of the headline and the gold of the line above it are read with ease
    assert "background:linear-gradient(90deg,#0f2d5c,#173f7a)" in band and '<span class="new-badge">NEW</span>' in band
    assert _contrast("#ffffff", "#173f7a") > 7 and _contrast("#ffd166", "#173f7a") > 4.5
    # the keyboard sees where it is: a white outline, in the style sheet (its version 56)
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    assert ".pib-band a:focus-visible { outline: 3px solid #fff; outline-offset: 3px; border-radius: 2px; }" in css
    # its day on one line on a phone (27-11-2026 would break at a hyphen)
    assert ".pib-band .pib-from bdi { white-space: nowrap; }" in css
    assert '<link rel="stylesheet" href="/static/css/portal.css?v=57">' in page and "<style" not in page
    # first of all, above the circular band, the bands of the Academic Orientation and of the quiz, and the hero
    at = [page.index(mark) for mark in ('class="pib-band"', 'class="nodal-attention"', 'class="acad-band"', 'class="quick-links"', 'class="hero"')]
    assert at == sorted(at) and page.index('class="pib-band"') > page.index("<main")
    assert page.count('href="' + URL.replace("&", "&amp;") + '"') == 1
    # on the home page only
    assert _band(client.get("/programme?lang=en").get_data(as_text=True)) is None


def test_in_the_23_languages():
    from kts.i18n import CATALOG
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for code in LANGS:
        page = client.get(f"/?lang={code}").get_data(as_text=True)
        band = _band(page)
        assert band is not None, code
        # the headline stays as PIB gives it, in English; the rest in the language of the page
        assert TITLE in band and SUBTITLE in band, code
        # the day of the release, as the page writes days (with the marks that keep it left to right on a page from right to left)
        assert re.search("<bdi>(?:27 Nov 2026|⁦?27-11-2026⁩?)</bdi> · <span lang=\"en\" dir=\"ltr\">PIB Delhi</span>", band), code
        for key in ("news.press", "site.ministry", "circ.new"):
            assert str(CATALOG[code][key]).replace("&", "&amp;").replace("'", "&#39;") in band, (code, key)


def test_the_card_on_the_news_page():
    # CICT: "yes add in news also" - a card of its own, as the press releases before it, at its hour among the posts of its day
    import datetime as dt
    news = json.loads((ROOT / "data" / "news.json").read_text(encoding="utf-8"))
    (card,) = [n for n in news if "2342468" in json.dumps(n)]
    assert card == {"key": "pib-2026-11-27-kts5-inauguration", "date": "2026-11-27", "kind": "press", "source": "Press Information Bureau",
                    "versions": [{"lang": "en", "office": "PIB Delhi", "ministry": "Ministry of Education", "title": TITLE, "subtitle": SUBTITLE,
                                  "time": "1:58 PM", "url": "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2342468"}]}
    assert len(news) == 160 and len({n["key"] for n in news}) == 160 and [n["date"] for n in news] == sorted(n["date"] for n in news)
    times = [dt.datetime.strptime(n["versions"][0]["time"], "%I:%M %p") for n in news if n["date"] == "2026-11-27"]
    assert times == sorted(times) and len(times) >= 2
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for code in ("en", "ta", "hi", "ur"):
        page = client.get(f"/in-the-news?lang={code}").get_data(as_text=True)
        at = page.index('href="https://www.pib.gov.in/PressReleasePage.aspx?PRID=2342468"')
        block = page[page.rindex('<div class="card news-press"', 0, at):page.index("</div>", at)]
        from kts.i18n import CATALOG
        assert str(CATALOG[code]["news.press"]).replace("'", "&#39;") in block and "PIB Delhi" in block and "Ministry of Education" in block and "1:58 PM" in block, code
        assert f'<h3 style="margin:0;line-height:1.4" lang="en" dir="auto"><a href="https://www.pib.gov.in/PressReleasePage.aspx?PRID=2342468" target="_blank" rel="noopener">{TITLE}</a></h3>' in block, code
        assert SUBTITLE in block and "pib.gov.in ↗" in block, code
        # 27 November, the latest of the days, comes first, with this card in it
        assert page.index("PRID=2342468") < page.index("PRID=2339668"), code


def test_the_console_takes_it_off():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS, set_setting
    assert DEFAULT_SETTINGS["home.pib"] == "1"
    site = {k: kind for k, _label, kind in dict(SETTING_GROUPS)["Site"]}
    assert site["home.pib"] == "bool"
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    with app.app_context():
        set_setting("home.pib", "0")
    page = client.get("/?lang=en").get_data(as_text=True)
    assert _band(page) is None and "PRID=2342468" not in page and '<div class="nodal-attention">' in page
    with app.app_context():
        set_setting("home.pib", "1")
    assert _band(client.get("/?lang=en").get_data(as_text=True)) is not None


def test_without_the_file(tmp_path, monkeypatch):
    # no file, no band, no error
    from kts import public
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        assert public.home_press()["url"] == URL
        app.config["DATA_DIR"] = tmp_path
        assert public.home_press() is None
    monkeypatch.setattr(public, "home_press", lambda: None)
    r = make_app(ADMIN_PASSWORD=None).test_client().get("/?lang=en")
    assert r.status_code == 200 and _band(r.get_data(as_text=True)) is None and '<div class="nodal-attention">' in r.get_data(as_text=True)

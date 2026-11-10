"""
What CICT asked on 7 November 2026 (1.2.164): the last date beside the button of the strip; item 7 of the Programme and the
article of not more than 10 pages everywhere; the two study books to come; two figures hidden.

    python -m pytest tests/test_1107.py -q
"""
import re

from markupsafe import escape

from conftest import make_app

LIVE = {"reg.open": "0", "launch.on": "0", "hei.open": "1", "hei.start": "2026-10-22", "hei.end": "2099-11-15",
        "reg.end": "2099-11-20"}


def _app(**values):
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for key, value in {**LIVE, **values}.items():
            set_setting(key, value)
    return app


def _get(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def _strip(page):
    start = page.index('<div class="banner')
    return page[start:page.index("</div></div>", start)]


def test_the_last_date_beside_the_button():
    from kts.i18n import CATALOG
    client = _app().test_client()
    for code, cat in CATALOG.items():
        strip = _strip(_get(client, f"/?lang={code}"))
        go = strip.index('class="banner-go"')
        date = strip.index('<span class="banner-date">')
        assert go < date, code
        assert re.search(r'<span class="banner-date">' + re.escape(str(escape(cat["bank.last_date"]))) + r": <bdi>.*?</bdi></span>",
                         strip[date:]), code
    strip = _strip(_get(client, "/?lang=en"))
    assert re.search(r'<span class="banner-date">Last date: <bdi>(<bdi dir="ltr">)?15 Nov 2099', strip)
    # on every page with the strip, and only while the institutions register
    assert 'class="banner-date"' in _strip(_get(client, "/programme?lang=en"))
    closed = _app(**{"hei.end": "2020-01-01"}).test_client()
    assert 'class="banner-date"' not in _get(closed, "/?lang=en")


def test_item_7_of_the_programme():
    page = _get(_app().test_client(), "/programme?lang=en")
    assert "Student presentation and dissemination of knowledge" in page
    # the minimum of 4 pages and the college's website (1.2.167)
    for words in ("an original article or research note of at least 4 and not more than 10 pages",
                  "with a PowerPoint (PPT) or another suitable presentation", "the institution submits its video recording to CICT",
                  "The student and the institution post the news of KTS 5.0 on the student&#39;s social media and arrange for it to "
                  "appear on the college&#39;s website and social media and in the local news media."):
        assert words in page, words


def test_the_article_of_not_more_than_10_pages_everywhere():
    from kts.i18n import CATALOG
    keys = ("reg.declare_participate", "reg.cdeclare_participate", "about.p2", "prog.i7.d", "paper.card_text", "paper.f_file",
            "guide.s6", "nl.b2", "nl.art_c4")
    en = CATALOG["en"]
    for key in keys:
        assert "10 pages" in en[key] or "ten pages" in en[key], key
    for code, cat in CATALOG.items():
        for key, value in cat.items():
            assert not re.search(r"\b4\s*[–-]\s*5\b|four to five", value), (code, key)
        if code != "en":
            for key in keys:
                assert cat[key] != en[key], (code, key)
    client = _app().test_client()
    assert "write an article or research note of at least 4 and not more than 10 pages" in _get(client, "/about?lang=en")
    assert "write an article/research note of at least 4 and not more than 10 pages" in _get(client, "/how-to-take-part?lang=en")
    # the institution's page, in English
    from pathlib import Path
    home = (Path(__file__).resolve().parents[1] / "templates" / "campus" / "home.html").read_text(encoding="utf-8")
    assert "4–5" not in home and "write an article/research note of at least 4 and not more than 10 pages" in home


def test_the_two_books_to_come():
    from kts.i18n import CATALOG
    client = _app().test_client()
    page = _get(client, "/syllabus?lang=en")
    note = '<b>Konkani (Devanagari script) and Manipuri (Meitei Mayek script) content will be added soon.</b>'
    assert note in page and page.index(note) < page.index('id="books"')
    for code, cat in CATALOG.items():
        assert str(escape(cat["syl.soon"])) in _get(client, f"/syllabus?lang={code}"), code


def test_the_two_figures_are_hidden_and_come_back():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS["institutions.registered"] == "0" and DEFAULT_SETTINGS["nodal.covered"] == "0"
    site = {k: kind for k, _label, kind in dict(SETTING_GROUPS)["Site"]}
    assert site["institutions.registered"] == "bool" and site["nodal.covered"] == "bool"
    app = _app(**{"hei.public": "1", "nodal.officers_public": "1"})
    client = app.test_client()
    page = _get(client, "/institutions?lang=en")
    kpis = page[page.index('<div class="pi-kpis'):page.index('<div class="pi-two')]
    assert 'class="pi-kpis n3"' in kpis and 'class="lbl">Institutions registered</div>' not in kpis
    assert kpis.count('class="card pi-kpi') == 3
    rings_page = _get(client, "/nodal-institutions?lang=en")
    rings = rings_page[rings_page.index('class="prog-rings no-rings'):rings_page.index('class="no-steps-h"')]
    assert 'class="prog-rings no-rings n2"' in rings_page and rings.count('class="card prog-ring') == 2
    assert "Participating Institutions under a Nodal Officer" not in rings
    # the Console's switches bring them back
    on = _app(**{"hei.public": "1", "nodal.officers_public": "1", "institutions.registered": "1", "nodal.covered": "1"}).test_client()
    page = _get(on, "/institutions?lang=en")
    kpis = page[page.index('<div class="pi-kpis'):page.index('<div class="pi-two')]
    assert '<div class="pi-kpis">' in kpis and 'class="lbl">Institutions registered</div>' in kpis
    rings_page = _get(on, "/nodal-institutions?lang=en")
    rings = rings_page[rings_page.index('class="prog-rings no-rings'):rings_page.index('class="no-steps-h"')]
    assert rings.count('class="card prog-ring') == 3 and "Participating Institutions under a Nodal Officer" in rings

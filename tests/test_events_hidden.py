"""
The seminars and workshops of CICT hidden (version 1.2.151; the user: "hide Seminars and workshops of CICT"): setting
events.public, '0' by default; the menu's link, the cards on the home page and in the Digital repository, the figure of
"KTS 5.0 in numbers", the search (its results and its hint) and the sitemap without them; the page /seminars-workshops still
opens at its address, out of the search engines; '1' shows it all again.

    python -m pytest tests -q
"""
from markupsafe import escape

from conftest import make_app


def _get(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def _app(shown="0"):
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("events.public", shown)
    return app


def test_the_setting():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS["events.public"] == "0"
    assert [k for k, _label, kind in dict(SETTING_GROUPS)["Site"] if k == "events.public" and kind == "bool"] == ["events.public"]


def test_hidden_on_every_public_page():
    from kts.i18n import CATALOG
    from kts.public import SITEMAP
    app = _app()
    client = app.test_client()
    for code, catalogue in CATALOG.items():
        home = _get(client, f"/?lang={code}")
        assert "/seminars-workshops" not in home and "ev-home" not in home, code
        assert escape(catalogue["num.events"]) not in home.split('<section class="numbers"')[1].split("</section>")[0], code
        resources = _get(client, f"/resources?lang={code}")
        assert "/seminars-workshops" not in resources and '<div class="grid grid-3" style="margin:18px 0 26px">' in resources, code
        hint = _get(client, f"/search?lang={code}")
        assert escape(catalogue["search.hint_noev"]) in hint and escape(catalogue["search.hint"]) not in hint, code
    # the numbers: seven tiles before the Digital repository
    band = _get(client, "/?lang=en").split('<section class="numbers"')[1].split('class="num-da num-res"')[0]
    assert band.count('class="num-tile') == 7 and "Seminars and workshops" not in band
    # six figures, and the visitors as a bar under them
    assert '<div class="num-grid num-grid-six">' in band and band.rindex('class="num-tile') == band.index('class="num-tile num-live"')
    # no other page of the sitemap leads to it
    with app.test_request_context():
        from flask import url_for
        paths = {url_for(ep, **args) for _heading, links in SITEMAP for ep, args, _label in links} - {"/seminars-workshops"}
    for path in sorted(paths):
        r = client.get(path + ("&" if "?" in path else "?") + "lang=en")
        if r.status_code == 200:
            assert "/seminars-workshops" not in r.get_data(as_text=True), path
    assert "/seminars-workshops" not in _get(client, "/sitemap?lang=en")
    assert "/seminars-workshops" not in _get(client, "/sitemap.xml")
    # the search finds nothing of them, and says nothing of them when it finds nothing
    page = _get(client, "/search?lang=en&q=brahmi")
    assert 'aria-labelledby="sg-events"' not in page and "/seminars-workshops" not in page
    page = _get(client, "/search?lang=en&q=zzqqxxyy")
    assert "seminars and workshops" not in page and "lectures, reels and the pages of the portal" in page


def test_the_page_still_opens_out_of_the_search_engines():
    client = _app().test_client()
    r = client.get("/seminars-workshops?lang=en")
    assert r.status_code == 200 and r.headers.get("X-Robots-Tag") == "noindex"
    assert "Seminars and workshops of CICT" in r.get_data(as_text=True)


def test_shown_again_with_the_setting():
    client = _app("1").test_client()
    home = _get(client, "/?lang=en")
    assert '<li><a href="/seminars-workshops">Seminars and workshops of CICT</a></li>' in home
    assert '<a class="card accent ev-home-card" href="/seminars-workshops">' in home
    assert '<span class="num-l">Seminars and workshops of CICT</span>' in home and "num-grid-six" not in home
    resources = _get(client, "/resources?lang=en")
    assert '<div class="grid grid-4" style="margin:18px 0 26px">' in resources and 'href="/seminars-workshops"' in resources
    assert 'aria-labelledby="sg-events"' in _get(client, "/search?lang=en&q=brahmi")
    assert "seminars and workshops, lectures" in _get(client, "/search?lang=en")
    assert 'href="/seminars-workshops"' in _get(client, "/sitemap?lang=en")
    assert "/seminars-workshops</loc>" in _get(client, "/sitemap.xml")
    r = client.get("/seminars-workshops?lang=en")
    assert r.status_code == 200 and "X-Robots-Tag" not in r.headers

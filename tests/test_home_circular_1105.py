"""
The newest circular in the band of the home page (1.2.162), as CICT asked on 5 November 2026 ("hide: D.O. letter of the Ministry of
Education, 31 October 2026 → ⬇ PDF"): the line of the newest circular of the Ministry and its PDF leave the circular band; the
Guidelines for Nodal Institutions, the State/UT-wise list and the Participating Institutions stay; the notice stays under Notices.
The Console's switch home.circular brings the line back.

    python -m pytest tests/test_home_circular_1105.py -q
"""
from conftest import make_app

LIVE = {"reg.open": "0", "launch.on": "0", "hei.open": "1", "hei.end": "2099-12-31", "reg.end": "2099-12-31"}


def _app(**values):
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for key, value in {**LIVE, **values}.items():
            set_setting(key, value)
    return app


def _band(client, lang="en"):
    page = client.get(f"/?lang={lang}").get_data(as_text=True)
    return page[page.index('<div class="nodal-attention">'):page.index('<section class="hero">')]


def test_the_letter_leaves_the_band():
    from kts.db import DEFAULT_SETTINGS, DO_NOTICE, DO_NOTICE_FILE, query
    assert DEFAULT_SETTINGS["home.circular"] == "0"
    app = _app()
    client = app.test_client()
    from kts.i18n import CATALOG
    for code in CATALOG:
        band = _band(client, code)
        assert 'class="na-first"' not in band and "D.O. letter of the Ministry of Education" not in band, code
        assert DO_NOTICE_FILE not in band and "/notices/" not in band and 'class="na-pdf"' not in band, code
        # the rest of the band stays
        assert 'href="/guidelines-for-nodal-institutions"' in band and '<a class="na-link" href="/nodal-institutions">' in band, code
        assert '<a class="na-btn" href="/institutions">' in band, code
    # the notice itself stays, under Notices, with its letter
    with app.app_context():
        nid = query("SELECT id FROM notices WHERE title = ?", (DO_NOTICE[0],), one=True)["id"]
    assert DO_NOTICE[0].split(":")[0] in client.get("/notices?lang=en").get_data(as_text=True)
    notice = client.get(f"/notices/{nid}?lang=en")
    assert notice.status_code == 200 and DO_NOTICE_FILE in notice.get_data(as_text=True)
    assert client.get(f"/files/{DO_NOTICE_FILE}").status_code == 200


def test_the_console_brings_it_back():
    from kts.admin import SETTING_GROUPS
    from kts.db import DO_NOTICE_FILE, set_setting
    site = {k: kind for k, _label, kind in dict(SETTING_GROUPS)["Site"]}
    assert site["home.circular"] == "bool"
    app = _app()
    with app.app_context():
        set_setting("home.circular", "1")
    band = _band(app.test_client())
    assert band.index('<li class="na-first">') < band.index('href="/guidelines-for-nodal-institutions"')
    assert '<span class="na-title" lang="en" dir="ltr">D.O. letter of the Ministry of Education, 31 October 2026</span>' in band
    assert f'href="/files/{DO_NOTICE_FILE}"' in band

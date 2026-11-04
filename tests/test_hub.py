"""
"Find your next step" (version 1.2.140): the hub of the home page - a tab for each audience with what to do now and the days left;
for the students, "Is your college taking part?", the search of the Participating Institutions (/my-college.json as they type,
/my-college as a page) and, when the college is not among them, the message to the Principal with the link to register.

    python -m pytest tests -q
"""
import json
from datetime import date, datetime
from urllib.parse import unquote

from markupsafe import escape

from conftest import ROOT, make_app


def _at(app, day, monkeypatch):
    """The clock of kts/finder.py at 10:00 IST on that day."""
    from kts import finder
    from kts.utils import IST
    monkeypatch.setattr(finder, "now_ist", lambda: datetime(day.year, day.month, day.day, 10, 0, tzinfo=IST))


def _portal():
    from kts.db import execute, set_setting, utcnow
    app = make_app(ADMIN_PASSWORD=None)
    rows = [("Government Arts College", "Coimbatore", "Tamil Nadu", "accepted", "C-12345"),
            ("PSG College of Arts and Science", "Coimbatore", "Tamil Nadu", "accepted", ""),
            ("Maharaja's College", "Ernakulam", "Kerala", "accepted", ""),
            ("Kavaratti Arts College", "Kavaratti", "Lakshadweep", "accepted", ""),
            ("Government Engineering College", "Thrissur", "Kerala", "pending", ""),
            ("Hidden Declined College", "Pune", "Maharashtra", "declined", "")]
    with app.app_context():
        for n, (name, district, state, status, aishe) in enumerate(rows, 1):
            execute("INSERT INTO institutions(ref, name, itype, state, district, aishe_code, inst_key, status, created_at, updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)", (f"KTS5-HEI-{n:05d}", name, "Government college", state, district, aishe,
                                                    f"name:{name.lower()}|{state.lower()}", status, utcnow(), utcnow()))
        set_setting("hei.open", "1")
        set_setting("hei.public", "1")
        set_setting("home.hub", "1")   # hidden on the home page by default since 1.2.146
        for key, value in (("hei.end", "2026-11-15"), ("hei.select_end", "2026-11-17"), ("camp.to", "2026-11-19"),
                           ("reg.end", "2026-11-20"), ("verify.end", "2026-12-05")):
            set_setting(key, value)
    return app


def test_the_search():
    from kts import finder
    app = _portal()
    with app.test_request_context():
        names = lambda q: [r["name"] for r in finder.search(q, "en")["results"]]  # noqa: E731
        # every word that says something must begin a word of the name, the district or the State/UT; short forms written out
        assert names("govt arts coimbatore") == ["Government Arts College"]
        assert names("arts coim") == ["Government Arts College", "PSG College of Arts and Science"]
        assert names("psg") == ["PSG College of Arts and Science"] and names("maharaja") == ["Maharaja's College"]
        assert names("college") == [] and names("the university of") == []
        # the accepted only: neither the pending nor the declined
        assert names("engineering thrissur") == [] and names("hidden declined") == []
        # the paired Union Territory under its own name and the row of Annexure-I
        r = finder.search("kavaratti", "en")["results"][0]
        assert r["state"] == "Lakshadweep" and r["district"] == "Kavaratti" and r["url"] == "/institutions#st-lakshadweep"
        # an AISHE code finds its institution, with or without the hyphen
        assert names("C-12345") == names("c12345") == ["Government Arts College"]
        d = finder.search("coimbatore", "en")
        assert d["total"] == 2 and d["searched"] == 4 and set(d["results"][0]) == {"name", "district", "state", "url"}


def test_the_days_left():
    from kts.finder import days_chip, span
    today = date(2026, 11, 3)
    assert days_chip(date(2026, 11, 15), today, "en") == ("ok", "12 days left")
    assert days_chip(date(2026, 11, 6), today, "en") == ("soon", "3 days left")
    assert days_chip(date(2026, 11, 4), today, "en") == ("soon", "1 day left")
    assert days_chip(date(2026, 11, 3), today, "en") == ("now", "Last day today")
    assert days_chip(date(2026, 11, 2), today, "en") == ("shut", "Closed") and days_chip(None, today, "en") is None
    assert span(date(2026, 11, 16), date(2026, 11, 17), "en") == "16–17 November 2026"
    assert span(date(2026, 12, 15), date(2027, 1, 14), "en") == "15 December – 14 January 2027"


def test_the_hub_of_the_home_page(monkeypatch):
    app = _portal()
    _at(app, date(2026, 11, 3), monkeypatch)
    page = app.test_client().get("/?lang=en").get_data(as_text=True)
    hub = page[page.index('<section class="hub-section"'):page.index('<section class="section', page.index('<section class="hub-section"'))]
    assert page.index('class="hero"') < page.index('class="hub-section"') < page.index('<section class="numbers"')
    assert '<h2 id="hub-title">Find your next step</h2>' in hub and hub.count('role="tab"') == 3 and hub.count('role="tabpanel"') == 3
    assert '<button type="button" class="hub-tab" role="tab" id="hub-tab-student" aria-controls="hub-student" aria-selected="true"' in hub
    # the student: the days left to the assessment, the search, the message to the Principal (hidden until nothing is found)
    assert "<h3>Is your college taking part?</h3><span class=\"hub-chip ok\">16 days left</span>" in hub
    assert 'action="/my-college"' in hub and 'data-hub-find="/my-college.json?lang=en"' in hub
    assert "Searching the 4 Participating Institutions selected so far" in hub
    assert '<div class="hub-invite" data-hub-invite hidden>' in hub
    assert "Colleges and universities can still register until 15 November 2026. Send this to your Principal:" in hub
    assert "Colleges and universities register on the KTS 5.0 portal by 15 November 2026: http://localhost:8905/institutions/register The Nodal Institution of the State/UT selects" in hub
    wa = hub[hub.index('href="https://wa.me/?text=') + 6:]
    wa = wa[:wa.index('"')]
    assert "15 November 2026" in unquote(wa) and "/institutions/register" in unquote(wa)
    assert 'href="mailto:?subject=Kashi%20Tamil%20Sangamam%205.0%3A%20please%20register%20our%20college%20by%2015%20November%202026&amp;body=' in hub
    assert 'data-hub-copy data-done="Copied" hidden>' in hub
    # the college or university: register by 15 November, 12 days left, the institutions registered so far
    assert "<h3>Register your institution by 15 November 2026</h3><span class=\"hub-chip ok\">12 days left</span>" in hub
    assert "selects the Participating Institutions on 16–17 November 2026; each then assesses its students by 19 November 2026 and nominates one by 20 November 2026." in hub
    assert "6 institutions have registered so far." in hub   # declined ones too, as the dashboard counts them
    assert 'href="/institutions/register">Register your institution</a>' in hub and 'href="/institution/login">Institution sign-in</a>' in hub
    # the Nodal Officer: select by 17 November, then verify by 5 December
    assert "<h3>Select the Participating Institutions by 17 November 2026</h3><span class=\"hub-chip ok\">14 days left</span>" in hub
    assert 'href="/console/login">Console sign-in</a>' in hub and 'href="/nodal-institutions#letter">' in hub


def test_the_hub_after_the_registration_of_the_institutions(monkeypatch):
    app = _portal()
    _at(app, date(2026, 11, 18), monkeypatch)
    page = app.test_client().get("/?lang=en").get_data(as_text=True)
    hub = page[page.index('<section class="hub-section"'):page.index('<section class="section', page.index('<section class="hub-section"'))]
    # registration of institutions ended (by the clock of the window, hei.end): the panel of the Participating Institutions
    from kts import heis
    assert heis.window({"hei.open": "1", "hei.end": "2026-11-15"}) in ("ended", "open")
    if "Register your institution by" not in hub:
        assert "<h3>Participating Institutions: assess by 19 November 2026, nominate by 20 November 2026</h3>" in hub
    assert "<h3>Verify the nominations by 5 December 2026</h3>" in hub and "<span class=\"hub-chip soon\">1 day left</span>" in hub


def test_the_json_and_the_page():
    app = _portal()
    client = app.test_client()
    r = client.get("/my-college.json?q=govt+arts&lang=en")
    assert r.status_code == 200 and r.mimetype == "application/json" and r.headers["Cache-Control"] == "no-store"
    d = json.loads(r.get_data(as_text=True))
    assert d["total"] == 1 and d["results"][0]["name"] == "Government Arts College" and d["results"][0]["state"] == "Tamil Nadu"
    assert json.loads(client.get("/my-college.json?q=ab").get_data(as_text=True)) == {"total": 0, "results": [], "searched": None}
    # the page: found, and not found (the message to the Principal shown, without the script)
    page = client.get("/my-college?q=coimbatore&lang=en").get_data(as_text=True)
    assert "<h1>Is your college taking part?</h1>" in page and 'data-hub-start="student"' in page
    assert page.count("✓ Participating Institution</span>") == 2 and '<div class="hub-invite" data-hub-invite hidden>' in page
    page = client.get("/my-college?q=nowhere+college+xyz&lang=en").get_data(as_text=True)
    assert '<p class="hub-none">Your college is not among the Participating Institutions yet.</p>' in page
    assert '<div class="hub-invite" data-hub-invite>' in page
    assert "/my-college</loc>" in client.get("/sitemap.xml").get_data(as_text=True)
    # while the Participating Institutions are not public: neither the page nor the search, and no search on the home page
    from kts.db import set_setting
    with app.app_context():
        set_setting("hei.public", "0")
    assert client.get("/my-college").status_code == 404 and client.get("/my-college.json?q=arts").status_code == 404
    home = client.get("/?lang=en").get_data(as_text=True)
    assert 'class="hub-section"' in home and 'data-hub-find=' not in home


def test_every_language_and_the_assets():
    from kts.i18n import CATALOG
    app = _portal()
    client = app.test_client()
    for code, catalogue in CATALOG.items():
        page = client.get(f"/?lang={code}").get_data(as_text=True)
        assert f'<h2 id="hub-title">{escape(catalogue["hub.title"])}</h2>' in page, code
        assert str(escape(catalogue["hub.s_title"])) in page and str(escape(catalogue["hub.tab_nodal"])) in page, code
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "portal.js").read_text(encoding="utf-8")
    assert ".hub-section { position: relative; z-index: 3; margin-top: -30px;" in css and ".hub-js .hub-panel.on" in css
    assert 'document.querySelector("[data-hub]")' in js and 'localStorage.setItem("kts.hub", key)' in js and "navigator.clipboard" in js
    assert "innerHTML" not in js[js.index('document.querySelector("[data-hub]")'):]

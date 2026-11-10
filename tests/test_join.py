"""
The State/UT pages for the registration of institutions (version 1.2.142): /join (the board of the 31 rows of Annexure-I),
/join/<code> (the live count against the number to be selected, the button to register with the State/UT filled in and marked
as coming from the page, what to have ready, the Nodal Institution, the message to forward), /join/<code>/poster (A4, QR);
the form's "Have this ready", the done page's "Pass it on", the source in the Console's export; setting join.on.

    python -m pytest tests -q
"""
import io
import re
from datetime import datetime
from urllib.parse import unquote

from conftest import make_app
from test_public_fixes import _staff


def _clock(monkeypatch, day, month=11):
    from kts import drive, finder, heis, public
    from kts.utils import IST
    at = datetime(2026, month, day, 10, 0, tzinfo=IST)
    for mod in (drive, finder, heis, public):
        monkeypatch.setattr(mod, "now_ist", lambda: at)
    drive.clear()


def _portal():
    from kts import drive
    from kts.db import execute, set_setting, utcnow
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("institutions.registered", "1")   # the institutions registered shown (hidden by default since 1.2.168, tests/test_1110.py)
    rows = [("Presidency College", "Tamil Nadu", "accepted"), ("Loyola College", "Tamil Nadu", "pending"),
            ("Declined College", "Tamil Nadu", "declined"), ("JNRM Port Blair", "Andaman and Nicobar Islands", "accepted"),
            ("Identified Only College", "Tamil Nadu", "identified"), ("Secret Test College", "Tamil Nadu", "accepted")]
    rows += [(f"Sikkim College {i}", "Sikkim", "pending") for i in range(6)]
    with app.app_context():
        for n, (name, state, status) in enumerate(rows, 1):
            execute("INSERT INTO institutions(ref, name, itype, state, district, inst_key, status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (f"KTS5-HEI-{n:05d}", name, "Government college", state, "District", f"name:{name.lower()}|{state.lower()}", status, utcnow(), utcnow()))
        for key, value in (("hei.open", "1"), ("hei.end", "2026-11-15"), ("hei.select_end", "2026-11-17"), ("camp.to", "2026-11-19"),
                           ("reg.end", "2026-11-20"), ("verify.end", "2026-12-05"), ("join.on", "1"),
                           ("home.hub", "1")):   # the hub, with its link to /join, hidden by default since 1.2.146
            set_setting(key, value)
    drive.clear()
    return app


def test_the_codes_and_the_redirects(monkeypatch):
    from kts.progress import nodal_heis
    app = _portal()
    _clock(monkeypatch, 3)
    client = app.test_client()
    from kts import drive
    with app.app_context():
        codes = [drive.code_of(h["state"]) for h in nodal_heis()]
    assert len(codes) == 31 and len(set(codes)) == 31 and None not in codes
    for code in codes:
        assert client.get(f"/join/{code}?lang=en").status_code == 200, code
    for ut, row in (("ld", "kl"), ("ch", "pb"), ("dh", "gj"), ("an", "tn"), ("la", "jk")):
        r = client.get(f"/join/{ut}?lang=ta")
        assert r.status_code == 302 and r.headers["Location"].endswith(f"/join/{row}?lang=ta"), ut
    assert client.get("/join/zz").status_code == 404 and client.get("/join/OD").status_code == 200


def test_the_page_of_a_row(monkeypatch):
    app = _portal()
    _clock(monkeypatch, 3)
    page = app.test_client().get("/join/tn?lang=en").get_data(as_text=True)
    # registered: Presidency, Loyola, Declined, Secret and the A&N college (folded into the row); not the one only identified
    assert "<h1>Tamil Nadu and Andaman and Nicobar Islands: 50 colleges and universities to be selected for KTS 5.0</h1>" in page
    assert '<b class="join-big"><bdi dir="ltr">5</bdi></b> <span>Institutions registered: 5 of 50</span>' in page
    assert page.count('<i class="jm-sq') == 50 and page.count('<i class="jm-sq on">') == 5
    assert '<span class="hub-chip ok">12 days left</span>' in page and "Live figures, as on 10:00 IST" in page
    assert '<meta name="description" content="Institutions registered: 5 of 50 · 12 days left">' in page
    # a paired row: the button carries via=join and no State/UT
    assert 'class="btn saffron join-cta" href="/institutions/register?via=join"' in page
    assert "Have this ready before you start" in page and "Central University of Tamil Nadu" in page
    msg = page[page.index('id="join-msg">') + 14:page.index("</blockquote>", page.index('id="join-msg">'))]
    assert "50 colleges and universities of Tamil Nadu and Andaman and Nicobar Islands are to be selected, and 5 have registered so far" in msg
    assert "Register yours by 15 November 2026: http://localhost:8905/join/tn" in msg
    assert 'href="https://wa.me/?text=' in page and "/join/tn/poster" in page
    assert 'data-copy="join-msg"' in page and "data-share" in page
    # never the name of an institution
    for name in ("Presidency", "Loyola", "Secret Test College", "JNRM"):
        assert name not in page, name


def test_the_meter_the_first_and_the_over(monkeypatch):
    app = _portal()
    _clock(monkeypatch, 3)
    client = app.test_client()
    up = client.get("/join/up?lang=en").get_data(as_text=True)
    assert 'class="jm-bar"' in up and "jm-sq" not in up and 'href="/institutions/register?state=Uttar+Pradesh&amp;via=join"' in up
    od = client.get("/join/od?lang=en").get_data(as_text=True)
    assert "No college or university of Odisha has registered yet. Be the first." in od
    sk = client.get("/join/sk?lang=en").get_data(as_text=True)
    assert "the Nodal Institution selects 5 on merit and keeps a reserve list" in sk and "full" not in sk.split('id="main"')[1].split("</main>")[0].lower()
    assert sk.count('<i class="jm-sq on">') == 5


def test_the_phases(monkeypatch):
    app = _portal()
    client = app.test_client()
    _clock(monkeypatch, 18)
    page = client.get("/join/od?lang=en").get_data(as_text=True)
    assert "<h1>Participating Institutions: assess by 19 November 2026, nominate by 20 November 2026</h1>" in page
    assert "0 of 0 Participating Institutions of Odisha have opened the online test; 0 have selected their student." in page
    main = page.split('id="main"')[1].split("</main>")[0]
    assert 'href="/institution/login"' in main and "/institutions/register" not in main
    r = client.get("/join/od/poster")
    assert r.status_code == 302 and r.headers["Location"].endswith("/join/od")
    _clock(monkeypatch, 22)
    page = client.get("/join/od?lang=en").get_data(as_text=True)
    assert 'href="/dashboard">KTS 5.0 by State/UT</a>' in page


def test_the_poster_and_the_board(monkeypatch):
    app = _portal()
    _clock(monkeypatch, 3)
    client = app.test_client()
    poster = client.get("/join/od/poster?lang=or").get_data(as_text=True)
    assert 'class="jp-qr" src="data:image/png;base64,' in poster and '<p class="jp-url" dir="ltr">localhost:8905/join/od</p>' in poster
    assert "Odisha: 48 colleges and universities to be selected for KTS 5.0" in poster   # the English line under the Odia
    assert "join-big" not in poster and "data-print" in poster
    board = client.get("/join?lang=en").get_data(as_text=True)
    assert board.count('class="jb-row"') == 31 and "All States/UTs" in board and "Secret Test College" not in board
    codes = re.findall(r'<span class="jb-code" dir="ltr">(\w+)</span>', board)
    assert codes[-1] in ("SK", "TN") and codes.index("SK") > codes.index("UP")   # the emptiest first
    assert "/join</loc>" in client.get("/sitemap.xml").get_data(as_text=True) and "/join/up</loc>" in client.get("/sitemap.xml").get_data(as_text=True)


def test_the_form_the_source_and_the_done_page(monkeypatch):
    from kts.db import query
    from test_institutions import _apply
    app = _portal()
    _clock(monkeypatch, 3)
    client = app.test_client()
    form = client.get("/institutions/register?state=Odisha&via=join&lang=en").get_data(as_text=True)
    assert '<option value="Odisha" selected>' in form and '<input type="hidden" name="via" value="join">' in form
    assert "Have this ready before you start" in form
    assert '<option value="Atlantis"' not in client.get("/institutions/register?state=Atlantis").get_data(as_text=True)
    r = _apply(client, name="Ravenshaw College", state="Odisha", aishe_code="", head_email="h@rc.example", coord_email="c@rc.example", via="join")
    assert r.status_code == 302
    with app.app_context():
        assert query("SELECT source FROM institutions WHERE name = 'Ravenshaw College'", one=True)["source"] == "join"
    done = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "Forward this page to the Principals you know" in done and "/join/od" in done and "https://wa.me/?text=" in done
    other = app.test_client()
    r = _apply(other, name="Plain College", state="Odisha", aishe_code="", head_email="h@pc.example", coord_email="c@pc.example")
    with app.app_context():
        assert query("SELECT source FROM institutions WHERE name = 'Plain College'", one=True)["source"] == ""
    # the Console's export shows the source
    from kts.utils import xlsx_rows
    admin = _staff(app, "admin@tests.example", "superadmin")
    rows = xlsx_rows(admin.get("/console/institutions/export.xlsx").data)
    assert rows[0][-1] == "Source" and ["State/UT page"] == [r[-1] for r in rows[1:] if r[3] == "Ravenshaw College"]


def test_languages_links_and_the_switch(monkeypatch):
    from kts.db import set_setting
    from kts.i18n import CATALOG
    app = _portal()
    _clock(monkeypatch, 3)
    client = app.test_client()
    for code in ("ur", "ks"):
        assert 'dir="rtl"' in client.get(f"/join/kl?lang={code}").get_data(as_text=True)[:600], code
    odia = client.get("/join/od?lang=or").get_data(as_text=True)
    assert CATALOG["or"]["join.ready_t"] in odia and "/join/od?lang=or" in unquote(odia)
    assert client.get("/join/od").headers["Content-Security-Policy"] == client.get("/").headers["Content-Security-Policy"]
    assert 'href="/join">Registration of institutions, State/UT by State/UT →</a>' in client.get("/?lang=en").get_data(as_text=True)
    nodal = client.get("/nodal-institutions?lang=en").get_data(as_text=True)
    assert nodal.count('<td class="join-cell small"><a href="/join/') == 31
    for code, catalogue in CATALOG.items():
        assert client.get(f"/join/od?lang={code}").status_code == 200, code
    with app.app_context():
        set_setting("join.on", "0")
    assert client.get("/join").status_code == 404 and client.get("/join/od").status_code == 404 and client.get("/join/od/poster").status_code == 404
    assert 'href="/join' not in client.get("/?lang=en").get_data(as_text=True)
    assert "join-cell" not in client.get("/nodal-institutions?lang=en").get_data(as_text=True)

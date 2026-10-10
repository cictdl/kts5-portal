"""
The participating institutions of the States/UTs (version 1.2.41): an institution applies on the
website, the Nodal Officer of its State/UT accepts or declines it, the accepted ones are listed
State/UT by State/UT, and a student chooses one of them (or "not listed") when registering.

    python -m pytest tests -q
"""
import re

from conftest import make_app
from test_nodal_access import _nodal, _token
from test_public_fixes import _staff

FORM = {"name": "Government Arts College Thrissur", "itype": "Government college", "state": "Kerala", "district": "Thrissur",
        "aishe_code": "c-12345", "head_name": "Dr. A. Principal", "head_designation": "Principal",
        "head_email": "Principal@gac.example", "head_phone": "0487-2251234", "coord_name": "Dr. B. Coordinator",
        "coord_email": "coord@gac.example", "coord_mobile": "9876543210", "coord_designation": "Assistant Professor of Tamil",
        "guide_name": "Dr. C. Guide", "guide_designation": "Associate Professor of History", "guide_email": "guide@gac.example",
        "guide_mobile": "9876501234", "declare": "1"}


def _apply(client, **changes):
    client.get("/institutions/register?lang=en")
    with client.session_transaction() as s:
        token = s["_csrf"]
        s["_captcha"] = "7"
    data = dict(FORM, _csrf=token, captcha="7")
    data.update(changes)
    return client.post("/institutions/register", data=data)


def _app():
    app = make_app(ADMIN_PASSWORD=None)
    from kts.db import set_setting
    with app.app_context():
        set_setting("hei.end", "2099-12-31")
    return app


def test_an_institution_applies_and_the_nodal_officer_accepts_it():
    from kts.db import query
    app = _app()
    officer = _nodal(app, "nodal.kerala@tests.example", ["Kerala"])
    client = app.test_client()
    page = client.get("/institutions/register?lang=en").get_data(as_text=True)
    assert "Register your institution" in page and "Head of the Institution" in page
    r = _apply(client)
    assert r.status_code == 302 and "/institutions/register/done/KTS5-HEI-" in r.headers["Location"]
    done = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "KTS5-HEI-00001" in done and "Government Arts College Thrissur" in done
    with app.app_context():
        row = query("SELECT * FROM institutions", one=True)
        mails = {m["to_addr"]: m for m in query("SELECT * FROM outbox")}
    assert (row["status"], row["head_email"], row["head_phone"], row["aishe_code"]) == ("pending", "principal@gac.example", "4872251234", "C-12345")
    assert {"principal@gac.example", "coord@gac.example", "nodal.kerala@tests.example"} <= set(mails)
    assert "/console/institutions?status=pending" in mails["nodal.kerala@tests.example"]["body"]
    # the same institution again: refused
    r = _apply(app.test_client(), name="government arts college  thrissur")
    assert r.status_code == 400 and "already applied (reference KTS5-HEI-00001)" in r.get_data(as_text=True)
    # not yet on the public list
    assert "Government Arts College Thrissur" not in client.get("/institutions?lang=en").get_data(as_text=True)
    # the Nodal Officer of Kerala accepts it
    page = officer.get("/console/institutions").get_data(as_text=True)
    assert "Government Arts College Thrissur" in page and "pending" in page
    r = officer.post("/console/institutions", data={"_csrf": _token(officer), "id": str(row["id"]), "action": "accept"})
    assert r.status_code == 302
    with app.app_context():
        assert query("SELECT status FROM institutions", one=True)["status"] == "accepted"
        accepted = query("SELECT body FROM outbox WHERE to_addr = 'coord@gac.example' ORDER BY id DESC LIMIT 1", one=True)["body"]
    assert "has accepted your institution" in accepted and "KTS5-nomination-form.pdf" in accepted
    listing = client.get("/institutions?lang=en").get_data(as_text=True)
    assert "Government Arts College Thrissur" in listing and "Central University of Kerala" in listing
    assert "1 institutions from 1 States/UTs" in listing
    # the institution signs in and sees its page
    assert "Government Arts College Thrissur" in page
    # the export of the console
    r = officer.get("/console/institutions/export.xlsx")
    assert r.status_code == 200 and r.data[:2] == b"PK"


def test_a_nodal_officer_decides_for_their_state_only_and_the_most_is_kept():
    from kts.db import query, set_setting
    app = _app()
    for n, (name, state) in enumerate((("College One", "Kerala"), ("College Two", "Kerala"), ("College Three", "Assam"))):
        _apply(app.test_client(), name=name, state=state, aishe_code="", head_email=f"h{n}@x.example", coord_email=f"c{n}@x.example")
    with app.app_context():
        ids = {r["name"]: r["id"] for r in query("SELECT id, name FROM institutions")}
        set_setting("hei.max_per_state", "1")   # 0, the default since 1.2.43, is no limit
    officer = _nodal(app, "nodal.kerala@tests.example", ["Kerala"])
    page = officer.get("/console/institutions").get_data(as_text=True)
    assert "College One" in page and "College Three" not in page
    assert officer.post("/console/institutions", data={"_csrf": _token(officer), "id": ids["College Three"], "action": "accept"}).status_code == 404
    assert officer.get(f"/console/institutions/{ids['College Three']}/edit").status_code == 404
    officer.post("/console/institutions", data={"_csrf": _token(officer), "id": ids["College One"], "action": "accept"})
    r = officer.post("/console/institutions", data={"_csrf": _token(officer), "id": ids["College Two"], "action": "accept"},
                     follow_redirects=True)
    assert "that is the most" in r.get_data(as_text=True)
    officer.post("/console/institutions", data={"_csrf": _token(officer), "id": ids["College Two"], "action": "decline",
                                                "note": "Not a higher educational institution"})
    with app.app_context():
        status = {r["name"]: (r["status"], r["decision_note"]) for r in query("SELECT * FROM institutions")}
        mail = query("SELECT body FROM outbox WHERE to_addr = 'c1@x.example' ORDER BY id DESC LIMIT 1", one=True)["body"]
    assert status == {"College One": ("accepted", ""), "College Two": ("declined", "Not a higher educational institution"),
                      "College Three": ("pending", "")}
    assert "could not accept" in mail and "Remark: Not a higher educational institution" in mail
    # a viewer sees, does not decide
    viewer = _staff(app, "viewer@tests.example", "viewer")
    assert "College Three" in viewer.get("/console/institutions").get_data(as_text=True)
    assert viewer.post("/console/institutions", data={"_csrf": _token(viewer), "id": ids["College Three"], "action": "accept"}).status_code == 403
    # the page of the Nodal Officers counts them
    admin = _staff(app, "admin@tests.example", "superadmin")
    kerala = admin.get("/console/nodal").get_data(as_text=True).split("Central University of Kerala")[1].split("</tr>")[0]
    assert "1<span class=\"small muted\">/45</span>" in kerala


def test_the_form_checks_and_closes():
    from kts.db import set_setting
    app = _app()
    r = _apply(app.test_client(), head_phone="12345", coord_mobile="123", head_email="nope", name="கல்லூரி", declare="")
    page = r.get_data(as_text=True)
    assert r.status_code == 400
    for says in ("Enter a 10-digit phone number", "Enter a valid 10-digit Indian mobile number", "Enter a valid email address",
                 "Write this in English letters", "Please confirm the declaration"):
        assert says in page, says
    with app.app_context():
        set_setting("hei.end", "2020-01-01")
    page = app.test_client().get("/institutions/register?lang=en").get_data(as_text=True)
    assert "Applications of institutions closed on" in page and 'name="head_name"' not in page
    with app.app_context():
        set_setting("hei.open", "0")
    assert "Institutions cannot apply on the website at present." in app.test_client().get("/institutions/register?lang=en").get_data(as_text=True)
    with app.app_context():
        set_setting("hei.public", "0")
    assert app.test_client().get("/institutions").status_code == 404


def test_the_morning_mail_names_the_institutions_awaiting():
    from datetime import datetime
    from kts import nodal
    from kts.db import query, set_setting
    from kts.utils import IST
    app = _app()
    _nodal(app, "nodal.kerala@tests.example", ["Kerala"])
    _apply(app.test_client())
    with app.app_context():
        set_setting("reg.start", "2026-10-15")
        set_setting("verify.end", "2026-10-21")
    # before registration opens: the mail goes for the institution awaiting a decision
    assert nodal.daily(app, datetime(2026, 10, 10, 8, 30, tzinfo=IST)) == 1
    with app.app_context():
        mail = query("SELECT * FROM outbox WHERE to_addr = 'nodal.kerala@tests.example' ORDER BY id DESC LIMIT 1", one=True)
    assert mail["subject"] == "KTS 5.0: 1 institution awaits your decision (Kerala)"
    assert "Institutions awaiting your decision: 1." in mail["body"]


def test_register_leads_to_the_institutions():
    """Version 1.2.42: Register opens a short menu, and the registration pages offer the institutions."""
    from kts.db import set_setting
    app = _app()
    client = app.test_client()
    page = client.get("/?lang=en").get_data(as_text=True)
    sub = page.split('id="primary-menu"')[1].split('class="has-sub"')[1].split("</ul></li>")[0]
    assert '<ul class="sub">' in sub
    for href, label in (("/register", "Participant registration"), ("/institutions/register", "Register your institution"),
                        ("/institutions", "Participating institutions")):
        assert f'<a href="{href}">{label}</a>' in sub
    # Register is lit on the pages of the institutions
    for path in ("/institutions/register?lang=en", "/institutions?lang=en"):
        assert '<a href="/register" class="active" aria-haspopup="true">' in client.get(path).get_data(as_text=True)
    # the registration form, and the page before registration opens, offer the institutions
    def content(path):
        html = client.get(path).get_data(as_text=True)
        return html.split('class="nav"')[1].split("</nav>", 1)[1].split("<footer")[0]
    assert 'href="/institutions/register"' in content("/register?lang=en")
    with app.app_context():
        set_setting("reg.start", "2099-01-01")
        set_setting("reg.end", "2099-01-31")
    page = content("/register?lang=en")
    assert 'name="full_name"' not in page and 'href="/institutions/register"' in page and 'href="/institutions"' in page
    with app.app_context():
        set_setting("hei.open", "0")
    page = content("/register?lang=en")
    assert 'href="/institutions/register"' not in page and 'href="/institutions"' in page


def test_the_coordinator_and_the_faculty_supervisor_are_two_people():
    """1.2.46, Annexure-IV: the Institutional Coordinator and the Faculty Supervisor/Guide, each with name, designation, e-mail, mobile."""
    from kts.db import query
    app = _app()
    page = app.test_client().get("/institutions/register?lang=en").get_data(as_text=True)
    assert "3 · Institutional Coordinator" in page and "4 · Faculty Supervisor/Guide" in page and "5 · Declaration" in page
    for name in ("coord_designation", "guide_name", "guide_designation", "guide_email", "guide_mobile"):
        assert f'name="{name}"' in page, name
    # each is required, and checked
    r = _apply(app.test_client(), guide_name="", guide_email="nope", guide_mobile="123", coord_designation="")
    page = r.get_data(as_text=True)
    assert r.status_code == 400 and page.count("This field is required.") >= 2
    assert "Enter a valid email address" in page and "Enter a valid 10-digit Indian mobile number" in page
    r = _apply(app.test_client())
    assert r.status_code == 302
    with app.app_context():
        row = query("SELECT * FROM institutions", one=True)
        mail = query("SELECT body FROM outbox WHERE to_addr = 'coord@gac.example' ORDER BY id LIMIT 1", one=True)["body"]
    assert (row["coord_designation"], row["guide_name"], row["guide_email"], row["guide_mobile"]) == (
        "Assistant Professor of Tamil", "Dr. C. Guide", "guide@gac.example", "9876501234")
    assert "Institutional Coordinator: Dr. B. Coordinator, Assistant Professor of Tamil" in mail
    assert "Faculty Supervisor/Guide: Dr. C. Guide, Associate Professor of History" in mail

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
    assert "has selected your institution as a Participating Institution" in accepted and "KTS5-nomination-form.pdf" in accepted
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
        set_setting("hei.cap_annexure", "0")    # the number of Annexure-I (1.2.110) off: the limit for all States/UTs
        set_setting("hei.max_per_state", "1")   # 0, the default since 1.2.43, is no limit
    officer = _nodal(app, "nodal.kerala@tests.example", ["Kerala"])
    page = officer.get("/console/institutions").get_data(as_text=True)
    assert "College One" in page and "College Three" not in page
    assert officer.post("/console/institutions", data={"_csrf": _token(officer), "id": ids["College Three"], "action": "accept"}).status_code == 404
    assert officer.get(f"/console/institutions/{ids['College Three']}/edit").status_code == 404
    officer.post("/console/institutions", data={"_csrf": _token(officer), "id": ids["College One"], "action": "accept"})
    r = officer.post("/console/institutions", data={"_csrf": _token(officer), "id": ids["College Two"], "action": "accept"},
                     follow_redirects=True)
    assert "that is the number Annexure-I prescribes for it" in r.get_data(as_text=True)
    officer.post("/console/institutions", data={"_csrf": _token(officer), "id": ids["College Two"], "action": "decline",
                                                "note": "Not a higher educational institution"})
    with app.app_context():
        status = {r["name"]: (r["status"], r["decision_note"]) for r in query("SELECT * FROM institutions")}
        mail = query("SELECT body FROM outbox WHERE to_addr = 'c1@x.example' ORDER BY id DESC LIMIT 1", one=True)["body"]
    assert status == {"College One": ("accepted", ""), "College Two": ("declined", "Not a higher educational institution"),
                      "College Three": ("pending", "")}
    assert "could not select your institution" in mail and "Remark: Not a higher educational institution" in mail
    # a viewer sees, does not decide
    viewer = _staff(app, "viewer@tests.example", "viewer")
    assert "College Three" in viewer.get("/console/institutions").get_data(as_text=True)
    assert viewer.post("/console/institutions", data={"_csrf": _token(viewer), "id": ids["College Three"], "action": "accept"}).status_code == 403
    # the page of the Nodal Officers counts them
    admin = _staff(app, "admin@tests.example", "superadmin")
    kerala = admin.get("/console/nodal").get_data(as_text=True).split("Central University of Kerala")[1].split("</tr>")[0]
    assert "1<span class=\"small muted\">/21</span>" in kerala


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
    for href, label in (("/register", "Student registration"), ("/institutions/register", "Register your institution"),
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


def test_each_state_accepts_at_most_its_number_of_annexure_i():
    # the revised D.O. letter (1.2.110): the Nodal Institution selects only the number Annexure-I prescribes for its State/UT
    from kts import heis as HEI
    from kts.db import execute, query, set_setting, utcnow
    app = _app()
    with app.app_context():
        assert (HEI.cap_of("Kerala"), HEI.cap_of("Uttar Pradesh"), HEI.cap_of("Tamil Nadu"), HEI.cap_of("Puducherry")) == (21, 350, 150, 5)
        assert HEI.cap_of("Ladakh") == 0          # a State/UT without a Nodal Institution: no limit
        for n in range(21):
            execute("INSERT INTO institutions(ref, name, itype, state, district, inst_key, status, created_at, updated_at) "
                    "VALUES(?, ?, 'Government college', 'Kerala', 'Thrissur', ?, 'accepted', ?, ?)",
                    (f"KTS5-HEI-9{n:04d}", f"Accepted College {n}", f"name:accepted college {n}|kerala", utcnow(), utcnow()))
    _apply(app.test_client(), name="College Twenty-two", state="Kerala", aishe_code="", head_email="h@x.example", coord_email="c@x.example")
    with app.app_context():
        rid = query("SELECT id FROM institutions WHERE name = 'College Twenty-two'", one=True)["id"]
    officer = _nodal(app, "nodal.kerala2@tests.example", ["Kerala"])
    r = officer.post("/console/institutions", data={"_csrf": _token(officer), "id": rid, "action": "accept"}, follow_redirects=True)
    assert "Kerala has 21 accepted institutions: that is the number Annexure-I prescribes for it" in r.get_data(as_text=True)
    with app.app_context():
        assert query("SELECT status FROM institutions WHERE id = ?", (rid,), one=True)["status"] == "pending"
        set_setting("hei.cap_annexure", "0")      # switched off in Settings: no limit (hei.max_per_state is 0)
    officer.post("/console/institutions", data={"_csrf": _token(officer), "id": rid, "action": "accept"})
    with app.app_context():
        assert query("SELECT status FROM institutions WHERE id = ?", (rid,), one=True)["status"] == "accepted"


def test_the_marks_of_annexure_v_rank_the_institutions_and_the_reserve_list():
    # the revised D.O. letter (1.2.111): the committee's marks on the six criteria, the order they give, the evaluation sheet,
    # and the reserve list, from which a selected institution that drops out is replaced
    import json as _json
    from kts import heis as HEI
    from kts.db import query
    app = _app()
    for n, name in enumerate(("College Alpha", "College Beta", "College Gamma")):
        _apply(app.test_client(), name=name, state="Kerala", aishe_code="", head_email=f"ha{n}@x.example", coord_email=f"ca{n}@x.example")
    with app.app_context():
        ids = {r["name"]: r["id"] for r in query("SELECT id, name FROM institutions")}
        assert [k for k, *_ in HEI.SOP] == ["readiness", "outreach", "academic", "geography", "diversity", "record"]
        assert sum(m for _k, _c, m, *_ in HEI.SOP) == 100 and HEI.SOP_BENCHMARK == 60
        assert (HEI.reserve_of("Kerala"), HEI.reserve_of("Uttar Pradesh"), HEI.reserve_of("Puducherry"), HEI.reserve_of("Ladakh")) == (5, 70, 1, 0)
    officer = _nodal(app, "nodal.kerala3@tests.example", ["Kerala"])
    page = officer.get(f"/console/institutions/{ids['College Beta']}/marks").get_data(as_text=True)
    assert "Institutional readiness" in page and "Past record and documentation capacity" in page and 'max="25"' in page
    # a mark above the maximum is refused
    r = officer.post(f"/console/institutions/{ids['College Beta']}/marks",
                     data={"_csrf": _token(officer), "readiness": "26", "outreach": "10", "academic": "10", "geography": "10",
                           "diversity": "5", "record": "5"})
    assert r.status_code == 200 and "a whole number from 0 to 25" in r.get_data(as_text=True)
    for name, marks in (("College Alpha", (20, 15, 15, 10, 5, 5)), ("College Beta", (25, 15, 15, 10, 5, 0)),
                        ("College Gamma", (10, 10, 10, 10, 5, 5))):
        officer.post(f"/console/institutions/{ids[name]}/marks",
                     data=dict(zip(("readiness", "outreach", "academic", "geography", "diversity", "record"), map(str, marks)),
                               _csrf=_token(officer), note="Committee of 3, 12 Nov 2026"))
    with app.app_context():
        rows = {r["name"]: r for r in query("SELECT * FROM institutions")}
        assert (rows["College Alpha"]["sop_total"], rows["College Beta"]["sop_total"], rows["College Gamma"]["sop_total"]) == (70, 70, 50)
        assert _json.loads(rows["College Beta"]["sop_scores"])["readiness"] == 25
        # a tie of 70: institutional readiness first
        order = sorted(rows.values(), key=HEI.sop_order)
        assert [r["name"] for r in order] == ["College Beta", "College Alpha", "College Gamma"]
    listing = officer.get("/console/institutions?state=Kerala&order=marks").get_data(as_text=True)
    listing = listing[listing.index('<table class="table institutions">'):]
    assert listing.index("College Beta") < listing.index("College Alpha") < listing.index("College Gamma")
    assert "<b>50</b>/100" in listing and "(below 60)" in listing
    # select one, put one in the reserve list (each is informed by mail), and replace the first from the reserve list
    officer.post("/console/institutions", data={"_csrf": _token(officer), "id": ids["College Beta"], "action": "accept"})
    officer.post("/console/institutions", data={"_csrf": _token(officer), "id": ids["College Alpha"], "action": "reserve"})
    with app.app_context():
        assert query("SELECT status FROM institutions WHERE id = ?", (ids["College Alpha"],), one=True)["status"] == "reserve"
        mail = query("SELECT body FROM outbox WHERE to_addr = 'ca0@x.example' ORDER BY id DESC", one=True)["body"]
        assert "placed your institution in the reserve list" in mail
    page = officer.get("/console/institutions?state=Kerala").get_data(as_text=True)
    assert '<span class="pill saffron">reserve list</span>' in page and '<span class="pill green">selected</span>' in page
    # the reserve list is not among the Participating Institutions of the website
    public = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    assert "College Beta" in public and "College Alpha" not in public
    officer.post("/console/institutions", data={"_csrf": _token(officer), "id": ids["College Beta"], "action": "decline", "note": "Withdrew"})
    officer.post("/console/institutions", data={"_csrf": _token(officer), "id": ids["College Alpha"], "action": "accept"})
    with app.app_context():
        assert query("SELECT status FROM institutions WHERE id = ?", (ids["College Alpha"],), one=True)["status"] == "accepted"
    # the evaluation sheet of Annexure-V, ranked
    r = officer.get("/console/institutions/evaluation.xlsx?state=Kerala")
    assert r.status_code == 200 and r.data[:2] == b"PK"
    import io
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(r.data)).active
    values = [[c.value for c in row] for row in ws.iter_rows()]
    assert values[0][:5] == ["State/UT", "Nodal HEI", "Number to be selected (Annexure-I)", "Reserve list (up to 20%)", "Rank"]
    assert [(v[4], v[5], v[17]) for v in values[1:]] == [(1, "College Beta", 70), (2, "College Alpha", 70), (3, "College Gamma", 50)]
    assert values[1][2] == 21 and values[1][3] == 5 and values[3][18] == "no"
    # a Nodal Officer of another State/UT sees none of them
    other = _nodal(app, "nodal.assam3@tests.example", ["Assam"])
    assert other.get(f"/console/institutions/{ids['College Gamma']}/marks").status_code == 404

"""
The portal in line with the Ministry's D.O. letter of 31 October 2026 (version 1.2.155; the user: "accordingly make changes in the
portal very careful", with the user's answers of 4 November 2026): Annexure-V with its five criteria (20 marks each, 5 as 5A and 5B),
the scoring parameters as the only marks, the tie-break of paragraph 4 and a reserve list of up to 20 per cent; the final list in the
format of Annexure-II; an invited institution awaits the selection; the mails; the selected students without rank or waiting list;
no age limit; CICT's central online test off; the nomination on the schedule; the notices; the guidelines and the guide.

    python -m pytest tests -q
"""
import io
import json
import re

from conftest import make_app
from test_campus import _accepted, _coordinator, _mails, _portal, _register_with
from test_institutions import _app, _apply
from test_nodal_access import _nodal, _token


def _get(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def test_the_five_criteria_of_annexure_v():
    from kts import heis as HEI
    assert [k for k, *_ in HEI.SOP] == ["readiness", "outreach", "academic", "geography", "diversity_type", "diversity_disc"]
    assert [m for _k, _c, m, *_ in HEI.SOP] == [20, 20, 20, 20, 10, 10] and HEI.SOP_BENCHMARK == 60
    allowed = {k: a for k, _c, _m, _p, _e, a in HEI.SOP}
    assert allowed == {"readiness": (0, 5, 10, 15, 20), "outreach": (0, 5, 10, 15, 20), "academic": (0, 5, 10, 15, 20),
                       "geography": (5, 10, 15, 20), "diversity_type": (5, 10), "diversity_disc": (2, 5, 7, 10)}
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        # ordinarily up to 20 per cent of the allocation, at least one
        assert (HEI.reserve_of("Kerala"), HEI.reserve_of("Uttar Pradesh"), HEI.reserve_of("Puducherry"), HEI.reserve_of("Goa")) == (4, 60, 1, 1)


def test_the_committee_records_the_marks_and_they_rank_the_institutions():
    from kts import heis as HEI
    from kts.db import execute, query
    app = _app()
    for n, name in enumerate(("College Alpha", "College Beta", "College Gamma", "College Delta")):
        _apply(app.test_client(), name=name, state="Kerala", aishe_code="", head_email=f"hd{n}@x.example", coord_email=f"cd{n}@x.example")
    with app.app_context():
        ids = {r["name"]: r["id"] for r in query("SELECT id, name FROM institutions")}
    officer = _nodal(app, "nodal.kerala9@tests.example", ["Kerala"])
    page = _get(officer, f"/console/institutions/{ids['College Beta']}/marks")
    assert "1. Institutional readiness" in page and "5B. Disciplinary diversity" in page and "Past record" not in page
    assert '<select name="geography" required' in page and '<option value="25"' not in page
    # a mark the scoring parameters do not give is refused
    r = officer.post(f"/console/institutions/{ids['College Beta']}/marks",
                     data={"_csrf": _token(officer), "readiness": "18", "outreach": "10", "academic": "10", "geography": "10",
                           "diversity_type": "5", "diversity_disc": "5"})
    assert r.status_code == 200 and "one of 0, 5, 10, 15, 20" in r.get_data(as_text=True)
    keys = ("readiness", "outreach", "academic", "geography", "diversity_type", "diversity_disc")
    for name, marks in (("College Alpha", (20, 15, 15, 10, 5, 5)), ("College Beta", (20, 15, 15, 15, 5, 0)),
                        ("College Gamma", (20, 15, 15, 15, 5, 7)), ("College Delta", (10, 10, 10, 5, 5, 2))):
        if name == "College Beta":   # 0 is not a mark of 5B: the form refuses it
            r = officer.post(f"/console/institutions/{ids[name]}/marks", data=dict(zip(keys, map(str, marks)), _csrf=_token(officer)))
            assert "one of 2, 5, 7, 10" in r.get_data(as_text=True)
            marks = (20, 15, 15, 15, 5, 2)
        officer.post(f"/console/institutions/{ids[name]}/marks", data=dict(zip(keys, map(str, marks)), _csrf=_token(officer)))
    with app.app_context():
        rows = {r["name"]: r for r in query("SELECT * FROM institutions")}
        assert {n: rows[n]["sop_total"] for n in rows} == {"College Alpha": 70, "College Beta": 72, "College Gamma": 77, "College Delta": 42}
        # a tie of the total is broken by readiness, academic engagement, then geographical representation (paragraph 4)
        execute("UPDATE institutions SET sop_total = 72 WHERE name = 'College Alpha'")
        order = [r["name"] for r in sorted(query("SELECT * FROM institutions"), key=HEI.sop_order)]
        assert order == ["College Gamma", "College Beta", "College Alpha", "College Delta"]
        # marks of the six criteria of 26 October no longer count, and the form says so
        execute("UPDATE institutions SET sop_scores = ?, sop_total = NULL WHERE name = 'College Delta'",
                (json.dumps({"readiness": 25, "outreach": 20, "academic": 20, "geography": 15, "diversity": 10, "record": 10}),))
        delta = query("SELECT * FROM institutions WHERE name = 'College Delta'", one=True)
        assert HEI.sop_marks(delta) == {} and HEI.sop_legacy(delta)["record"] == 10
    page = _get(officer, f"/console/institutions/{ids['College Delta']}/marks")
    assert "Marks recorded on the six criteria of the letter of 26 October 2026" in page and "They no longer count" in page
    # the evaluation sheet has the six columns of the five criteria
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(officer.get("/console/institutions/evaluation.xlsx?state=Kerala").data)).active
    head = [c.value for c in next(ws.iter_rows())]
    assert "5A. Institutional diversity: institution type (max 10)" in head and "1. Institutional readiness (max 20)" in head


def test_the_old_marks_lose_their_total_once():
    from kts.db import execute, init_db, query
    app = _app()
    _apply(app.test_client(), name="College Omega", state="Kerala", aishe_code="", head_email="ho@x.example", coord_email="co@x.example")
    with app.app_context():
        execute("UPDATE institutions SET sop_scores = ?, sop_total = 90",
                (json.dumps({"readiness": 25, "outreach": 20, "academic": 20, "geography": 15, "diversity": 5, "record": 5}),))
        execute("DELETE FROM settings WHERE key = 'migrate.do_31oct.1155'")
    init_db(app)
    with app.app_context():
        row = query("SELECT sop_total, sop_scores FROM institutions", one=True)
        assert row["sop_total"] is None and json.loads(row["sop_scores"])["record"] == 5


def test_the_final_list_in_the_format_of_annexure_ii():
    from kts.db import query
    from openpyxl import load_workbook
    app = _app()
    for n, name in enumerate(("Selected College", "Waiting College")):
        _apply(app.test_client(), name=name, state="Kerala", aishe_code="KER123" if n == 0 else "", head_email=f"hx{n}@x.example",
               coord_email=f"cx{n}@x.example")
    with app.app_context():
        sid = query("SELECT id FROM institutions WHERE name = 'Selected College'", one=True)["id"]
    officer = _nodal(app, "nodal.kerala8@tests.example", ["Kerala"])
    officer.post("/console/institutions", data={"_csrf": _token(officer), "id": sid, "action": "accept"})
    listing = _get(officer, "/console/institutions?state=Kerala")
    assert ">Excel (Annexure-II)</a>" in listing and ">Excel (all institutions)</a>" in listing
    assert "Invite institutions to register (a list)" in listing and "The list identified by the Nodal Institution (Annexure-II)" not in listing
    r = officer.get("/console/institutions/annexure-ii-selected.xlsx")
    assert r.status_code == 200
    rows = [[c.value for c in row] for row in load_workbook(io.BytesIO(r.data)).active.iter_rows()]
    flat = [v for row in rows for v in row if v is not None]
    assert "ANNEXURE-II" in flat and "FORMAT FOR LIST OF INSTITUTIONS SELECTED BY THE NODAL HEI" in flat
    assert "State/UT: Kerala and Lakshadweep" in flat and "Name of Nodal HEI: Central University of Kerala" in flat
    assert "Number of institutions prescribed in Annexure-I: 21" in flat and "Total registrations received: 2" in flat
    assert "Number of institutions selected: 1" in flat
    head = next(row for row in rows if row and row[0] == "#")
    assert head[:8] == ["#", "Name of Institution", "District/City", "Type", "AISHE/Institution Code", "Coordinator Name", "Mobile No.", "Email ID"]
    assert "Selected College" in flat and "Waiting College" not in flat and "KER123" in flat
    # a Nodal Officer sees only the rows of Annexure-I of the account
    assert all("Assam" not in str(v) for v in flat)


def test_an_invited_institution_awaits_the_selection():
    from kts.db import query
    app = _portal()
    officer = _nodal(app, "nodal.kerala7@tests.example", ["Kerala"])
    data = "Name of Institution,Official Email ID,District/City\nInvited College,inv@college.example,Kochi\n".encode("utf-8")
    officer.post("/console/institutions/identified", data={"_csrf": _token(officer), "state": "Kerala", "file": (io.BytesIO(data), "list.csv")},
                 content_type="multipart/form-data")
    mail = _mails(app, "inv@college.example")[-1]
    assert mail["subject"] == "KTS 5.0: Invited College is invited to register" and "registration does not by itself confer selection" in mail["body"]
    with app.app_context():
        token = query("SELECT invite_token FROM institutions WHERE name = 'Invited College'", one=True)["invite_token"]
    client = app.test_client()
    client.get(f"/institutions/register?invite={token}")
    with client.session_transaction() as s:
        csrf = s["_csrf"]
        s["_captcha"] = "7"
    from test_institutions import FORM
    form = dict(FORM, _csrf=csrf, captcha="7", invite=token, name="Invited College", state="Kerala", coord_email="inv@college.example",
                head_email="head@college.example")
    r = client.post(f"/institutions/register?invite={token}", data=form)
    assert r.status_code == 302, r.get_data(as_text=True)[:1500]
    with app.app_context():
        assert query("SELECT status FROM institutions WHERE name = 'Invited College'", one=True)["status"] == "pending"
    received = _mails(app, "inv@college.example")[-1]
    assert "application of Invited College received" in received["subject"] and "registration does not by itself confer selection" in received["body"]


def test_the_mail_of_a_selected_institution_says_how_to_nominate():
    app = _portal()
    inst = _accepted(app)
    mail = _mails(app, inst["coord_email"])[-1]
    assert "is a Participating Institution" in mail["subject"]
    body = mail["body"]
    assert "/institution/login" in body and "/how-to-submit-the-student" in body and "submit the nomination there" in body
    assert "chooses" not in body and "approved by the Head of the Institution or an authorised committee" in body
    # the Nodal Officers are asked to record the marks and select, not to accept or decline
    with app.app_context():
        from kts.nodal import account_paragraph
        assert "record the marks of the Evaluation Committee on the criteria of Annexure-V" in account_paragraph(["Kerala"])


def test_the_selected_students_have_no_rank_and_no_waiting_list():
    from kts.db import execute, query
    from test_public_fixes import _staff
    app = _portal()
    inst = _accepted(app)
    coord, token = _coordinator(app, inst)
    page = coord.post("/institution/winner", data={"_csrf": token, "action": "enter", "name": "Priya Student", "email": "priya@student.example",
                                                    "mobile": "9123456780", "roll_no": "1", "course": "B.A.", "lang": "hi"},
                      follow_redirects=True).get_data(as_text=True)
    link = re.search(r"https?://[^\s<]+/register\?token=[A-Za-z0-9_-]+", page).group(0)
    _form, r = _register_with(app, link, dob="1984-05-06")   # 42 years old: no age limit since 1.2.155
    assert r.status_code == 302, r.get_data(as_text=True)[:1500]
    with app.app_context():
        execute("UPDATE applications SET status = 'verified'")
    admin = _staff(app, "root9@tests.example", "superadmin")
    page = admin.post("/console/selection", data={"_csrf": _token(admin), "action": "run"}, follow_redirects=True).get_data(as_text=True)
    assert "1 selected student," in page and "Waitlist" not in page and "Number to select" not in page
    with app.app_context():
        a = query("SELECT * FROM applications", one=True)
        assert a["status"] == "selected" and a["exam_rank"] is None
        assert [r["outcome"] for r in query("SELECT outcome FROM merit_list")] == ["selected"]
        from kts.admin import SETTING_GROUPS
        assert "merit.wait_count" not in [k for _g, items in SETTING_GROUPS for k, *_ in items]


def test_the_central_online_test_is_off():
    from kts.db import DEFAULT_SETTINGS, init_db, query, set_setting
    assert DEFAULT_SETTINGS["exam.open"] == "0"
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("exam.open", "auto")
        from kts.db import execute
        execute("DELETE FROM settings WHERE key = 'migrate.do_31oct.1155'")
    init_db(app)
    with app.app_context():
        assert query("SELECT value FROM settings WHERE key = 'exam.open'", one=True)["value"] == "0"
    assert "Institution-level assessments:" not in _get(app.test_client(), "/candidate/login?lang=en")


def test_the_schedule_and_the_milestones_have_the_nomination():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for k, v in (("reg.open", "0"), ("launch.on", "0"), ("reg.end", "2099-11-20")):
            set_setting(k, v)
    assert "Last date for the institutions to register their selected students" in _get(app.test_client(), "/schedule?lang=en")
    with app.test_request_context("/progress?lang=en"):
        from kts import dashboard as D
        marks = [m for m in D._pipeline()["milestones"] if m["key"] == "reg_close"]
        assert len(marks) == 1 and marks[0]["starts"] == "2099-11-20" and marks[0]["title_key"] == "timeline.reg_close"


def test_the_notices_follow_the_letter():
    from kts.db import DO_NOTICE, LAUNCH_NOTICE, LAUNCH_BODY_1154, execute, init_db, query
    assert "the institution submits the video recording of the presentation to CICT" in DO_NOTICE[1]
    assert "mobile 9790325518 / 9965734497" in DO_NOTICE[1] and "29 October" not in LAUNCH_NOTICE[1]
    app = make_app(ADMIN_PASSWORD=None)
    before = DO_NOTICE[1].replace("recorded; the institution submits the video recording of the presentation to CICT.", "recorded.") \
                         .replace("registrar@cict.in, mobile 9790325518 / 9965734497.", "registrar@cict.in.")
    with app.app_context():
        execute("UPDATE notices SET body = ? WHERE title = ?", (before, DO_NOTICE[0]))
        execute("UPDATE notices SET body = ? WHERE title = ?", (LAUNCH_BODY_1154, LAUNCH_NOTICE[0]))
        execute("DELETE FROM settings WHERE key = 'migrate.do_31oct.1155'")
    init_db(app)
    with app.app_context():
        assert query("SELECT body FROM notices WHERE title = ?", (DO_NOTICE[0],), one=True)["body"] == DO_NOTICE[1]
        launch = query("SELECT body FROM notices WHERE title = ?", (LAUNCH_NOTICE[0],), one=True)
        assert launch is None or launch["body"] == LAUNCH_NOTICE[1]
        circular = query("SELECT body FROM notices WHERE title = 'State/UT-wise list of Nodal Higher Educational Institutions'", one=True)
        assert "The Participating Institutions selected by the Nodal Institutions are listed" in circular["body"]


def test_the_guidelines_the_guide_and_the_drive_pages():
    from kts.i18n import CATALOG
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = _get(client, "/guidelines-for-nodal-institutions?lang=en")
    assert "Only the applications found eligible after scrutiny" in page and "<h2 id=\"ng-replace\">Replacement</h2>" in page
    assert "the next eligible institution from the approved reserve list may be included" in page
    assert "Dr. R. Bhuvaneshwari, Registrar, Central Institute of Classical Tamil (CICT), Chennai · registrar@cict.in · 9790325518 / 9965734497" in page
    guide = _get(client, "/how-to-take-part?lang=en")
    assert "After the nomination" in guide and "By 23 Nov 2026" in guide and "22 Oct 2026" not in guide
    assert "Assess your students by 23 Nov 2026" in guide
    for code, cat in CATALOG.items():
        assert "{" not in re.sub(r"\{(camp_to|hei_end|hei_select_end|date|link|questions|minutes|online_test|switch_on|excel|name|email|phone)\}", "",
                                 " ".join(cat[k] for k in ("guide.s2", "guide.i3_t", "ng.contact", "guide.i7"))), code
    assert CATALOG["en"]["join.geo"].startswith("Under Annexure-V, 20 of the 100 marks")
    assert CATALOG["en"]["tag.internship"] == "Research and academic engagement"


def test_the_sample_letter_dates_only_the_ministrys_steps():
    import zipfile
    from urllib.parse import quote
    client = make_app(ADMIN_PASSWORD=None).test_client()
    r = client.get(f"/nodal-institutions/letter.docx?state={quote('Tamil Nadu')}&lang=en")
    assert r.status_code == 200
    doc = zipfile.ZipFile(io.BytesIO(r.data)).read("word/document.xml").decode("utf-8")
    assert "Verification of the nominations by the Nodal Institution and CICT" not in doc
    assert "21 November" not in doc

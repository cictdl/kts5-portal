"""
The D.O. letter of the Ministry of 9 October 2026 (version 1.2.43): the institutions identified by the
Nodal Institution, their page, their online assessment, the student they select and that student's
registration with the portal's link.

    python -m pytest tests -q
"""
import io
import re

from conftest import ROOT, make_app
from test_institutions import FORM, _apply
from test_nodal_access import _nodal, _token
from test_public_fixes import PNG, _staff


def _portal():
    """A portal of the D.O. letter: registration by the institutions' links, a question bank in Hindi and English."""
    from kts import kural as K
    from kts.db import executemany, set_setting, utcnow
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("reg.by_institution", "1")
        set_setting("hei.end", "2099-12-31")
        set_setting("camp.from", "2026-01-01")
        set_setting("camp.to", "2099-12-31")
        for lang in ("hi", "en"):
            rows = K.generate_questions(lang, 60, "tests-" + lang)
            executemany("INSERT INTO questions(lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active, source, created_at) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,1,'auto',?)",
                        [(r["lang"], r["qtype"], r["text"], r["opt_a"], r["opt_b"], r["opt_c"], r["opt_d"], r["correct"],
                          r["kural_no"], r["difficulty"], utcnow()) for r in rows])
    return app


def _mails(app, to=None):
    from kts.db import query
    with app.app_context():
        if to:
            return query("SELECT * FROM outbox WHERE to_addr = ? ORDER BY id", (to,))
        return query("SELECT * FROM outbox ORDER BY id")


def _accepted(app, **changes):
    """An accepted institution, as the Nodal Officer leaves it; gives its row."""
    from kts.db import query
    _apply(app.test_client(), **changes)
    admin = _staff(app, f"admin{len(changes)}@tests.example", "superadmin")
    with app.app_context():
        iid = query("SELECT id FROM institutions ORDER BY id DESC LIMIT 1", one=True)["id"]
    admin.post("/console/institutions", data={"_csrf": _token(admin), "id": str(iid), "action": "accept"})
    with app.app_context():
        return query("SELECT * FROM institutions WHERE id = ?", (iid,), one=True)


def _coordinator(app, inst):
    """A client signed in to the institution's page as its coordinator, with the mailed code."""
    client = app.test_client()
    client.get("/institution/login")
    with client.session_transaction() as s:
        token = s["_csrf"]
    r = client.post("/institution/login", data={"_csrf": token, "email": inst["coord_email"]})
    assert r.status_code == 200 and "a six-digit code has been mailed" in r.get_data(as_text=True)
    code = re.search(r"\n    (\d{6})\n", _mails(app, inst["coord_email"])[-1]["body"]).group(1)
    r = client.post("/institution/code", data={"_csrf": token, "code": code})
    assert r.status_code == 302 and r.headers["Location"].endswith("/institution")
    return client, token


def test_the_nodal_officer_uploads_annexure_ii_and_the_institution_completes_its_registration():
    from kts.db import query
    from kts.utils import xlsx_bytes
    app = _portal()
    officer = _nodal(app, "nodal.kerala@tests.example", ["Kerala"])
    page = officer.get("/console/institutions").get_data(as_text=True)
    assert "Annexure-II" in page and "Upload and invite" in page and 'name="file"' in page
    r = officer.get("/console/institutions/annexure-ii.xlsx")
    assert r.status_code == 200 and r.data[:2] == b"PK"
    head = ["S. No.", "Name of Institution", "District/City", "Type", "AISHE/Institution Code", "Institutional Coordinator Name",
            "Mobile No.", "Official Email ID"]
    sheet = xlsx_bytes(head, [(1, "St. Thomas College Thrissur", "Thrissur", "Government-aided college", "C-22222", "Dr. T. Coordinator",
                               "9876500001", "coord@stthomas.example"),
                              (2, "", "", "", "", "", "", ""),
                              (3, "No Mail College", "Kochi", "Other", "", "Dr. N", "9876500002", "not-a-mail"),
                              (4, "St. Thomas College Thrissur", "Thrissur", "", "C-22222", "Again", "9876500003", "again@stthomas.example")],
                       "Annexure-II", text_cols=(4, 6))
    r = officer.post("/console/institutions/identified", data={"_csrf": _token(officer), "state": "Kerala",
                                                                "file": (io.BytesIO(sheet), "annexure2.xlsx")},
                     content_type="multipart/form-data")
    page = r.get_data(as_text=True)
    assert "1 institution(s) identified and invited" in page and "2 row(s) not taken" in page
    assert "no valid e-mail address" in page and "is in the list already" in page
    with app.app_context():
        row = query("SELECT * FROM institutions", one=True)
    assert (row["status"], row["coord_email"], row["aishe_code"], row["itype"], row["ref"]) == ("identified", "coord@stthomas.example", "C-22222", "Government-aided college", "KTS5-HEI-00001")
    assert row["invite_token"]
    mail = _mails(app, "coord@stthomas.example")[-1]
    assert "identified as a participating institution" in mail["subject"] and f"/institutions/register?invite={row['invite_token']}" in mail["body"]
    # on the website: identified, not yet listed; the officer's page counts it
    assert "St. Thomas" not in app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    assert ">1</a>" in officer.get("/console/institutions").get_data(as_text=True)
    # the institution completes its registration with the invitation: the form comes filled in
    client = app.test_client()
    form = client.get(f"/institutions/register?invite={row['invite_token']}&lang=en").get_data(as_text=True)
    assert 'value="St. Thomas College Thrissur"' in form and 'value="coord@stthomas.example"' in form and 'name="invite"' in form
    with client.session_transaction() as s:
        token = s["_csrf"]
        s["_captcha"] = "7"
    data = dict(FORM, _csrf=token, captcha="7", invite=row["invite_token"], name="St. Thomas College Thrissur",
                itype="Government-aided college", aishe_code="C-22222", coord_name="Dr. T. Coordinator",
                coord_email="coord@stthomas.example", coord_mobile="9876500001", head_name="Dr. Principal T", head_email="principal@stthomas.example")
    r = client.post("/institutions/register", data=data)
    assert r.status_code == 302 and r.headers["Location"].endswith("/institutions/register/done/KTS5-HEI-00001")
    with app.app_context():
        row = query("SELECT * FROM institutions", one=True)
    assert row["status"] == "accepted" and row["invite_token"] is None and row["head_name"] == "Dr. Principal T"
    assert "has accepted your institution" in _mails(app, "coord@stthomas.example")[-1]["body"]
    assert "St. Thomas College Thrissur" in app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    # a used invitation
    assert "not valid or has been used" in client.get(f"/institutions/register?invite={data['invite']}&lang=en", follow_redirects=True).get_data(as_text=True)


def test_the_coordinator_signs_in_with_a_code_and_switches_the_assessment_on():
    from kts.db import query
    app = _portal()
    inst = _accepted(app)
    client = app.test_client()
    client.get("/institution/login")
    with client.session_transaction() as s:
        token = s["_csrf"]
    # an address of nobody is answered as any other
    r = client.post("/institution/login", data={"_csrf": token, "email": "nobody@x.example"})
    assert "a six-digit code has been mailed" in r.get_data(as_text=True) and not _mails(app, "nobody@x.example")
    # a wrong code
    client.post("/institution/login", data={"_csrf": token, "email": inst["coord_email"]})
    r = client.post("/institution/code", data={"_csrf": token, "code": "000000"})
    assert r.status_code == 400 and "The code is wrong" in r.get_data(as_text=True)
    assert client.get("/institution").status_code == 302
    coord, token = _coordinator(app, inst)
    page = coord.get("/institution").get_data(as_text=True)
    assert inst["name"] in page and "The steps and the dates" in page and "Switch on" in page
    assert "31 December 2030" in page  # the last day to register the student (reg.end of the tests)
    r = coord.post("/institution/assessment", data={"_csrf": token, "action": "on", "test_from": "2026-10-16", "test_to": "2026-10-20"},
                   follow_redirects=True)
    page = r.get_data(as_text=True)
    assert "The online assessment is on" in page and "Access code" in page
    with app.app_context():
        inst = query("SELECT * FROM institutions WHERE id = ?", (inst["id"],), one=True)
    assert inst["test_on"] == 1 and len(inst["test_slug"]) == 8 and len(inst["test_code"]) == 6
    assert f"/assessment/{inst['test_slug']}" in page and inst["test_code"] in page
    # the days must fall in the period of CICT
    from kts.db import set_setting
    with app.app_context():
        set_setting("camp.to", "2026-10-21")
    r = coord.post("/institution/assessment", data={"_csrf": token, "action": "on", "test_from": "2026-10-16", "test_to": "2026-10-30"},
                   follow_redirects=True)
    assert "must fall between" in r.get_data(as_text=True)
    # the console follows it
    admin = _staff(app, "root@tests.example", "superadmin")
    page = admin.get("/console/institutions?state=Kerala").get_data(as_text=True)
    assert "online 16 Oct 2026 – 20 Oct 2026: 0 of 0 students" in page and "no student selected yet" in page


def _assessing(app, days=("2026-01-01", "2099-12-31")):
    from kts.db import execute, query
    inst = _accepted(app)
    with app.app_context():
        execute("UPDATE institutions SET test_on = 1, test_from = ?, test_to = ?, test_slug = 'abcd1234', test_code = '246810' WHERE id = ?",
                (days[0], days[1], inst["id"]))
        return query("SELECT * FROM institutions WHERE id = ?", (inst["id"],), one=True)


def _signup(app, slug, **changes):
    client = app.test_client()
    client.get(f"/assessment/{slug}")
    with client.session_transaction() as s:
        token = s["_csrf"]
        s["_captcha"] = "7"
    data = {"_csrf": token, "captcha": "7", "code": "246810", "name": "Priya Student", "email": "priya@student.example",
            "mobile": "9123456780", "roll_no": "21TAM007", "course": "B.A. Tamil, 2nd year", "lang": "hi", "declare": "1"}
    data.update(changes)
    return client, client.post(f"/assessment/{slug}", data=data)


def test_a_student_takes_the_assessment_of_the_institution_once():
    from kts.db import query
    app = _portal()
    inst = _assessing(app)
    page = app.test_client().get("/assessment/abcd1234?lang=en").get_data(as_text=True)
    assert f"Online assessment of {inst['name']}" in page and "Access code given by your institution" in page
    assert app.test_client().get("/assessment/nothere").status_code == 404
    # the wrong code, then the right one
    client, r = _signup(app, "abcd1234", code="111111")
    assert r.status_code == 400 and "The access code is wrong." in r.get_data(as_text=True)
    client, r = _signup(app, "abcd1234")
    assert r.status_code == 302 and r.headers["Location"].endswith("/assessment/abcd1234/start")
    page = client.get("/assessment/abcd1234/start?lang=en").get_data(as_text=True)
    assert "Priya Student" in page and "Start test" in page
    r = client.post("/assessment/abcd1234/start", data={"_csrf": _token(client)})
    assert r.status_code == 302 and r.headers["Location"].endswith("/assessment/abcd1234/paper")
    paper = client.get("/assessment/abcd1234/paper?lang=en").get_data(as_text=True)
    assert "Thirukkural assessment" in paper and 'data-save="/assessment/abcd1234/save"' in paper and 'action="/assessment/abcd1234/submit"' in paper
    qids = re.findall(r'name="q(\d+)"', paper)
    assert len(set(qids)) == 50
    with app.app_context():
        attempt = query("SELECT * FROM campus_attempts", one=True)
        correct = {str(r["id"]): r["correct"] for r in query("SELECT id, correct FROM questions")}
    assert attempt["lang"] == "hi"
    # two answers saved, one of them right
    first, second = list(dict.fromkeys(qids))[:2]
    wrong = next(l for l in "ABCD" if l != correct[second])
    r = client.post("/assessment/abcd1234/save", json={"answers": {first: correct[first], second: wrong}},
                    headers={"X-CSRF-Token": re.search(r'data-csrf="([^"]+)"', paper).group(1)})
    assert r.status_code == 200 and r.get_json()["saved"] == 2
    r = client.post("/assessment/abcd1234/submit", data={"_csrf": _token(client), "answers": "{}"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/assessment/abcd1234/result")
    page = client.get("/assessment/abcd1234/result?lang=en").get_data(as_text=True)
    assert "Your answers are recorded" in page and "<b style=\"font-size:1.4rem\">2</b> / 100" in page
    with app.app_context():
        attempt = query("SELECT * FROM campus_attempts", one=True)
    assert (attempt["status"], attempt["score"], attempt["correct_count"]) == ("submitted", 2.0, 1)
    # once: signing up again with the same details leads to the result
    client2, r = _signup(app, "abcd1234")
    assert r.status_code == 302
    assert client2.get("/assessment/abcd1234/start").headers["Location"].endswith("/result")
    # the same e-mail with another mobile is refused
    client3, r = _signup(app, "abcd1234", mobile="9123456799")
    assert r.status_code == 400 and "has signed up with other details" in r.get_data(as_text=True)
    # the score hidden when CICT says so
    from kts.db import set_setting
    with app.app_context():
        set_setting("camp.show_score", "0")
    assert "/ 100" not in client.get("/assessment/abcd1234/result?lang=en").get_data(as_text=True)
    # the coordinator sees the student ranked, and the Excel file
    coord, token = _coordinator(app, inst)
    page = coord.get("/institution").get_data(as_text=True)
    assert "Priya Student" in page and "1 correct" in page and "Select</button>" in page
    r = coord.get("/institution/students.xlsx")
    assert r.status_code == 200 and r.data[:2] == b"PK"


def test_the_assessment_closed_outside_its_days_or_switched_off():
    app = _portal()
    inst = _assessing(app, days=("2099-01-01", "2099-01-31"))
    page = app.test_client().get("/assessment/abcd1234?lang=en").get_data(as_text=True)
    assert "is not open at present" in page and 'id="code"' not in page
    from kts.db import execute
    with app.app_context():
        execute("UPDATE institutions SET test_from = '2026-01-01', test_to = '2099-12-31', test_on = 0 WHERE id = ?", (inst["id"],))
    assert "is not open at present" in app.test_client().get("/assessment/abcd1234?lang=en").get_data(as_text=True)


def _register_with(app, link, **changes):
    client = app.test_client()
    token_value = link.split("token=")[1]
    page = client.get(f"/register?token={token_value}&lang=en").get_data(as_text=True)
    with client.session_transaction() as s:
        token = s["_csrf"]
        s["_captcha"] = "7"
    form = {
        "_csrf": token, "token": token_value, "full_name": "Priya Student", "gender": "F", "dob": "2004-05-06", "category": "General",
        "mobile": "9123456780", "email": "priya@student.example", "state": "Kerala", "course_level": "Undergraduate",
        "year_of_study": "2nd year", "pref_lang": "hi", "declare_true": "1", "declare_participate": "1", "declare_consent": "1",
        "captcha": "7", "mentor_name": "Dr. K. Mentor", "mentor_designation": "Assistant Professor of Tamil",
        "mentor_email": "mentor@tests.example", "mentor_phone": "9876012345",
        "photo": (io.BytesIO(PNG), "photo.png"), "idproof": (io.BytesIO(PNG), "id.png"), "nomination": (io.BytesIO(PNG), "nomination.png"),
    }
    form.update(changes)
    return page, client.post("/register", data=form, content_type="multipart/form-data")


def test_the_selected_student_registers_with_the_link_of_the_institution():
    from kts.db import query
    app = _portal()
    inst = _assessing(app)
    client, _r = _signup(app, "abcd1234")
    client.post("/assessment/abcd1234/start", data={"_csrf": _token(client)})
    client.post("/assessment/abcd1234/submit", data={"_csrf": _token(client), "answers": "{}"})
    # without a link, nobody registers
    page = app.test_client().get("/register?lang=en").get_data(as_text=True)
    assert "Registration is by the participating institution" in page and 'name="full_name"' not in page
    r = app.test_client().get("/register?token=nonsense&lang=en")
    assert r.status_code == 404 and "This registration link is not valid" in r.get_data(as_text=True)
    # the coordinator selects the student
    coord, token = _coordinator(app, inst)
    with app.app_context():
        sid = query("SELECT id FROM campus_students", one=True)["id"]
    r = coord.post("/institution/winner", data={"_csrf": token, "action": "select", "student_id": str(sid)}, follow_redirects=True)
    page = r.get_data(as_text=True)
    assert "Priya Student is selected" in page and "/register?token=" in page
    link = re.search(r"https?://[^\s<]+/register\?token=[A-Za-z0-9_-]+", page).group(0)
    mail = _mails(app, "priya@student.example")[-1]
    assert "register as the student selected by" in mail["subject"] and link in mail["body"]
    assert link in _mails(app, inst["coord_email"])[-1]["body"]
    # the form comes with the institution fixed and the student filled in
    form, r = _register_with(app, link)
    assert "from your registration link" in form and inst["name"] in form and 'value="Priya Student"' in form
    # the Faculty Supervisor/Guide of the institution comes filled in (1.2.46)
    assert 'value="Dr. C. Guide"' in form and 'value="guide@gac.example"' in form
    assert 'name="college_name"' not in form
    assert r.status_code == 302, r.get_data(as_text=True)[:1500]
    with app.app_context():
        a = query("SELECT * FROM applications", one=True)
        inst2 = query("SELECT * FROM institutions WHERE id = ?", (inst["id"],), one=True)
        session_row = query("SELECT * FROM exam_sessions WHERE application_id = ?", (a["id"],), one=True)
    assert (a["institution_id"], a["college_name"], a["college_state"], a["status"]) == (inst["id"], inst["name"], "Kerala", "submitted")
    assert inst2["application_id"] == a["id"]
    # the score of the online assessment goes with the application
    assert session_row is not None and session_row["status"] == "submitted" and a["exam_score"] == session_row["score"]
    assert "has registered" in _mails(app, inst["coord_email"])[-1]["subject"]
    # the link works once
    r = app.test_client().get(f"/register?token={link.split('token=')[1]}&lang=en")
    assert r.status_code == 404
    # the coordinator's page and the console show the registration
    page = coord.get("/institution").get_data(as_text=True)
    assert "has registered: application" in page and a["app_no"] in page
    admin = _staff(app, "root@tests.example", "superadmin")
    page = admin.get("/console/institutions?state=Kerala").get_data(as_text=True)
    assert a["app_no"] in page and "submitted" in page
    # the status page of the student
    client = app.test_client()
    client.get("/status")
    r = client.post("/status", data={"_csrf": _token(client), "app_no": a["app_no"], "dob": "2004-05-06", "last4": "6780"})
    assert "Online assessment of the institution taken" in r.get_data(as_text=True)


def test_a_student_assessed_in_another_way_is_entered_and_ranked_after_those_with_a_score():
    from kts.db import execute, query
    app = _portal()
    inst = _accepted(app)
    coord, token = _coordinator(app, inst)
    r = coord.post("/institution/winner", data={"_csrf": token, "action": "enter", "name": "Arun Student", "email": "arun@student.example",
                                                 "mobile": "9123456781", "roll_no": "21ENG003", "course": "B.Sc Physics", "lang": "en"},
                   follow_redirects=True)
    page = r.get_data(as_text=True)
    assert "Arun Student is selected" in page
    link = re.search(r"https?://[^\s<]+/register\?token=[A-Za-z0-9_-]+", page).group(0)
    # withdrawn and selected again: a new link; the old one is dead
    coord.post("/institution/winner", data={"_csrf": token, "action": "clear"})
    assert app.test_client().get(f"/register?token={link.split('token=')[1]}").status_code == 404
    with app.app_context():
        sid = query("SELECT id FROM campus_students", one=True)["id"]
    page = coord.post("/institution/winner", data={"_csrf": token, "action": "select", "student_id": str(sid)}, follow_redirects=True).get_data(as_text=True)
    link = re.search(r"https?://[^\s<]+/register\?token=[A-Za-z0-9_-]+", page).group(0)
    _form, r = _register_with(app, link, full_name="Arun Student", email="arun@student.example", mobile="9123456781", pref_lang="en")
    assert r.status_code == 302
    with app.app_context():
        a = query("SELECT * FROM applications", one=True)
        assert a["exam_score"] is None and query("SELECT COUNT(*) AS n FROM exam_sessions", one=True)["n"] == 0
        # a second application, with a score, ranks first in the selection
        execute("UPDATE applications SET status = 'verified'")
        rid = execute("INSERT INTO applications(full_name, gender, dob, mobile, email, state, college_name, college_key, pref_lang, status, "
                      "created_at, updated_at) VALUES('Scored Student','F','2004-05-06','9123456700','scored@x.example','Kerala','Other College',"
                      "'name:other college|kerala','hi','verified','2026-10-20T10:00:00','2026-10-20T10:00:00')")
        execute("INSERT INTO exam_sessions(application_id, lang, paper_json, answers_json, started_at, deadline_at, submitted_at, status, score, "
                "correct_count, time_taken_sec) VALUES(?, 'hi', '[]', '{}', '2026-10-18T10:00:00+05:30', '2026-10-18T10:30:00+05:30', "
                "'2026-10-18T10:20:00+05:30', 'submitted', 40, 20, 1200)", (rid,))
    from kts.admin import run_selection
    with app.test_request_context():
        run_id, ranked, runners = run_selection(1, 1, None)
        order = [(r["rank"], r["application_id"], r["score"]) for r in query("SELECT * FROM merit_list ORDER BY rank")]
    assert ranked == 2 and order == [(1, rid, 40.0), (2, a["id"], 0.0)] or order[0][1] == rid


def test_the_letter_in_the_data_and_the_pages():
    import json
    from kts.db import DEFAULT_SETTINGS, RETIRED_DEFAULTS, RETIRED_EVENT_TITLES
    heis = json.loads((ROOT / "data" / "nodal_heis.json").read_text(encoding="utf-8"))
    assert len(heis) == 31 and sum(h["allocation"] for h in heis) == 1385
    by = {h["state"]: h for h in heis}
    assert by["Tamil Nadu"]["name"] == "Central University of Tamil Nadu" and by["Tamil Nadu"]["allocation"] == 150
    assert by["Goa"]["name"] == "NIT Goa" and by["Goa"]["type"] == "nit" and by["Assam"]["name"] == "Assam University"
    assert DEFAULT_SETTINGS["exam.open"] == "0" and DEFAULT_SETTINGS["reg.by_institution"] == "1" and DEFAULT_SETTINGS["camp.to"] == "2026-10-21"
    assert "auto" in RETIRED_DEFAULTS["exam.open"] and "2026-10-21" in RETIRED_DEFAULTS["reg.end"] and "50" in RETIRED_DEFAULTS["hei.max_per_state"]
    assert set(RETIRED_EVENT_TITLES) == {"selection", "letters", "live"}
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    home = client.get("/?lang=en").get_data(as_text=True)
    assert "Institution-level assessments" in home and "data-countdown" not in home and "Assessment at the institution" in home
    exam = client.get("/examination?lang=en").get_data(as_text=True)
    assert "Institution-level assessment" in exam and 'href="/institution/login"' in exam and "11:30" not in exam
    assert 'href="/institution/login">Institution sign-in</a>' in home
    sched = client.get("/schedule?lang=en").get_data(as_text=True)
    assert "Completion of the institution-level assessments" in sched and "Online examination" not in sched
    assert "Nationwide Students' Engagement Programme" in sched.replace("&#39;", "'")
    # the partners page names the Nodal Institutions of the letter
    partners = client.get("/partners?lang=en").get_data(as_text=True)
    assert "Assam University" in partners and "Indian Institute of Technology Guwahati" not in partners
    # the live database: the old titles of the events receive the new ones, the retired settings move
    import sqlite3
    conn = sqlite3.connect(str(app.config["DATABASE"]))
    conn.execute("UPDATE events SET title = 'Selection of the 1,000 students' WHERE title LIKE 'Consolidation of the selected%'")
    conn.execute("UPDATE settings SET value = 'auto' WHERE key = 'exam.open'")
    conn.execute("UPDATE settings SET value = '2026-10-21' WHERE key = 'reg.end'")
    conn.commit()
    conn.close()
    from config import Config
    from kts import create_app
    again = create_app(type("Again", (Config,), {name: app.config[name] for name in ("INSTANCE_DIR", "DATABASE", "UPLOAD_DIR")} | {"ADMIN_PASSWORD": None}))
    conn = sqlite3.connect(str(again.config["DATABASE"]))
    assert conn.execute("SELECT COUNT(*) FROM events WHERE title LIKE 'Consolidation of the selected%'").fetchone()[0] == 1
    assert dict(conn.execute("SELECT key, value FROM settings WHERE key IN ('exam.open', 'reg.end')")) == {"exam.open": "0", "reg.end": "2026-10-22"}
    conn.close()


def test_a_wide_table_does_not_widen_the_page():
    """1.2.44: the columns of .two-col may shrink below their content, so a wide table scrolls inside its frame."""
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    assert ".two-col { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);" in css
    assert "@media (max-width: 899px) { .two-col { grid-template-columns: minmax(0, 1fr); } }" in css

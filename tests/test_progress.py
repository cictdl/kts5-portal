"""
The progress of the participating institutions in the week of the assessments, and the reminders to
those that are behind (version 1.2.52).

    python -m pytest tests -q
"""
from datetime import date, datetime

from conftest import add_candidates, make_app
from test_nodal_access import _nodal, _token
from test_public_fixes import _staff


def _at(day, hour=8, minute=0):
    from kts.utils import IST
    return datetime(2026, 10, day, hour, minute, tzinfo=IST)


def _inst(app, name, state="Kerala", status="accepted", **cols):
    """An institution written straight into the database; gives its id."""
    from kts.db import execute, utcnow
    from kts.heis import ref_of
    slug = name.lower().replace(" ", ".")
    with app.app_context():
        iid = execute("INSERT INTO institutions(name, itype, state, district, inst_key, head_name, head_email, coord_name, coord_email, "
                      "coord_mobile, status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (name, "College", state, "District", f"name:{slug}|{state}", "Dr. Head", f"head@{slug}.example",
                       "Coordinator " + name, f"coord@{slug}.example", "9000000001", status, utcnow(), utcnow()))
        execute("UPDATE institutions SET ref = ? WHERE id = ?", (ref_of(iid), iid))
        if cols:
            execute(f"UPDATE institutions SET {', '.join(k + ' = ?' for k in cols)} WHERE id = ?", (*cols.values(), iid))
    return iid


def _student(app, iid, name, tested=False):
    from kts.db import execute, utcnow
    with app.app_context():
        sid = execute("INSERT INTO campus_students(institution_id, name, email, mobile, lang, created_at) VALUES(?,?,?,?,?,?)",
                      (iid, name, f"{name.lower().replace(' ', '.')}@students.example", "9111111111", "hi", utcnow()))
        if tested:
            execute("INSERT INTO campus_attempts(student_id, lang, paper_json, started_at, deadline_at, submitted_at, status, score) "
                    "VALUES(?,?,?,?,?,?,?,?)", (sid, "hi", "[]", utcnow(), utcnow(), utcnow(), "submitted", 80))
    return sid


def _world():
    """
    Kerala: one institution at each stage, a pending and a declined one; Tamil Nadu: one that has
    done nothing. Registration ends on 22 October 2026, as on the portal.
    """
    from kts.db import execute, query, set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("reg.end", "2026-10-22")
    ids = {"none": _inst(app, "Idle College"),
           "testing": _inst(app, "Testing College", test_on=1, test_from="2026-10-15", test_to="2026-10-21", test_slug="testing1", test_code="111111"),
           "selected": _inst(app, "Selected College", test_on=1, test_from="2026-10-15", test_to="2026-10-21", test_slug="select11", test_code="222222"),
           "registered": _inst(app, "Registered College"),
           "verified": _inst(app, "Verified College"),
           "tn": _inst(app, "Madurai College", state="Tamil Nadu")}
    _inst(app, "Pending College", status="pending")
    _inst(app, "Declined College", status="declined")
    _student(app, ids["testing"], "Asha Nair", tested=True)
    _student(app, ids["testing"], "Binu Raj", tested=True)
    _student(app, ids["testing"], "Chitra Menon")
    winner = _student(app, ids["selected"], "Devi Pillai", tested=True)
    add_candidates(app, 2)
    with app.app_context():
        execute("UPDATE institutions SET winner_id = ?, reg_token = 'tok-selected' WHERE id = ?", (winner, ids["selected"]))
        apps = [r["id"] for r in query("SELECT id FROM applications ORDER BY id")]
        execute("UPDATE applications SET status = 'verified' WHERE id = ?", (apps[1],))
        for key, aid in (("registered", apps[0]), ("verified", apps[1])):
            sid = _student(app, ids[key], "Winner " + key)
            execute("UPDATE institutions SET winner_id = ?, application_id = ? WHERE id = ?", (sid, aid, ids[key]))
    return app, ids


def _mails(app):
    from kts.db import query
    with app.app_context():
        return query("SELECT * FROM outbox ORDER BY id")


def test_the_stage_of_each_institution_and_the_figures_of_each_state():
    from kts import progress
    app, ids = _world()
    with app.app_context():
        rows = progress.institutions()
        assert {r["id"]: r["stage"] for r in rows} == {ids[k]: ("none" if k == "tn" else k) for k in ids}
        b = progress.board()
    kerala = next(s for s in b["states"] if s["state"] == "Kerala")
    assert kerala == {"state": "Kerala", "allocation": 45, "participating": 5, "testing": 2, "signed_up": 6, "tested": 3,
                      "selected": 3, "registered": 2, "verified": 1, "not_selected": 2, "not_registered": 1}
    # the States/UTs of Annexure-I in its order, each one even without institutions yet
    assert b["states"][0]["state"] == "Andhra Pradesh" and b["states"][0]["participating"] == 0 and len(b["states"]) == 31
    assert b["total"]["participating"] == 6 and b["total"]["allocation"] == 1385 and b["total"]["not_selected"] == 3
    with app.app_context():
        assert [s["state"] for s in progress.board(["Kerala"])["states"]] == ["Kerala"]
        assert progress.board(["Ladakh"])["states"] == [{"state": "Ladakh", "allocation": None, **progress._empty()}]


def test_which_reminder_is_due():
    from kts import progress
    app, _ids = _world()
    with app.app_context():
        due = lambda stage, day: progress.due_kind(stage, date(2026, 10, day))  # noqa: E731
        assert due("none", 16) == (None, [])
        assert due("none", 17) == ("start", ["start"]) and due("testing", 17) == (None, [])
        assert due("none", 20) == ("select", ["start", "select"]) and due("testing", 20) == ("select", ["select"])
        assert due("selected", 20) == (None, []) and due("selected", 21) == ("register", ["register"])
        assert due("registered", 21) == (None, []) and due("verified", 22) == (None, [])
        assert due("none", 23) == (None, []) and due("selected", 23) == (None, [])


def test_the_morning_reminders_go_once_each():
    from kts import progress
    from kts.db import query, set_setting
    app, ids = _world()
    assert progress.daily(app, _at(16)) == 0
    assert progress.daily(app, _at(17, 7, 59)) == 0
    assert progress.daily(app, _at(17)) == 2
    mails = _mails(app)
    assert sorted(m["to_addr"] for m in mails) == ["coord@idle.college.example", "coord@madurai.college.example"]
    idle = next(m for m in mails if m["to_addr"] == "coord@idle.college.example")
    assert idle["subject"] == "Reminder – KTS 5.0: assess your students and select one by 21 October 2026 – Idle College"
    assert "Dear Coordinator Idle College," in idle["body"] and "/institution/login" in idle["body"]
    assert "The Nodal Institution of Kerala, Central University of Kerala, coordinates" in idle["body"]
    assert "on or before 22 October 2026" in idle["body"] and "/contact" in idle["body"]
    # once a day, and once each
    assert progress.daily(app, _at(17, 9)) == 0 and progress.daily(app, _at(18)) == 0 and len(_mails(app)) == 2
    # 20 October: to select, to those that have done nothing and to the one assessing; the Head in copy
    assert progress.daily(app, _at(20)) == 3
    fresh = _mails(app)[2:]
    assert len(fresh) == 6 and sum(1 for m in fresh if m["to_addr"].startswith("head@")) == 3
    testing = next(m for m in fresh if m["to_addr"] == "coord@testing.college.example")
    assert testing["subject"] == "Reminder – KTS 5.0: select your student by 21 October 2026 – Testing College"
    assert "open from 15 October 2026 to 21 October 2026: 3 students signed up, 2 tested" in testing["body"]
    head = next(m for m in fresh if m["to_addr"] == "head@testing.college.example")
    assert head["body"].startswith("Dear Dr. Head,\n\nFor your information: the reminder below has gone to the Institutional Coordinator")
    # 21 October: the selected student who has not registered, and the coordinator, with the personal link
    assert progress.daily(app, _at(21)) == 1
    last = _mails(app)[8:]
    assert sorted(m["to_addr"] for m in last) == ["coord@selected.college.example", "devi.pillai@students.example"]
    assert all("Devi Pillai has not registered yet – register by 22 October 2026" in m["subject"] for m in last)
    assert all("/register?token=tok-selected" in m["body"] for m in last)
    # after the last day of registration, and when switched off: none
    assert progress.daily(app, _at(23)) == 0
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM institution_reminders", one=True)["n"] == 6
        assert progress.sent_counts() == {"start": 2, "select": 3, "register": 1, "manual": 0}
        set_setting("remind.on", "0")
        set_setting("remind.sent_day", "")
    assert progress.daily(app, _at(21, 10)) == 0


def test_where_two_are_due_one_morning_only_the_later_goes():
    from kts import progress
    app, ids = _world()
    assert progress.daily(app, _at(20)) == 3
    subjects = [m["subject"] for m in _mails(app) if m["to_addr"].startswith("coord@")]
    assert len(subjects) == 3 and all("select your student" in s for s in subjects)
    with app.app_context():
        assert progress.sent_counts() == {"start": 2, "select": 3, "register": 0, "manual": 0}


def test_the_page_for_cict_and_for_the_nodal_officer():
    from kts.db import query
    app, ids = _world()
    admin = _staff(app, "progress-admin@tests.example", role="admin")
    page = admin.get("/console/progress").get_data(as_text=True)
    assert "Progress of the institutions" in page and "State/UT by State/UT" in page and "Madurai College" in page
    assert "Idle College" in page and "Selected College" in page and "Verified College" not in page   # behind only
    assert "Remind the 4 institution(s) behind now" in page and 'href="/console/progress"' in page
    all_rows = admin.get("/console/progress?stage=all").get_data(as_text=True)
    assert "Verified College" in all_rows and "Pending College" not in all_rows and "Declined College" not in all_rows
    assert "Testing College" in admin.get("/console/progress?stage=testing").get_data(as_text=True)
    officer = _nodal(app, "nodal.kerala.progress@tests.example", ["Kerala"])
    mine = officer.get("/console/progress").get_data(as_text=True)
    assert "Idle College" in mine and "Madurai College" not in mine and "You see the institutions of <b>Kerala</b>" in mine
    from kts.utils import xlsx_rows
    sheet = xlsx_rows(officer.get("/console/progress.xlsx").data)
    assert sheet[0][:5] == ["State/UT", "Reference", "Institution", "District/City", "Stage"]
    assert sorted(r[2] for r in sheet[1:]) == [
        "Idle College", "Registered College", "Selected College", "Testing College", "Verified College"]
    # the Nodal Officer reminds the institutions of the State/UT, not those of another
    assert officer.post("/console/progress", data={"_csrf": _token(officer), "state": "Tamil Nadu"}).status_code == 404
    r = officer.post("/console/progress", data={"_csrf": _token(officer), "state": "Kerala"}, follow_redirects=True)
    assert "A reminder is mailed to 3 institution(s) that are behind." in r.get_data(as_text=True)
    subjects = {m["to_addr"]: m["subject"] for m in _mails(app)}
    assert subjects["coord@idle.college.example"].startswith("Reminder – KTS 5.0: select your student")
    assert subjects["coord@selected.college.example"].startswith("Reminder – KTS 5.0: Devi Pillai has not registered yet")
    assert "coord@madurai.college.example" not in subjects
    again = officer.post("/console/progress", data={"_csrf": _token(officer), "state": "Kerala"}, follow_redirects=True)
    assert "No institution is behind, or each has had a reminder today." in again.get_data(as_text=True)
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM institution_reminders WHERE kind LIKE 'manual:%'", one=True)["n"] == 3
        assert query("SELECT detail FROM audit_log WHERE action = 'institutions_reminded'", one=True)["detail"].startswith('{"count": 3')
    assert "1 · last" in officer.get("/console/progress?stage=all").get_data(as_text=True)
    # a viewer sees the page, without the button
    viewer = _staff(app, "progress-viewer@tests.example", role="viewer")
    seen = viewer.get("/console/progress")
    assert seen.status_code == 200 and "Remind the" not in seen.get_data(as_text=True)
    assert viewer.post("/console/progress", data={"_csrf": _token(viewer)}).status_code == 403


def test_the_dashboard_and_the_settings():
    app, _ids = _world()
    admin = _staff(app, "progress-dash@tests.example", role="admin")
    dash = admin.get("/console/").get_data(as_text=True)
    assert "6 participating: 2 assessing online, 3 selected a student, 2 registered, 1 verified" in dash
    assert "Assessed by institutions" in dash and ">Online test<" not in dash and 'href="/console/progress"' in dash
    settings = admin.get("/console/settings").get_data(as_text=True)
    for key in ("remind.on", "remind.test_by", "remind.select_by", "remind.register_by"):
        assert f'name="{key}"' in settings

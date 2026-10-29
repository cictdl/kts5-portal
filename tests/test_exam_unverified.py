"""
The central test for registered students not yet verified (version 1.2.119, Console > Settings exam.unverified, on): a
student whose application awaits the Nodal Officer may take it; one not accepted or withdrawn may not; with the switch off
only verified students may, as before. The selection counts verified students only either way.

    python -m pytest tests -q
"""
from conftest import add_candidates, make_app
from test_exam_modalities import _attempt, _signed_in


def _portal(statuses):
    """A portal with a question bank in Hindi, the window forced open, one student of each status."""
    from kts import kural as K
    from kts.db import execute, executemany, set_setting, utcnow
    app = make_app(ADMIN_PASSWORD=None)
    students = add_candidates(app, len(statuses))
    with app.app_context():
        rows = K.generate_questions("hi", 60, "tests")
        executemany("INSERT INTO questions(lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active, source, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,1,'auto',?)",
                    [(r["lang"], r["qtype"], r["text"], r["opt_a"], r["opt_b"], r["opt_c"], r["opt_d"], r["correct"],
                      r["kural_no"], r["difficulty"], utcnow()) for r in rows])
        for who, status in zip(students, statuses):
            execute("UPDATE applications SET status = ? WHERE app_no = ?", (status, who["app_no"]))
        set_setting("exam.open", "1")
    return app, students


def test_a_registered_student_not_yet_verified_takes_the_test():
    from kts.db import get_setting
    app, students = _portal(["submitted"])
    with app.app_context():
        assert get_setting("exam.unverified") == "1"
    client, token = _signed_in(app, students[0])
    home = client.get("/candidate/").get_data(as_text=True)
    assert 'href="/candidate/exam"' in home and 'href="/candidate/admit-card"' in home
    assert client.get("/candidate/admit-card").status_code == 200
    page = client.get("/candidate/exam").get_data(as_text=True)
    assert "not yet verified" not in page and 'type="submit">▶' in page
    r = client.post("/candidate/exam", data={"_csrf": token})
    assert r.status_code == 302 and r.headers["Location"].endswith("/candidate/exam/paper")
    assert _attempt(app, students[0])["status"] == "in_progress"


def test_not_accepted_or_withdrawn_may_not():
    app, students = _portal(["rejected", "withdrawn"])
    for who, label in zip(students, ("Not accepted", "Withdrawn")):
        client, token = _signed_in(app, who)
        assert 'href="/candidate/exam"' not in client.get("/candidate/").get_data(as_text=True)
        page = client.get("/candidate/exam").get_data(as_text=True)
        assert f'<div class="alert warning">{label}</div>' in page and "▶" not in page
        r = client.post("/candidate/exam", data={"_csrf": token}, follow_redirects=True)
        assert label in r.get_data(as_text=True) and _attempt(app, who) is None


def test_with_the_switch_off_verified_students_only():
    from kts.db import set_setting
    app, students = _portal(["submitted", "verified"])
    with app.app_context():
        set_setting("exam.unverified", "0")
    client, token = _signed_in(app, students[0])
    page = client.get("/candidate/exam").get_data(as_text=True)
    assert "Your application is not yet verified for the test." in page
    client.post("/candidate/exam", data={"_csrf": token})
    assert _attempt(app, students[0]) is None
    client, token = _signed_in(app, students[1])
    assert client.post("/candidate/exam", data={"_csrf": token}).headers["Location"].endswith("/candidate/exam/paper")


def test_the_console_counts_them_and_the_selection_does_not():
    from kts.db import execute, query
    from kts.admin import run_selection
    app, students = _portal(["submitted", "verified", "rejected"])
    with app.app_context():
        from kts.candidate import test_statuses
        from kts.db import all_settings
        assert "submitted" in test_statuses(all_settings())
        n = query("SELECT COUNT(*) AS n FROM applications WHERE status IN ('submitted','verified')", one=True)["n"]
        assert n == 2
    # both take the test; only the verified one is ranked
    for who in students[:2]:
        client, token = _signed_in(app, who)
        client.post("/candidate/exam", data={"_csrf": token})
    with app.test_request_context():
        execute("UPDATE exam_sessions SET status = 'submitted', score = 50, submitted_at = started_at")
        run_selection(10, 5, None)
        ranked = {r["application_id"] for r in query("SELECT application_id FROM merit_list")}
        ids = {r["app_no"]: r["id"] for r in query("SELECT id, app_no FROM applications")}
    assert ranked == {ids[students[1]["app_no"]]}

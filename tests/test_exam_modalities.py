"""
The online test as the students meet it: the attempt, its end, and what the selection counts.

    python -m pytest tests -q
"""
import json
from datetime import timedelta

from conftest import add_candidates, make_app
from test_public_fixes import _staff


def _ready(n=1):
    """A portal with a question bank in Hindi, the window forced open, n verified students."""
    from kts import kural as K
    from kts.db import execute, executemany, set_setting, utcnow
    app = make_app(ADMIN_PASSWORD=None)
    students = add_candidates(app, n)
    with app.app_context():
        rows = K.generate_questions("hi", 60, "tests")
        executemany("INSERT INTO questions(lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active, source, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,1,'auto',?)",
                    [(r["lang"], r["qtype"], r["text"], r["opt_a"], r["opt_b"], r["opt_c"], r["opt_d"], r["correct"],
                      r["kural_no"], r["difficulty"], utcnow()) for r in rows])
        execute("UPDATE applications SET status = 'verified'")
        set_setting("exam.open", "1")
        set_setting("merit.published", "0")
    return app, students


def _signed_in(app, who):
    client = app.test_client()
    client.get("/candidate/login")
    with client.session_transaction() as s:
        token = s["_csrf"]
    r = client.post("/candidate/login", data={"_csrf": token, "app_no": who["app_no"], "dob": who["dob"], "last4": who["last4"]})
    assert r.status_code == 302
    return client, token


def _attempt(app, who):
    from kts.db import query
    with app.app_context():
        return query("SELECT s.* FROM exam_sessions s JOIN applications a ON a.id = s.application_id WHERE a.app_no = ?",
                     (who["app_no"],), one=True)


def test_a_paper_has_fifty_questions_of_the_language_with_shuffled_options():
    app, students = _ready()
    client, token = _signed_in(app, students[0])
    r = client.post("/candidate/exam", data={"_csrf": token})
    assert r.status_code == 302 and r.headers["Location"].endswith("/candidate/exam/paper")
    attempt = _attempt(app, students[0])
    paper = json.loads(attempt["paper_json"])
    assert len(paper) == 50 and len({p["q"] for p in paper}) == 50 and attempt["lang"] == "hi"
    assert any(p["order"] != ["A", "B", "C", "D"] for p in paper)
    # thirty minutes from the start, and the paper page shows all fifty
    from kts.utils import parse_iso
    assert parse_iso(attempt["deadline_at"]) - parse_iso(attempt["started_at"]) == timedelta(minutes=30)
    page = client.get("/candidate/exam/paper").get_data(as_text=True)
    assert page.count('type="radio"') == 200 and 'data-total="50"' in page


def test_two_start_clicks_at_once_make_one_attempt(monkeypatch):
    app, students = _ready()
    client, token = _signed_in(app, students[0])
    assert client.post("/candidate/exam", data={"_csrf": token}).status_code == 302
    first = _attempt(app, students[0])
    # the second click found no attempt yet (it was being written) and tries to write one too
    import kts.candidate
    monkeypatch.setattr(kts.candidate, "_exam_session", lambda cand: None)
    r = client.post("/candidate/exam", data={"_csrf": token})
    assert r.status_code == 302 and r.headers["Location"].endswith("/candidate/exam/paper")
    monkeypatch.undo()
    assert _attempt(app, students[0])["paper_json"] == first["paper_json"]
    from kts.db import query
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM exam_sessions", one=True)["n"] == 1


def test_an_attempt_that_ran_out_with_the_browser_closed_is_counted_by_the_selection():
    app, students = _ready(3)
    scores = {}
    for i, who in enumerate(students):
        client, token = _signed_in(app, who)
        client.post("/candidate/exam", data={"_csrf": token})
        attempt = _attempt(app, who)
        paper = json.loads(attempt["paper_json"])
        from kts.db import query
        with app.app_context():
            correct = {r["id"]: r["correct"] for r in query("SELECT id, correct FROM questions")}
        right = [p["q"] for p in paper][: 20 + 10 * i]
        answers = {str(q): correct[q] for q in right}
        client.post("/candidate/exam/save", data=json.dumps({"answers": answers}), content_type="application/json",
                    headers={"X-CSRF-Token": token})
        scores[who["app_no"]] = len(right) * 2
        if i < 2:
            client.post("/candidate/exam/submit", data={"_csrf": token, "answers": json.dumps(answers)})
    # the third student closed the browser; the time ran out an hour ago
    from kts.db import execute
    from kts.utils import now_ist
    with app.app_context():
        execute("UPDATE exam_sessions SET started_at = ?, deadline_at = ? WHERE status = 'in_progress'",
                ((now_ist() - timedelta(minutes=90)).isoformat(), (now_ist() - timedelta(minutes=60)).isoformat()))
    assert _attempt(app, students[2])["status"] == "in_progress"
    admin = _staff(app, "admin@tests.example", "admin")
    admin.get("/console/selection")
    with admin.session_transaction() as s:
        token = s["_csrf"]
    r = admin.post("/console/selection", data={"_csrf": token, "action": "run", "select_count": "2", "wait_count": "1"})
    assert r.status_code == 302
    attempt = _attempt(app, students[2])
    assert attempt["status"] == "expired" and attempt["score"] == scores[students[2]["app_no"]]
    from kts.db import query
    with app.app_context():
        ranked = query("SELECT m.rank, m.outcome, a.app_no FROM merit_list m JOIN applications a ON a.id = m.application_id ORDER BY m.rank")
    # the three are of one college: the best of them is ranked, and it is the one whose time ran out
    assert [(r["rank"], r["app_no"], r["outcome"]) for r in ranked] == [(1, students[2]["app_no"], "selected")]


def test_the_window_closes_at_the_end_time_but_an_attempt_begun_before_it_goes_on(monkeypatch):
    from datetime import datetime
    from kts import candidate, utils
    from kts.db import set_setting
    app, students = _ready()
    with app.app_context():
        set_setting("exam.open", "auto")
        set_setting("exam.date", "2026-10-19")
    def at(hhmm):
        now = datetime.fromisoformat(f"2026-10-19T{hhmm}").replace(tzinfo=utils.IST)
        monkeypatch.setattr(utils, "now_ist", lambda: now)
        monkeypatch.setattr(candidate, "now_ist", lambda: now)
    client, token = _signed_in(app, students[0])
    at("10:59")
    r = client.post("/candidate/exam", data={"_csrf": token})
    assert r.headers["Location"].endswith("/candidate/") and _attempt(app, students[0]) is None
    at("11:59")
    r = client.post("/candidate/exam", data={"_csrf": token})
    assert r.headers["Location"].endswith("/candidate/exam/paper")
    at("12:20")
    assert client.get("/candidate/exam/paper").status_code == 200
    r = client.post("/candidate/exam/save", data=json.dumps({"answers": {}}), content_type="application/json",
                    headers={"X-CSRF-Token": token})
    assert r.status_code == 200 and r.get_json()["remaining"] == 9 * 60
    at("12:31")
    r = client.post("/candidate/exam/save", data=json.dumps({"answers": {}}), content_type="application/json",
                    headers={"X-CSRF-Token": token})
    assert r.status_code == 409 and r.get_json()["reason"] == "expired"
    assert _attempt(app, students[0])["status"] == "expired"


def test_a_student_not_yet_verified_cannot_start():
    from kts.db import execute
    app, students = _ready()
    with app.app_context():
        execute("UPDATE applications SET status = 'submitted'")
    client, token = _signed_in(app, students[0])
    r = client.post("/candidate/exam", data={"_csrf": token})
    assert r.headers["Location"].endswith("/candidate/") and _attempt(app, students[0]) is None

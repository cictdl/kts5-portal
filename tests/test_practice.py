"""
The practice test for students (version 1.2.54): questions made afresh from the Thirukkural, never
those of the question bank; the screen of the online test; nothing written in the database.

    python -m pytest tests -q
"""
import json
from datetime import timedelta

from conftest import make_app
from test_public_fixes import _text


def _bank(app, lang, count=120):
    """A question bank in this language, made by the generator as the console makes it."""
    from kts import kural as K
    from kts.db import executemany, utcnow
    with app.app_context():
        rows = K.generate_questions(lang, count, "bank-" + lang)
        executemany("INSERT INTO questions(lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active, source, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,1,'auto',?)",
                    [(r["lang"], r["qtype"], r["text"], r["opt_a"], r["opt_b"], r["opt_c"], r["opt_d"], r["correct"],
                      r["kural_no"], r["difficulty"], utcnow()) for r in rows])
        return rows


def _token(client):
    with client.session_transaction() as s:
        return s["_csrf"]


def _start(client, lang="ta"):
    client.get("/practice?lang=en")
    return client.post("/practice/start", data={"_csrf": _token(client), "lang": lang})


def _attempt(client):
    with client.session_transaction() as s:
        return dict(s["practice"])


def _counts(app):
    from kts.db import query
    with app.app_context():
        return {t: query(f"SELECT COUNT(*) AS n FROM {t}", one=True)["n"]
                for t in ("questions", "exam_sessions", "campus_attempts", "campus_students", "outbox", "audit_log", "applications")}


def test_the_questions_are_never_those_of_the_bank():
    from kts import practice
    app = make_app(ADMIN_PASSWORD=None)
    bank = _bank(app, "ta")
    asked = {(r["qtype"], r["kural_no"]) for r in bank if r["kural_no"]}
    texts = {r["text"] for r in bank}
    with app.app_context():
        for seed in ("a", "b", "c", "d", "e"):
            rows = practice.make("ta", 10, seed)
            assert len(rows) == 10
            assert all(r["qtype"] in ("complete", "chapter", "section") for r in rows)
            assert not {(r["qtype"], r["kural_no"]) for r in rows} & asked
            assert not {r["text"] for r in rows} & texts
            assert len({(r["qtype"], r["kural_no"]) for r in rows}) == 10
            # made again from the seed and the picks, the same questions in the same order
            picks = [[r["qtype"], r["kural_no"]] for r in rows]
            assert [r["text"] for r in practice.rows_for("ta", seed, picks)] == [r["text"] for r in rows]
        # in every language of the test
        from kts import kural as K
        for lang in K.ORIENTATION_LANGS:
            assert len(practice.make(lang, 10, "all")) == 10, lang


def test_a_practice_from_start_to_result_writes_nothing():
    from kts import practice
    app = make_app(ADMIN_PASSWORD=None)
    _bank(app, "ta")
    before = _counts(app)
    client = app.test_client()
    page = client.get("/practice?lang=en").get_data(as_text=True)
    assert "Practice test" in page and "10 questions in 6 minutes" in page and page.count('<option value="') >= 23
    assert 'name="lang"' in page and "Start the practice test" in page
    r = _start(client, "ta")
    assert r.status_code == 302 and r.headers["Location"].endswith("/practice/paper")
    a = _attempt(client)
    assert a["lang"] == "ta" and a["n"] == 10 and a["answers"] == {} and len(a["picks"]) == 10
    paper = client.get("/practice/paper").get_data(as_text=True)
    assert 'id="exam-app"' in paper and 'data-save="/practice/save"' in paper and 'action="/practice/submit"' in paper
    assert "Practice test" in paper and "Practice · not recorded" in paper and 'name="robots" content="noindex"' in paper
    assert paper.count('class="q"') == 10 and 'data-total="10"' in paper
    remaining = int(paper.split('data-remaining="')[1].split('"')[0])
    assert 350 <= remaining <= 360
    with app.app_context():
        rows = practice.rows_for("ta", a["seed"], a["picks"])
    right = {str(i): r["correct"] for i, r in enumerate(rows, 1)}
    wrong = {"1": "ABCD".replace(right["1"], "")[0]}
    # saved as the test saves: JSON with the token in the header
    r = client.post("/practice/save", data=json.dumps({"answers": {"1": wrong["1"], "2": right["2"], "99": "A"}}),
                    headers={"Content-Type": "application/json", "X-CSRF-Token": _token(client)})
    assert r.status_code == 200 and r.get_json()["ok"] and r.get_json()["saved"] == 2
    assert _attempt(client)["answers"] == {"1": wrong["1"], "2": right["2"]}
    sent = {k: v for k, v in right.items() if k not in ("1", "10")}
    r = client.post("/practice/submit", data={"_csrf": _token(client), "answers": json.dumps(sent)})
    assert r.status_code == 302 and r.headers["Location"].endswith("/practice/result")
    result = client.get("/practice/result?lang=en").get_data(as_text=True)
    assert "Your practice result" in result and "8 of 10 correct" in result
    assert result.count("Right answer") == 10 and "Not answered" in result and "Read this couplet" in result
    assert f'href="/thirukkural/{rows[0]["kural_no"]}"' in result and "Practise again" in result
    # submitted: the paper leads to the result, the saving is closed
    assert client.get("/practice/paper").headers["Location"].endswith("/practice/result")
    assert client.post("/practice/save", data="{}", headers={"Content-Type": "application/json",
                                                             "X-CSRF-Token": _token(client)}).status_code == 409
    # practise again: a new paper
    seed = _attempt(client)["seed"]
    _start(client, "ta")
    assert _attempt(client)["seed"] != seed and not _attempt(client).get("done")
    assert _counts(app) == before


def test_the_time_runs_out():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    _start(client, "hi")
    from kts.utils import now_ist
    with client.session_transaction() as s:
        a = dict(s["practice"])
        a["deadline"] = (now_ist() - timedelta(seconds=10)).isoformat()
        s["practice"] = a
    # within the grace of the test, the answers are still taken
    r = client.post("/practice/save", data=json.dumps({"answers": {"1": "A"}}),
                    headers={"Content-Type": "application/json", "X-CSRF-Token": _token(client)})
    assert r.status_code == 200 and r.get_json()["remaining"] == 0
    with client.session_transaction() as s:
        a = dict(s["practice"])
        a["deadline"] = (now_ist() - timedelta(minutes=5)).isoformat()
        s["practice"] = a
    r = client.post("/practice/save", data=json.dumps({"answers": {"2": "A"}}),
                    headers={"Content-Type": "application/json", "X-CSRF-Token": _token(client)})
    assert r.status_code == 409 and r.get_json()["reason"] == "expired"
    assert client.get("/practice/paper").headers["Location"].endswith("/practice/result")
    result = client.get("/practice/result?lang=en").get_data(as_text=True)
    assert "Your practice result" in result and _text("exam.auto_submitted") in result
    assert _attempt(client)["answers"] == {"1": "A"}


def test_switched_off_wrong_language_and_the_limit():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None, RATE_PRACTICE_PER_HOUR=2)
    client = app.test_client()
    # an address of its own: the limiter counts per address across the applications of the tests
    client.environ_base["REMOTE_ADDR"] = "198.51.100.154"
    assert _start(client, "xx").status_code == 400
    assert _start(client, "ta").status_code == 302 and _start(client, "en").status_code == 302
    r = _start(client, "ml")
    assert r.status_code == 302 and r.headers["Location"].endswith("/practice")
    assert _attempt(client)["lang"] == "en"
    with app.app_context():
        set_setting("practice.on", "0")
    page = client.get("/practice?lang=en").get_data(as_text=True)
    assert "The practice test is not available at present." in page and "Start the practice test" not in page
    assert client.post("/practice/start", data={"_csrf": _token(client), "lang": "ta"}).status_code == 404
    assert 'href="/practice"' not in client.get("/examination?lang=en").get_data(as_text=True)


def test_the_numbers_of_the_settings():
    from kts.practice import _numbers
    assert _numbers({}) == (10, 6)
    assert _numbers({"practice.questions": "100", "practice.minutes": "0"}) == (30, 1)
    assert _numbers({"practice.questions": "abc", "practice.minutes": "15"}) == (10, 15)


def test_found_from_the_examination_page_the_guide_and_the_sitemap():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    for path in ("/examination", "/how-to-take-part", "/sitemap"):
        assert 'href="/practice"' in client.get(f"{path}?lang=en").get_data(as_text=True), path
    assert "/practice" in client.get("/sitemap.xml").get_data(as_text=True)

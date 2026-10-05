"""
The classroom quiz: the questions it makes, the points, a whole game on a clock of the tests,
who may host, and what a player can and cannot do.

    python -m pytest tests -q
"""
import json
import random
import re

import pytest

from conftest import add_candidates, make_app
from test_public_fixes import _staff


class Clock:
    """The clock of the quiz, moved by the test."""

    def __init__(self, ms=1_800_000_000_000):
        self.ms = ms

    def __call__(self):
        return self.ms

    def go(self, seconds):
        self.ms += int(seconds * 1000)


@pytest.fixture
def clock(monkeypatch):
    from kts import quiz
    c = Clock()
    monkeypatch.setattr(quiz, "_now_ms", c)
    return c


def _csrf(client):
    with client.session_transaction() as s:
        if "_csrf" not in s:
            s["_csrf"] = "tests-csrf-token"
        return s["_csrf"]


def _post_json(client, path, body):
    return client.post(path, data=json.dumps(body), content_type="application/json",
                       headers={"X-CSRF-Token": _csrf(client)})


def _create(client, **form):
    data = {"_csrf": _csrf(client), "lang": "hi", "scope": "all", "count": "5", "seconds": "20"}
    data.update(form)
    r = client.post("/quiz/host", data=data)
    assert r.status_code == 302, r.data[:400]
    code = r.headers["Location"].rsplit("/", 1)[1]
    assert re.fullmatch(r"\d{6}", code)
    return code


def _join(app, code, name):
    player = app.test_client()
    player.get("/quiz")
    r = player.post("/quiz", data={"_csrf": _csrf(player), "code": code, "name": name})
    assert r.status_code == 302 and "/quiz/play" in r.headers["Location"], r.data[:400]
    return player


def _questions(app, code):
    from kts.db import query
    with app.app_context():
        return json.loads(query("SELECT questions FROM quiz_rooms WHERE code = ? ORDER BY id DESC", (code,), one=True)["questions"])


# ---- the questions ------------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["hi", "ta", "en", "ur", "bn", "sat", "ks", "mni"])
def test_questions_of_the_whole_thirukkural(app, lang):
    from kts import quiz
    with app.app_context():
        questions = quiz.make_questions(lang, 20, "all", random.Random(7))
    assert len(questions) == 20
    kurals = [q["kural"] for q in questions if q["kural"]]
    assert len(kurals) == len(set(kurals))
    assert {q["kind"] for q in questions} == {"complete", "chapter", "section", "gk"}
    for q in questions:
        assert len(q["options"]) == 4 and len(set(q["options"])) == 4 and 0 <= q["answer"] <= 3
        assert q["stem"] and all(q["options"])


def test_questions_of_one_chapter_and_of_one_section(app):
    from kts import kural as K
    from kts import quiz
    with app.app_context():
        chapter = quiz.make_questions("hi", 10, "ch40", random.Random(1))
        section = quiz.make_questions("hi", 20, "pal3", random.Random(2))
    assert len(chapter) == 10 and {q["kind"] for q in chapter} == {"complete"}
    assert sorted(q["kural"] for q in chapter) == list(range(391, 401))
    # the right second line is that of the couplet
    for q in chapter:
        assert q["options"][q["answer"]] == K.lines(K.kural(q["kural"]), "hi")[1]
    assert {q["kind"] for q in section} == {"complete", "chapter"}
    assert all(K.kural(q["kural"])["pal_num"] == 3 for q in section)
    # the chapters offered are those of the same section
    names = {K.chapter_label(ch, "hi") for ch in K.chapters() if ch["palNum"] == 3}
    for q in section:
        if q["kind"] == "chapter":
            assert set(q["options"]) <= names


def test_nothing_for_an_unknown_choice(app):
    from kts import quiz
    with app.app_context():
        assert quiz.make_questions("hi", 10, "ch134", random.Random(1)) == []
        assert quiz.make_questions("hi", 10, "everything", random.Random(1)) == []
        assert quiz.make_questions("bho", 10, "all", random.Random(1)) == []


def test_points():
    from kts.quiz import points
    assert points(0, 20000) == 1000
    assert points(10000, 20000) == 750
    assert points(20000, 20000) == 500
    assert points(-5, 20000) == 1000 and points(99999, 20000) == 500


# ---- a whole game ------------------------------------------------------------------------------

def test_a_whole_game(clock):
    app = make_app(ADMIN_PASSWORD=None)
    host = _staff(app, "admin@tests.example", "admin")
    code = _create(host)
    screen = host.get(f"/quiz/host/{code}").get_data(as_text=True)
    assert code[:3] in screen and code[3:] in screen and 'src="data:image/png;base64,' in screen
    assert "localhost:8905/quiz" in screen
    assert host.get(f"/quiz/host/{code}/state").get_json() == {"stage": "lobby", "index": -1, "total": 5, "players": 0, "names": []}
    # nobody yet: the quiz does not start
    assert _post_json(host, f"/quiz/host/{code}/action", {"action": "start"}).status_code == 409

    asha = _join(app, code, "  Asha  ")
    ravi = _join(app, code, "Ravi")
    twin = _join(app, code, "asha")
    names = [p["name"] for p in host.get(f"/quiz/host/{code}/state").get_json()["names"]]
    assert names == ["Asha", "Ravi", "asha 2"]
    assert asha.get("/quiz/api/state").get_json()["stage"] == "lobby"
    # the host removes one
    twin_id = host.get(f"/quiz/host/{code}/state").get_json()["names"][2]["id"]
    assert _post_json(host, f"/quiz/host/{code}/action", {"action": "remove", "player": twin_id}).get_json()["ok"]
    assert twin.get("/quiz/api/state").get_json() == {"stage": "removed"}

    questions = _questions(app, code)
    assert _post_json(host, f"/quiz/host/{code}/action", {"action": "start"}).get_json()["ok"]
    state = asha.get("/quiz/api/state").get_json()
    assert state["stage"] == "ready" and state["ready_ms"] == 5000 and "question" not in state
    # an answer before the options are shown counts for nothing
    assert _post_json(asha, "/quiz/api/answer", {"q": 0, "choice": 0}).get_json()["reason"] == "late"

    clock.go(5)
    state = asha.get("/quiz/api/state").get_json()
    assert state["stage"] == "question" and state["remaining_ms"] == 20000 and state["answered"] is None
    assert "answer" not in state["question"] and len(state["question"]["options"]) == 4
    right = questions[0]["answer"]
    clock.go(4)
    assert _post_json(asha, "/quiz/api/answer", {"q": 0, "choice": right}).get_json() == {"ok": True}
    assert _post_json(asha, "/quiz/api/answer", {"q": 0, "choice": (right + 1) % 4}).get_json()["reason"] == "twice"
    assert asha.get("/quiz/api/state").get_json()["answered"] == right
    assert host.get(f"/quiz/host/{code}/state").get_json()["answered"] == 1
    # the answer of a removed player is refused, and does not count
    assert _post_json(twin, "/quiz/api/answer", {"q": 0, "choice": right}).status_code == 404
    clock.go(2)
    assert _post_json(ravi, "/quiz/api/answer", {"q": 0, "choice": (right + 1) % 4}).get_json() == {"ok": True}
    # everybody has answered: the question ends at once
    shown = host.get(f"/quiz/host/{code}/state").get_json()
    assert shown["stage"] == "reveal" and shown["answer"] == right and sum(shown["counts"]) == 2
    assert shown["counts"][right] == 1
    if questions[0]["kural"]:
        assert shown["kural"]["n"] == questions[0]["kural"] and len(shown["kural"]["ta"]) == 2
    mine = asha.get("/quiz/api/state").get_json()
    assert mine["result"]["correct"] is True and mine["result"]["points"] == 900 and mine["rank"] == 1 and mine["players"] == 2
    theirs = ravi.get("/quiz/api/state").get_json()
    assert theirs["result"]["correct"] is False and theirs["result"]["points"] == 0 and theirs["rank"] == 2
    assert theirs["result"]["answer"] == questions[0]["options"][right]

    # the leaderboard, then the next question; a second click of the same button does nothing twice
    assert _post_json(host, f"/quiz/host/{code}/action", {"action": "board", "index": 0}).get_json()["ok"]
    board = host.get(f"/quiz/host/{code}/state").get_json()
    assert board["stage"] == "board" and board["board"][0] == {"name": "Asha", "score": 900, "gained": 900}
    assert _post_json(host, f"/quiz/host/{code}/action", {"action": "next", "index": 0}).get_json()["ok"]
    assert _post_json(host, f"/quiz/host/{code}/action", {"action": "next", "index": 0}).status_code == 409
    assert host.get(f"/quiz/host/{code}/state").get_json()["index"] == 1

    # question 2: nobody answers; the time runs out
    clock.go(5 + 20)
    assert host.get(f"/quiz/host/{code}/state").get_json()["stage"] == "reveal"
    assert asha.get("/quiz/api/state").get_json()["result"]["answered"] is False
    assert _post_json(asha, "/quiz/api/answer", {"q": 1, "choice": 0}).get_json()["reason"] == "late"
    # questions 3 to 5: the host shows each answer at once
    for index in range(1, 5):
        assert _post_json(host, f"/quiz/host/{code}/action", {"action": "next", "index": index}).get_json()["ok"]
        if index < 4:
            assert _post_json(host, f"/quiz/host/{code}/action", {"action": "skip", "index": index + 1}).get_json()["ok"]
            assert host.get(f"/quiz/host/{code}/state").get_json()["stage"] == "reveal"
    final = host.get(f"/quiz/host/{code}/state").get_json()
    assert final["stage"] == "end" and [r["name"] for r in final["board"]] == ["Asha", "Ravi"]
    end = ravi.get("/quiz/api/state").get_json()
    assert end["stage"] == "end" and end["rank"] == 2 and end["top"][0] == {"name": "Asha", "score": 900}
    # the quiz is over: nobody joins it any more
    late = app.test_client()
    late.get("/quiz")
    page = late.post("/quiz", data={"_csrf": _csrf(late), "code": code, "name": "Late"}).get_data(as_text=True)
    assert "No quiz is open with this code" in page
    # the results of the host
    r = host.get(f"/quiz/host/{code}/results.csv")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    lines = r.data.decode("utf-8-sig").splitlines()
    assert lines[0] == "Place,Name,Points,Correct answers" and lines[1] == "1,Asha,900,1/5" and lines[2] == "2,Ravi,0,0/5"


def test_the_screens_of_the_host_belong_to_the_host(clock):
    app = make_app(ADMIN_PASSWORD=None)
    host = _staff(app, "admin@tests.example", "admin")
    code = _create(host)
    other = _staff(app, email="content@tests.example", role="content")
    for path in (f"/quiz/host/{code}", f"/quiz/host/{code}/state", f"/quiz/host/{code}/results.csv"):
        assert other.get(path).status_code == 404
        assert app.test_client().get(path).status_code == 404
    assert _post_json(other, f"/quiz/host/{code}/action", {"action": "end"}).status_code == 404
    # a second quiz of the same host ends the first
    second = _create(host)
    from kts.db import query
    with app.app_context():
        rooms = query("SELECT code, ended_at FROM quiz_rooms ORDER BY id")
    assert [(r["code"], bool(r["ended_at"])) for r in rooms] == [(code, True), (second, False)]


def test_who_may_host(clock):
    app = make_app(ADMIN_PASSWORD=None)
    page = app.test_client().get("/quiz/host?lang=en").get_data(as_text=True)
    assert "is hosted by a student selected for KTS 5.0" in page and 'name="scope"' not in page
    students = add_candidates(app, 2)
    from kts.db import execute, set_setting
    with app.app_context():
        execute("UPDATE applications SET status = 'selected' WHERE id = 1")
        execute("UPDATE applications SET status = 'waitlisted' WHERE id = 2")
        set_setting("merit.published", "0")

    def signed_in(student):
        c = app.test_client()
        c.get("/candidate/login")
        r = c.post("/candidate/login", data={"_csrf": _csrf(c), **student})
        assert r.status_code == 302
        return c

    selected, waiting = signed_in(students[0]), signed_in(students[1])
    # before the merit list is published nobody of the students hosts
    assert 'name="scope"' not in selected.get("/quiz/host").get_data(as_text=True)
    assert 'id="quiz-card"' not in selected.get("/candidate/").get_data(as_text=True)
    with app.app_context():
        set_setting("merit.published", "1")
    home = selected.get("/candidate/?lang=en").get_data(as_text=True)
    assert 'id="quiz-card"' in home and 'href="/quiz/host"' in home
    form = selected.get("/quiz/host").get_data(as_text=True)
    # the language of the questions is the language of the student
    assert '<option value="hi" selected>' in form
    code = _create(selected, lang="ta", scope="ch1", count="10", seconds="30")
    assert selected.get(f"/quiz/host/{code}").status_code == 200
    assert 'name="scope"' not in waiting.get("/quiz/host").get_data(as_text=True)
    assert 'id="quiz-card"' not in waiting.get("/candidate/").get_data(as_text=True)
    # the console lists the quiz with the application number of its host
    admin = _staff(app, "admin@tests.example", "admin")
    listed = admin.get("/console/quizzes").get_data(as_text=True)
    assert code in listed and "student " + students[0]["app_no"] in listed
    # the switch of the administrator
    with app.app_context():
        set_setting("quiz.candidates", "0")
    assert 'id="quiz-card"' not in selected.get("/candidate/").get_data(as_text=True)
    assert 'name="scope"' not in selected.get("/quiz/host").get_data(as_text=True)


def test_joining(clock):
    app = make_app(ADMIN_PASSWORD=None)
    host = _staff(app, "admin@tests.example", "admin")
    code = _create(host)
    c = app.test_client()
    page = c.get(f"/quiz?code={code}&lang=en").get_data(as_text=True)
    assert f'value="{code}"' in page
    for name, message in (("", "Enter your name"), ("x" * 25, "Enter your name"), ("​\u0007", "Enter your name")):
        r = c.post("/quiz", data={"_csrf": _csrf(c), "code": code, "name": name})
        assert r.status_code == 200 and message in r.get_data(as_text=True)
    r = c.post("/quiz", data={"_csrf": _csrf(c), "code": "000000", "name": "Anu"})
    assert "No quiz is open with this code" in r.get_data(as_text=True)
    # a player without a language of his own reads the quiz in the language of its questions
    fresh = app.test_client()
    fresh.get("/quiz")
    r = fresh.post("/quiz", data={"_csrf": _csrf(fresh), "code": code, "name": "कविता"})
    assert r.headers["Location"].endswith("/quiz/play?lang=hi")
    page = fresh.get("/quiz/play?lang=hi").get_data(as_text=True)
    assert '<html lang="hi"' in page and "कविता" in page and 'id="quiz-data"' in page
    # back on the page for joining, the quiz is offered again
    assert "/quiz/play" in fresh.get("/quiz").get_data(as_text=True)
    # a full quiz
    from kts.db import set_setting
    with app.app_context():
        set_setting("quiz.max_players", "1")
    r = c.post("/quiz", data={"_csrf": _csrf(c), "code": code, "name": "Anu"})
    assert "This quiz is full" in r.get_data(as_text=True)
    # no answer without the token of the form
    assert fresh.post("/quiz/api/answer", data=json.dumps({"q": 0, "choice": 0}), content_type="application/json").status_code == 400
    # leaving forgets the player in this browser
    fresh.post("/quiz/leave", data={"_csrf": _csrf(fresh)})
    assert fresh.get("/quiz/api/state").get_json() == {"stage": "gone"}
    assert fresh.get("/quiz/play").status_code == 302


def test_closed_quiz(clock):
    app = make_app(ADMIN_PASSWORD=None)
    host = _staff(app, "admin@tests.example", "admin")
    code = _create(host)
    from kts.db import set_setting
    with app.app_context():
        set_setting("quiz.on", "0")
    c = app.test_client()
    page = c.get("/quiz?lang=en").get_data(as_text=True)
    assert "The classroom quiz is closed now." in page and 'name="name"' not in page
    r = c.post("/quiz", data={"_csrf": _csrf(c), "code": code, "name": "Anu"})
    assert r.status_code == 200 and "/quiz/play" not in r.headers.get("Location", "")
    assert 'name="scope"' not in host.get("/quiz/host").get_data(as_text=True)


def test_names_are_text(clock):
    from kts.quiz import _csv_text
    assert _csv_text("=HYPERLINK(1)") == "'=HYPERLINK(1)" and _csv_text("+91") == "'+91" and _csv_text("Asha") == "Asha"
    app = make_app(ADMIN_PASSWORD=None)
    host = _staff(app, "admin@tests.example", "admin")
    code = _create(host)
    player = _join(app, code, "<b>Bold</b>")
    page = player.get("/quiz/play").get_data(as_text=True)
    assert "<b>Bold</b>" not in page and "&lt;b&gt;Bold&lt;/b&gt;" in page
    # the screens draw the names from JSON, as text
    assert host.get(f"/quiz/host/{code}/state").get_json()["names"][0]["name"] == "<b>Bold</b>"
    script = (app.static_folder + "/js/quiz.js")
    source = open(script, encoding="utf-8").read()
    assert "innerHTML" not in source and "insertAdjacentHTML" not in source


def test_old_names_are_deleted(clock):
    app = make_app(ADMIN_PASSWORD=None)
    host = _staff(app, "admin@tests.example", "admin")
    code = _create(host)
    _join(app, code, "Asha")
    clock.go(31 * 86400)
    _create(host)
    from kts.db import query
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM quiz_players", one=True)["n"] == 0
        first = query("SELECT players FROM quiz_rooms WHERE code = ?", (code,), one=True)
    assert first["players"] == 1


def test_pages_of_the_quiz_in_every_language(app):
    from kts.i18n import LANG_INFO
    client = app.test_client()
    for code in LANG_INFO:
        page = client.get(f"/quiz?lang={code}").get_data(as_text=True)
        assert f'<html lang="{code}" dir="{LANG_INFO[code]["dir"]}"' in page
        host = client.get(f"/quiz/host?lang={code}").get_data(as_text=True)
        assert 'name="robots" content="noindex"' in host
    assert client.get("/quiz").headers["Cache-Control"] == "no-store"

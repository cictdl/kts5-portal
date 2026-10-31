"""
The classroom quiz draws from the 108 Thirukkural (version 1.2.132): every question of every room is on one of the 108
couplets, in the mix of the 108 (complete, chapter, section; no general knowledge); the host's form says so and offers no
other scope; rooms made before keep their label.

    python -m pytest tests -q
"""
import json
import random
import re

from conftest import make_app
from test_quiz import _create, _csrf


def test_every_question_is_on_one_of_the_108():
    from kts import kural as K
    from kts.quiz import make_questions
    numbers = set(K.kural108_numbers())
    assert len(numbers) == 108
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for lang in ("ta", "en", "hi"):
            for seed in range(3):
                qs = make_questions(lang, 20, "k108", random.Random(seed))
                assert len(qs) == 20, (lang, seed, len(qs))
                assert all(q["kural"] in numbers for q in qs), (lang, [q["kural"] for q in qs if q["kural"] not in numbers])
                assert all(q["kind"] in ("complete", "chapter", "section") for q in qs), lang
                assert len({q["kural"] for q in qs}) == 20
        kinds = [q["kind"] for q in make_questions("ta", 40, "k108", random.Random(7))]
        assert len(kinds) == 40 and kinds.count("complete") >= 18 and kinds.count("chapter") >= 10 and kinds.count("section") >= 6


def test_a_room_is_made_on_the_108_whatever_is_posted():
    from kts import kural as K
    from kts.db import query
    numbers = set(K.kural108_numbers())
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    client.environ_base["REMOTE_ADDR"] = "203.0.113.80"
    for posted in ("all", "pal2", "ch57", "k108", "nonsense"):
        code = _create(client, lang="ta", scope=posted, count="10", seconds="20")
        with app.app_context():
            room = query("SELECT * FROM quiz_rooms WHERE code = ?", (code,), one=True)
        assert room["scope"] == "k108", posted
        qs = json.loads(room["questions"])
        assert len(qs) == 10 and all(q["kural"] in numbers for q in qs), posted
        page = client.get(f"/quiz/host/{code}?lang=en").get_data(as_text=True)
        assert "The 108 Thirukkural" in page
        # the room is ended so that the next one may be made
        with app.app_context():
            from kts.db import execute
            execute("UPDATE quiz_rooms SET ended_at = ? WHERE code = ?", ("2026-10-31T00:00:00", code))


def test_the_form_says_where_the_questions_come_from():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    client.environ_base["REMOTE_ADDR"] = "203.0.113.81"
    page = client.get("/quiz/host?lang=en").get_data(as_text=True)
    assert '<select id="q-scope"' not in page and 'name="scope" value="k108"' in page
    assert ('<p class="scope-fixed"><b>The 108 Thirukkural</b> · <a href="/thirukkural-108" target="_blank" rel="noopener">'
            "Read the 108 Thirukkural") in page
    assert "The questions of every quiz come from the 108 Thirukkural: one couplet from each of the first 108 chapters." in page
    assert "Questions from" in page and "The whole Thirukkural" not in page
    # the join page says so too, in the visitor's language
    assert "The questions of every quiz come from the 108 Thirukkural" in client.get("/quiz/?lang=en").get_data(as_text=True)
    from kts.i18n import CATALOG
    ta = client.get("/quiz/?lang=ta").get_data(as_text=True)
    assert CATALOG["ta"]["quiz.k108_note"] in ta and CATALOG["ta"]["quiz.k108_note"] != CATALOG["en"]["quiz.k108_note"]
    assert '<link rel="stylesheet" href="/static/css/quiz.css?v=3">' in page


def test_rooms_made_before_keep_their_label():
    from kts.quiz import _scope, _scope_label
    app = make_app(ADMIN_PASSWORD=None)
    with app.test_request_context("/quiz/?lang=en"):
        assert _scope_label("k108") == "The 108 Thirukkural"
        assert _scope_label("all") == "The whole Thirukkural"
        assert re.fullmatch(r"1\. .+", _scope_label("ch1"))
        assert _scope("k108")[0] == "k108" and len(_scope("k108")[1]) == 108 and _scope("ch1")[0] == "chapter"

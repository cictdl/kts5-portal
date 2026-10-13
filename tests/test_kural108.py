"""
The 108 Thirukkural (version 1.2.64): one couplet from each of the first 108 chapters, with CICT's Tamil
commentary; the syllabus an institution may choose for its online assessment; the generator, the paper,
the bank check and the practice test that follow it; and the public page in the languages.

    python -m pytest tests -q
"""
import json
import random
import re

from conftest import make_app
from test_campus import _accepted, _coordinator, _portal, _signup
from test_practice import _attempt, _token
from test_public_fixes import _staff


def _bank108(app, lang, count=120):
    """A question bank on the 108 in this language, as the console makes it with the box ticked."""
    from kts import kural as K
    from kts.db import executemany, utcnow
    with app.app_context():
        rows = K.generate_questions(lang, count, "k108-" + lang, kurals=K.kural108_numbers())
        executemany("INSERT INTO questions(lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active, source, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,1,'auto',?)",
                    [(r["lang"], r["qtype"], r["text"], r["opt_a"], r["opt_b"], r["opt_c"], r["opt_d"], r["correct"],
                      r["kural_no"], r["difficulty"], utcnow()) for r in rows])


def test_the_selection_is_one_couplet_from_each_of_the_first_108_chapters():
    from kts import kural as K
    items = K.kural108()
    assert len(items) == 108 and [x["chapter"] for x in items] == list(range(1, 109))
    nums = K.kural108_numbers()
    assert len(set(nums)) == 108 and nums[:3] == (1, 11, 30) and nums[-1] == 1071
    for x in items:
        k = K.kural(x["n"])
        assert k["adhigaram"] == x["chapter"] and len(x["urai"]) > 40, x["n"]


def test_the_generator_stays_within_the_108_and_asks_no_general_knowledge():
    from kts import kural as K
    nums = set(K.kural108_numbers())
    for lang in ("ta", "hi", "en", "bn"):
        rows = K.generate_questions(lang, 50, "k108-" + lang, kurals=K.kural108_numbers())
        assert len(rows) == 50 and all(r["kural_no"] in nums for r in rows), lang
        assert {r["qtype"] for r in rows} == {"complete", "chapter", "section"}
    # the usual generator still asks general knowledge of the whole book
    plain = K.generate_questions("en", 40, "plain")
    assert any(r["qtype"] == "gk" for r in plain) and any(r["kural_no"] not in nums for r in plain if r["kural_no"])


def test_a_paper_within_the_108_takes_a_different_couplet_for_each_question():
    from kts import kural as K
    from kts.candidate import _build_paper
    from kts.db import query
    app = make_app(ADMIN_PASSWORD=None)
    _bank108(app, "hi")
    with app.app_context():
        # the plain bank of the tests too: a paper on the 108 leaves it aside
        from test_practice import _bank
        _bank(app, "hi", 60)
        nums = set(K.kural108_numbers())
        paper = _build_paper("hi", 50, random.Random(1), kurals=K.kural108_numbers())
        ids = [p["q"] for p in paper]
        rows = query(f"SELECT id, kural_no FROM questions WHERE id IN ({','.join('?' * len(ids))})", ids)
        assert len(ids) == 50 and all(r["kural_no"] in nums for r in rows)
        assert len({r["kural_no"] for r in rows}) == 50
        # the usual paper is as before: the whole bank
        plain = _build_paper("hi", 50, random.Random(1))
        assert len(plain) == 50


def test_the_institution_chooses_the_108_and_the_students_are_told():
    from kts import kural as K
    from kts.db import execute, query
    app = _portal()
    _bank108(app, "hi")
    _bank108(app, "en", 60)
    inst = _accepted(app)
    coord, token = _coordinator(app, inst)
    page = coord.get("/institution").get_data(as_text=True)
    assert 'name="syllabus"' in page and "The 108 Thirukkural only" in page and 'href="/thirukkural-108"' in page
    r = coord.post("/institution/assessment", data={"_csrf": token, "action": "on", "test_from": "2026-10-16", "test_to": "2026-10-20",
                                                     "syllabus": "108"}, follow_redirects=True)
    page = r.get_data(as_text=True)
    assert "The online assessment is on, on the 108 Thirukkural." in page and "<b>The 108 Thirukkural</b>: one couplet" in page
    assert "Change the days or the syllabus" in page
    with app.app_context():
        execute("UPDATE institutions SET test_from = '2026-01-01', test_to = '2099-12-31', test_slug = 'abcd1234', test_code = '246810' WHERE id = ?",
                (inst["id"],))
        inst = query("SELECT * FROM institutions WHERE id = ?", (inst["id"],), one=True)
    assert inst["test_syllabus"] == "108"
    # the students see it on the sign-up page and on the start page, with the list
    page = app.test_client().get("/assessment/abcd1234?lang=en").get_data(as_text=True)
    assert 'id="syllabus-108"' in page and "drawn from the 108 Thirukkural alone" in page and 'href="/thirukkural-108"' in page
    client, r = _signup(app, "abcd1234")
    assert r.status_code == 302
    start = client.get("/assessment/abcd1234/start?lang=en").get_data(as_text=True)
    assert 'id="syllabus-108"' in start and "Read the 108 Thirukkural" in start
    r = client.post("/assessment/abcd1234/start", data={"_csrf": _token(client)})
    assert r.status_code == 302 and r.headers["Location"].endswith("/paper")
    with app.app_context():
        attempt = query("SELECT * FROM campus_attempts", one=True)
        ids = [p["q"] for p in json.loads(attempt["paper_json"])]
        rows = query(f"SELECT kural_no FROM questions WHERE id IN ({','.join('?' * len(ids))})", ids)
    nums = set(K.kural108_numbers())
    assert len(ids) == 50 and all(r["kural_no"] in nums for r in rows)
    # back to the whole book
    r = coord.post("/institution/assessment", data={"_csrf": token, "action": "on", "test_from": "2026-10-16", "test_to": "2026-10-20",
                                                     "syllabus": "all"}, follow_redirects=True)
    assert "The online assessment is on. Give" in r.get_data(as_text=True)
    with app.app_context():
        assert query("SELECT test_syllabus FROM institutions WHERE id = ?", (inst["id"],), one=True)["test_syllabus"] == "all"
        execute("UPDATE institutions SET test_from = '2026-01-01', test_to = '2099-12-31' WHERE id = ?", (inst["id"],))
    assert 'id="syllabus-108"' not in app.test_client().get("/assessment/abcd1234?lang=en").get_data(as_text=True)


def test_the_console_generates_on_the_108_and_the_check_counts_them():
    from kts import kural as K, qbank
    from kts.db import query
    app = make_app(ADMIN_PASSWORD=None)
    admin = _staff(app, "k108-admin@tests.example", "superadmin")
    page = admin.get("/console/questions").get_data(as_text=True)
    assert 'name="set" value="108"' in page
    r = admin.post("/console/questions/generate", data={"_csrf": _token(admin), "langs": ["ta"], "count": "20", "set": "108"},
                   follow_redirects=True)
    assert "Generated 20 questions from the Thirukkural corpus, on the 108 Thirukkural (none that the bank asked already)." in r.get_data(as_text=True)
    with app.app_context():
        rows = query("SELECT lang, qtype, kural_no FROM questions")
        rep = qbank.report(50)
    nums = set(K.kural108_numbers())
    assert len(rows) == 20 and all(r["lang"] == "ta" and r["kural_no"] in nums and r["qtype"] != "gk" for r in rows)
    ta = next(s for s in rep["languages"] if s["lang"] == "ta")
    assert ta["usable"] == 20 and ta["usable108"] == 20 and rep["k108"] == 108 and rep["short108"] == 23
    page = admin.get("/console/questions/check").get_data(as_text=True)
    assert "On the 108" in page and "23 language(s) have fewer than 50" in page
    # without the box: the whole book, general knowledge among the questions
    admin.post("/console/questions/generate", data={"_csrf": _token(admin), "langs": ["en"], "count": "40"})
    with app.app_context():
        kinds = {r["qtype"] for r in query("SELECT qtype FROM questions WHERE lang = 'en'")}
    assert "gk" in kinds


def test_the_questions_on_the_108_are_made_once_for_each_database():
    """At the first start (KTS_K108_SEED=1; 0 in the tests) 150 questions on the 108 are made in every language (1.2.65)."""
    from kts import kural as K, qbank
    from kts.db import get_setting, query
    app = make_app(ADMIN_PASSWORD=None)
    assert app.config["K108_SEED"] is False
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM questions", one=True)["n"] == 0
    made = qbank.seed_k108(app, count=20)
    assert made == 23 * 20
    nums = set(K.kural108_numbers())
    with app.app_context():
        rows = query("SELECT lang, qtype, kural_no, source FROM questions")
        assert len(rows) == 460 and all(r["kural_no"] in nums and r["qtype"] != "gk" and r["source"] == "auto" for r in rows)
        assert len({(r["lang"], r["qtype"], r["kural_no"]) for r in rows}) == 460 and {r["lang"] for r in rows} == set(K.ORIENTATION_LANGS)
        assert get_setting("seed.questions.k108")
        log = query("SELECT * FROM audit_log WHERE action = 'questions_generated'", one=True)
        assert log["actor"] == "public" and '"by": "start-up"' in log["detail"]
    # a second start makes nothing more
    assert qbank.seed_k108(app, count=20) == 0
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM questions", one=True)["n"] == 460
        # what the bank asks is left out, and the check counts the usable questions on the 108
        asked = qbank.taken_pairs("ta")
        more = qbank.generate_k108("ta", 50, "again")
        assert len(more) == 50 and not any((r["qtype"], r["kural_no"]) in asked for r in more)
        assert next(s for s in qbank.report(50)["languages"] if s["lang"] == "ta")["usable108"] == 20
    # with the 324 possible nearly all asked, fewer come, never a duplicate
    _bank108(app, "ta", 300)
    with app.app_context():
        asked = qbank.taken_pairs("ta")
        few = qbank.generate_k108("ta", 100, "last")
        assert 0 < len(few) < 100 and not any((r["qtype"], r["kural_no"]) in asked for r in few)
    # the console's box does the same, twice without a duplicate
    admin = _staff(app, "k108-seed@tests.example", "superadmin")
    for _ in range(2):
        admin.post("/console/questions/generate", data={"_csrf": _token(admin), "langs": ["hi"], "count": "30", "set": "108"})
    with app.app_context():
        hi = query("SELECT qtype, kural_no FROM questions WHERE lang = 'hi'")
        assert len(hi) == 80 and len({(r["qtype"], r["kural_no"]) for r in hi}) == 80


def test_the_practice_test_on_the_108():
    from kts import kural as K, practice
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    page = client.get("/practice?lang=en").get_data(as_text=True)
    assert 'name="set"' in page and "The 108 Thirukkural only" in page and "All 1,330 couplets" in page and 'href="/thirukkural-108"' in page
    r = client.post("/practice/start", data={"_csrf": _token(client), "lang": "en", "set": "108"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/practice/paper")
    a = _attempt(client)
    assert a["set"] == "108" and a["n"] == 10
    nums = set(K.kural108_numbers())
    assert all(n in nums for _kind, n in a["picks"])
    paper = client.get("/practice/paper").get_data(as_text=True)
    assert "Practice · not recorded · The 108 Thirukkural" in paper and paper.count('class="q"') == 10
    with app.app_context():
        rows = practice.rows_for("en", a["seed"], a["picks"], K.kural108_numbers())
    assert len(rows) == 10 and all(r["kural_no"] in nums for r in rows)
    # the usual practice test is unchanged
    client2 = app.test_client()
    client2.get("/practice?lang=en")
    client2.post("/practice/start", data={"_csrf": _token(client2), "lang": "en", "set": "all"})
    assert _attempt(client2)["set"] == "all" and "· The 108" not in client2.get("/practice/paper").get_data(as_text=True)


def test_a_practice_paper_on_the_108_is_full_when_the_bank_asks_nearly_everything():
    """324 questions are possible on the 108 in a language; with 300 of them in the bank, a practice paper of 30 is still full."""
    from kts import kural as K, practice
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    _bank108(app, "ta", 300)
    with app.app_context():
        set_setting("practice.questions", "30")
        nums = set(K.kural108_numbers())
        for seed in ("a", "b", "c"):
            rows = practice.make("ta", 30, seed, K.kural108_numbers())
            assert len(rows) == 30 and all(r["kural_no"] in nums for r in rows), seed
            assert len({(r["qtype"], r["kural_no"]) for r in rows}) == 30
            picks = [[r["qtype"], r["kural_no"]] for r in rows]
            again = practice.rows_for("ta", seed, picks, K.kural108_numbers())
            assert [(r["qtype"], r["kural_no"]) for r in again] == [tuple(p) for p in picks]
        # the whole book keeps clear of the bank
        assert len(practice.make("ta", 30, "d")) == 30
    client = app.test_client()
    client.get("/practice?lang=en")
    client.post("/practice/start", data={"_csrf": _token(client), "lang": "ta", "set": "108"})
    assert _attempt(client)["n"] == 30


def test_the_page_of_the_108_in_the_languages_and_the_links():
    from kts import kural as K
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    r = client.get("/thirukkural-108?lang=en")
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    assert "108 திருக்குறள்" in page and "The 108 Thirukkural" in page and page.count('class="kural-row"') == 108
    assert "· Virtue</span>" in page and "· Wealth</span>" in page and "· Love</span>" not in page   # no third section: chapters 1 to 108 only
    for n in K.kural108_numbers():
        assert f'href="/thirukkural/{n}"' in page
    assert "1. கடவுள் வாழ்த்து</span> · The Praise of God" in page and "108. கயமை</span> · " in page
    # English stream: the translation; Tamil: the commentary; Hindi: Devanagari
    assert "leads letters; the Ancient Lord" in page and "உரை:" not in page
    ta = client.get("/thirukkural-108?l=ta&lang=ta").get_data(as_text=True)
    assert ta.count("<b>உரை:</b>") == 108 and "எழுத்துக்களெல்லாம் அகரத்தை முதலாக உடையன" in ta
    hi = client.get("/thirukkural-108?l=hi&lang=hi").get_data(as_text=True)
    assert re.search(r"[ऀ-ॿ]", hi) and "उरै" not in hi and 'lang="hi"' in hi
    # the couplet 108 itself is still a couplet page
    assert "Couplet 108" in client.get("/thirukkural/108?lang=en").get_data(as_text=True)
    # found from the examination page, the practice test and the sitemap
    assert 'href="/thirukkural-108"' in client.get("/examination?lang=en").get_data(as_text=True)
    assert "/thirukkural-108" in client.get("/sitemap.xml").get_data(as_text=True)
    assert 'href="/thirukkural-108">The 108 Thirukkural' in client.get("/sitemap?lang=en").get_data(as_text=True)

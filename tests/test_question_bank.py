"""
The check of the question bank (version 1.2.49): whether a full paper of exam.questions questions can
be drawn in each language of the test, and the active questions that should not be in a paper.

    python -m pytest tests -q
"""
import io

from conftest import make_app
from test_public_fixes import _staff


def _token(client):
    with client.session_transaction() as s:
        return s["_csrf"]


def _q(app, lang, text, opts=("one", "two", "three", "four"), correct="A", active=1):
    from kts.db import execute, utcnow
    with app.app_context():
        return execute("INSERT INTO questions(lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, active, source, created_at) "
                       "VALUES(?,?,?,?,?,?,?,?,?,'manual',?)", (lang, "gk", text, *opts, correct, active, utcnow()))


def _many(app, lang, count, word="Question"):
    for i in range(count):
        _q(app, lang, f"{word} {lang} {i}?", (f"a{i}", f"b{i}", f"c{i}", f"d{i}"))


def _report(app):
    from kts import qbank
    with app.app_context():
        return qbank.report(50)


def _lang(rep, code):
    return next(s for s in rep["languages"] if s["lang"] == code)


def test_the_faults_that_keep_a_question_out_of_a_paper():
    app = make_app(ADMIN_PASSWORD=None)
    good = _q(app, "en", "Who wrote the Thirukkural?", ("Thiruvalluvar", "Kambar", "Ilango", "Avvaiyar"))
    blank = _q(app, "en", "  ", ("a", "b", "c", "d"))
    option = _q(app, "en", "Which one?", ("a", "", "c", " "))
    answer = _q(app, "en", "Which answer?", ("a", "b", "c", "d"), correct="E")
    same = _q(app, "en", "Which option?", ("Virtue", "virtue ", "Wealth", "Love"))
    twice = _q(app, "en", "who wrote the  Thirukkural?", ("Thiruvalluvar", "Kambar", "Ilango", "Avvaiyar"))
    # an inactive question is not looked at, and a faulty one is not the original of a duplicate
    _q(app, "en", "Which answer?", ("a", "b", "c", "d"), active=0)
    later = _q(app, "en", "Which answer?", ("a", "b", "c", "d"))
    rep = _report(app)
    kinds = {}
    for p in rep["problems"]:
        kinds.setdefault(p["row"]["id"], []).append(p["kind"])
    assert kinds == {blank: ["blank"], option: ["option"], answer: ["answer"], same: ["same"], twice: ["duplicate"]}
    why = {p["row"]["id"]: p["why"] for p in rep["problems"]}
    assert why[option] == "Option B, D are blank." and why[same] == "Options A and B are the same."
    assert why[twice] == f"The same question as #{good}." and "“E”" in why[answer]
    assert rep["faulty_ids"] == sorted([blank, option, answer, same, twice])
    en = _lang(rep, "en")
    assert (en["active"], en["faulty"], en["usable"], en["inactive"]) == (7, 5, 2, 1)
    assert later not in rep["faulty_ids"]


def test_whether_each_language_can_fill_a_paper():
    app = make_app(ADMIN_PASSWORD=None)
    _many(app, "en", 30)
    _many(app, "hi", 120)
    _many(app, "ta", 60)
    _many(app, "bn", 10)
    rep = _report(app)
    assert _lang(rep, "hi")["status"] == "ready" and _lang(rep, "hi")["say"] == "Ready: 120 questions for papers of 50."
    assert _lang(rep, "ta")["status"] == "thin" and "At least 100 are advised" in _lang(rep, "ta")["say"]
    assert _lang(rep, "bn")["status"] == "short"
    assert _lang(rep, "bn")["say"] == "Short by 40: each paper gets 10 in this language and 30 in English; only 40 of 50 questions in all."
    assert _lang(rep, "en")["say"] == "Short by 20: a paper in English would have only 30 questions."
    assert _lang(rep, "gu")["status"] == "empty" and _lang(rep, "gu")["say"] == "Empty: a paper would be wholly in English (30 questions); only 30 of 50 questions in all."
    assert len(rep["languages"]) == 23 and rep["count"] == {"ready": 1, "thin": 1, "short": 2, "empty": 19}
    assert not rep["ok"]
    _many(app, "en", 70, "More")
    rep = _report(app)
    assert _lang(rep, "en")["status"] == "ready"
    assert _lang(rep, "bn")["say"] == "Short by 40: each paper gets 10 in this language and 40 in English."
    assert _lang(rep, "gu")["say"] == "Empty: a paper would be wholly in English (50 questions)."


def test_another_script_is_pointed_out_and_a_wrong_code_is_listed():
    app = make_app(ADMIN_PASSWORD=None)
    english = _q(app, "bn", "Who wrote the Thirukkural?", ("Thiruvalluvar", "Kambar", "Ilango", "Avvaiyar"))
    _q(app, "bn", "তিরুক্কুরাল কে লিখেছেন?", ("তিরুবল্লুবর", "কম্বর", "ইলাঙ্গো", "অব্বৈয়ার"))
    # Kashmiri: the portal writes it in Arabic letters, CICT's Thirukkural in Devanagari; Konkani in Kannada letters
    _q(app, "ks", "तिरुक्कुरल किस ने लिखा?", ("तिरुवल्लुवर", "कम्बर", "इलंगो", "अव्वैयार"))
    _q(app, "kok", "ತಿರುಕ್ಕುರಳ್ ಕೋಣೆ ಬರಯ್ಲೆಂ?", ("ತಿರುವಳ್ಳುವರ್", "ಕಂಬರ್", "ಇಳಂಗೊ", "ಅವ್ವೈಯಾರ್"))
    wrong = _q(app, "Hindi", "तिरुक्कुरल किसने लिखा?", ("तिरुवल्लुवर", "कम्बर", "इलंगो", "अव्वैयार"))
    rep = _report(app)
    kinds = {p["row"]["id"]: p["kind"] for p in rep["problems"]}
    assert kinds == {english: "script", wrong: "code"}
    assert _lang(rep, "bn")["usable"] == 2 and _lang(rep, "bn")["other_script"] == 1
    assert rep["faulty_ids"] == [] and rep["notes"] == 2
    assert "Written wholly in Latin letters" in next(p["why"] for p in rep["problems"] if p["kind"] == "script")


def test_the_generated_questions_have_no_fault_and_a_second_run_is_seen_twice():
    from kts import kural as K
    from kts.db import executemany, utcnow
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for lang in ("ta", "hi", "en", "ks", "sat", "kok", "ur"):
            rows = K.generate_questions(lang, 60, "check")
            executemany("INSERT INTO questions(lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active, source, created_at) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,1,'auto',?)",
                        [(r["lang"], r["qtype"], r["text"], r["opt_a"], r["opt_b"], r["opt_c"], r["opt_d"], r["correct"],
                          r["kural_no"], r["difficulty"], utcnow()) for r in rows])
    rep = _report(app)
    assert rep["faulty_ids"] == []
    # only the general-knowledge questions in English are in another script, and only outside English, Tamil and Hindi
    assert {p["row"]["lang"] for p in rep["problems"]} <= {"ks", "sat", "kok", "ur"}
    assert all(p["kind"] == "script" and p["row"]["qtype"] == "gk" for p in rep["problems"])
    with app.app_context():
        rows = K.generate_questions("ta", 60, "check")
        executemany("INSERT INTO questions(lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active, source, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,1,'auto',?)",
                    [(r["lang"], r["qtype"], r["text"], r["opt_a"], r["opt_b"], r["opt_c"], r["opt_d"], r["correct"],
                      r["kural_no"], r["difficulty"], utcnow()) for r in rows])
    rep = _report(app)
    assert len(rep["faulty_ids"]) == 60 and _lang(rep, "ta")["usable"] == 60


def test_the_page_the_csv_and_setting_aside():
    from kts.db import query
    app = make_app(ADMIN_PASSWORD=None)
    _many(app, "en", 110)
    bad = _q(app, "en", "Which option?", ("Virtue", "Virtue", "Wealth", "Love"))
    dup = _q(app, "en", "Question en 3?", ("x", "y", "z", "w"))
    admin = _staff(app, "qb-admin@tests.example", role="admin")
    page = admin.get("/console/questions/check").get_data(as_text=True)
    assert "Check of the question bank" in page and "Options alike" in page and "Twice in the bank" in page
    assert "Set aside the 2 faulty question(s)" in page and "Ready: 110 questions for papers of 50." in page
    assert "Short by 50: each paper gets 0" not in page and "Empty: a paper would be wholly in English (50 questions)." in page
    assert admin.get("/console/questions/check?lang=hi").status_code == 200
    csv = admin.get("/console/questions/check.csv")
    assert csv.status_code == 200 and csv.mimetype == "text/csv"
    body = csv.get_data().decode("utf-8-sig")
    assert body.splitlines()[0] == "id,lang,problem,action,explanation,text,opt_a,opt_b,opt_c,opt_d,correct,source"
    assert f"{bad},en,same,set aside," in body and f"{dup},en,duplicate,set aside," in body
    assert "Check the bank" in admin.get("/console/questions").get_data(as_text=True)
    dash = admin.get("/console/").get_data(as_text=True)
    assert "1 of 23 languages can fill a paper · 22 short · 2 faulty question(s)" in dash and "Check the bank" in dash
    # a viewer sees the check, but neither the answers in the CSV nor the button
    viewer = _staff(app, "qb-viewer@tests.example", role="viewer")
    seen = viewer.get("/console/questions/check")
    assert seen.status_code == 200 and "Set aside the" not in seen.get_data(as_text=True)
    assert viewer.get("/console/questions/check.csv").status_code == 403
    assert viewer.post("/console/questions/check", data={"_csrf": _token(viewer), "action": "set_aside"}).status_code == 403
    r = admin.post("/console/questions/check", data={"_csrf": _token(admin), "action": "set_aside"})
    assert r.status_code == 302
    with app.app_context():
        assert {q["id"]: q["active"] for q in query("SELECT id, active FROM questions WHERE id IN (?, ?)", (bad, dup))} == {bad: 0, dup: 0}
        assert query("SELECT COUNT(*) AS n FROM questions WHERE active = 1", one=True)["n"] == 110
        assert query("SELECT detail FROM audit_log WHERE action = 'questions_set_aside'", one=True)["detail"].startswith('{"count": 2')
    page = admin.get("/console/questions/check").get_data(as_text=True)
    assert "Set aside the" not in page and "No problem found." in page


def test_the_form_and_the_import_keep_faults_out():
    from kts.db import query
    app = make_app(ADMIN_PASSWORD=None)
    admin = _staff(app, "qb-form@tests.example", role="admin")
    form = {"_csrf": _token(admin), "lang": "en", "qtype": "manual", "text": "Which?", "opt_a": "Virtue", "opt_b": " virtue",
            "opt_c": "Wealth", "opt_d": "Love", "correct": "A", "active": "1"}
    page = admin.post("/console/questions/new", data=form, follow_redirects=True).get_data(as_text=True)
    assert "Two of the options are the same" in page
    form["opt_b"] = "Love of wealth"
    admin.post("/console/questions/new", data=form)
    data = ("lang,text,opt_a,opt_b,opt_c,opt_d,correct\n"
            "HI,प्रश्न एक?,क,ख,ग,घ,A\n"
            "Hindi,प्रश्न दो?,क,ख,ग,घ,A\n"
            "hi,प्रश्न तीन?,क,,ग,घ,B\n"
            "hi,प्रश्न चार?,क,ख,ग,घ,E\n").encode("utf-8")
    page = admin.post("/console/questions/import", data={"_csrf": _token(admin), "file": (io.BytesIO(data), "bank.csv")},
                      content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "Imported 1 question(s); skipped 3 (a language code that is not one of the 23" in page
    with app.app_context():
        assert [(q["lang"], q["text"]) for q in query("SELECT lang, text FROM questions ORDER BY id")] == [("en", "Which?"), ("hi", "प्रश्न एक?")]

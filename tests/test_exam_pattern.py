"""
Pattern of the online test: 50 objective multiple-choice questions, 2 marks each, no negative marking.

    python -m pytest tests -q
"""
from conftest import make_app

LINE = "50 objective multiple-choice questions · 2 marks each · no negative marking"


def _restart(app):
    """The portal started again on the same database and the same folders."""
    return make_app(**{name: app.config[name] for name in ("INSTANCE_DIR", "DATABASE", "UPLOAD_DIR")})


def _settings(app):
    from kts.db import all_settings
    with app.app_context():
        return all_settings()


def test_the_pages_state_the_pattern():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    for path in ("/examination", "/programme"):
        assert LINE in client.get(path + "?lang=en").get_data(as_text=True), path
    assert "50 objective multiple-choice questions" in client.get("/?lang=en").get_data(as_text=True)


def test_the_pattern_gives_100_marks():
    s = _settings(make_app(ADMIN_PASSWORD=None))
    assert (s["exam.questions"], s["exam.marks_per_q"], s["exam.negative"]) == ("50", "2", "0")
    assert int(s["exam.questions"]) * float(s["exam.marks_per_q"]) == 100


def test_a_database_with_the_old_pattern_is_brought_up_to_date():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("exam.questions", "25")
        set_setting("exam.marks_per_q", "4")
    s = _settings(_restart(app))
    assert (s["exam.questions"], s["exam.marks_per_q"]) == ("50", "2")


def test_a_pattern_chosen_in_the_console_stays():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("exam.questions", "40")
        set_setting("exam.marks_per_q", "2.5")
    s = _settings(_restart(app))
    assert (s["exam.questions"], s["exam.marks_per_q"]) == ("40", "2.5")
    page = _restart(app).test_client().get("/examination?lang=en").get_data(as_text=True)
    assert "40 objective multiple-choice questions · 2.5 marks each" in page


def test_the_pattern_in_other_languages_carries_the_numbers():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for lang in ("ta", "hi", "ur", "sat"):
        page = client.get(f"/examination?lang={lang}").get_data(as_text=True)
        assert "50 " in page and " 2 " in page, lang

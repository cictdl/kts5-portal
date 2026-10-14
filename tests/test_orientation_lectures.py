"""
The online orientation has two lectures, each followed by a 20-minute live question-and-answer segment, no longer ten
(version 1.2.71): the default note of the Orientation page, the old note of the settings that follows, and the wording of
every language.

    python -m pytest tests -q
"""
import re

from conftest import make_app

KEYS = ("reg.pref_help", "res.orient_intro", "home.orient_sub", "home.step_orient_sub", "about.p2", "prog.i5.d",
        "set.orientation_note")


def test_the_note_and_its_old_wording():
    from kts.db import DEFAULT_SETTINGS, RETIRED_DEFAULTS
    assert "(2 lectures + 20-minute live Q&A)" in DEFAULT_SETTINGS["orientation.note"]
    assert any("(10 lectures + 20-minute live Q&A)" in old for old in RETIRED_DEFAULTS["orientation.note"])


def test_no_language_says_ten_lectures_any_more():
    from kts.i18n import CATALOG
    for key in KEYS:
        assert not re.search(r"\bten\b|\bten-|(?<!\d)10(?!\d)", CATALOG["en"][key], re.I), key
    assert "2 lectures" in CATALOG["en"]["home.orient_sub"] and "two-lecture" in CATALOG["en"]["about.p2"]
    for code, catalogue in CATALOG.items():
        for key in KEYS:
            assert not re.search(r"(?<!\d)10(?!\d)", catalogue[key]), (code, key)
        assert re.search(r"(?<!\d)2(?!\d)", catalogue["home.orient_sub"]), code


def test_the_pages_say_two_lectures():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    home = client.get("/?lang=en").get_data(as_text=True)
    assert "2 lectures and a 20-minute question-and-answer session" in home and "10 lectures" not in home
    orientation = client.get("/orientation?lang=en").get_data(as_text=True)
    assert "A two-lecture academic series on the Thirukkural" in orientation
    assert "(2 lectures + 20-minute live Q&amp;A)" in orientation and "10 lectures" not in orientation
    programme = client.get("/programme?lang=en").get_data(as_text=True)
    assert "A two-part series of academic video lectures" in programme

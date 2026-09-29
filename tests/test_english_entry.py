"""
The registration form is filled in English by every applicant, whatever the language of the page.

    python -m pytest tests -q
"""
import pytest

from conftest import make_app
from test_public_fixes import _register, _stored

ENGLISH = ["full_name", "address", "district", "college_name", "aishe_code", "college_district", "university",
           "discipline", "roll_no", "mentor_name", "mentor_designation"]


# every test has a database of its own (make_app with a setting)


def _message(lang):
    from kts import i18n
    return i18n.text("reg.err_english", lang)


def _row(app):
    from kts.db import query
    with app.app_context():
        return query("SELECT * FROM applications ORDER BY id DESC LIMIT 1", one=True)


def test_an_application_in_english_is_accepted():
    app = make_app(ADMIN_PASSWORD=None)
    r = _register(app, 1, address="No. 12/3, 2nd Street (near Bus Stand), Thrissur - 680001",
                  university="University of Calicut", discipline="B.Sc. Physics & Maths", roll_no="21/PHY#07",
                  mentor_name="Dr. K. Anand", mentor_designation="Asst. Professor, Dept. of Physics")
    assert r.status_code == 302, r.get_data(as_text=True)[:500]
    assert _stored(app) == 1


@pytest.mark.parametrize("name", ["முருகன்", "राम कुमार", "Ramesh குமார்", "راجیش", "Ｒａｍｅｓｈ"])
def test_a_name_in_another_script_is_refused(name):
    app = make_app(ADMIN_PASSWORD=None)
    r = _register(app, 1, full_name=name)
    assert r.status_code == 400
    assert _message("en") in r.get_data(as_text=True)
    assert _stored(app) == 0


@pytest.mark.parametrize("field", ENGLISH)
def test_every_written_field_asks_for_english(field):
    app = make_app(ADMIN_PASSWORD=None)
    r = _register(app, 1, **{field: "कॉलेज"})
    assert r.status_code == 400, field
    page = r.get_data(as_text=True)
    assert _message("en") in page, field
    assert _stored(app) == 0


def test_the_curly_marks_of_phone_keyboards_are_made_plain():
    app = make_app(ADMIN_PASSWORD=None)
    r = _register(app, 1, full_name="Mary D’Souza", college_name="St. Joseph’s College – Autonomous",
                  address="Flat 4 B, “Sea View”…")
    assert r.status_code == 302
    row = _row(app)
    assert row["full_name"] == "Mary D'Souza"
    assert row["college_name"] == "St. Joseph's College - Autonomous"
    assert row["address"] == 'Flat 4 B, "Sea View"...'


@pytest.mark.parametrize("lang", ["ta", "hi", "ur", "sat"])
def test_the_message_is_in_the_language_of_the_page(lang):
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    client.get(f"/register?lang={lang}")
    with client.session_transaction() as s:
        token = s["_csrf"]
        s["_captcha"] = "7"
    import io
    from test_public_fixes import PNG
    form = {"_csrf": token, "full_name": "முருகன்", "gender": "M", "dob": "2004-05-06", "mobile": "9876500001",
            "email": "m@tests.example", "state": "Tamil Nadu", "college_name": "Government College",
            "college_type": "Government college", "college_state": "Tamil Nadu", "course_level": "Undergraduate",
            "year_of_study": "2nd year", "pref_lang": "hi", "declare_true": "1", "declare_participate": "1",
            "declare_consent": "1", "captcha": "7", "photo": (io.BytesIO(PNG), "p.png"), "idproof": (io.BytesIO(PNG), "i.png")}
    r = client.post("/register", data=form, content_type="multipart/form-data")
    assert r.status_code == 400
    assert _message(lang) in r.get_data(as_text=True)


@pytest.mark.parametrize("lang", ["en", "ta", "ur", "ks"])
def test_the_form_says_so_and_types_left_to_right(lang):
    page = make_app(ADMIN_PASSWORD=None).test_client().get(f"/register?lang={lang}").get_data(as_text=True)
    from kts import i18n
    assert i18n.text("reg.english_note", lang) in page
    for field in ENGLISH:
        start = page.rfind("<", 0, page.find(f'name="{field}"'))
        whole = page[start:page.find(">", start) + 1]
        assert 'dir="ltr"' in whole and 'lang="en"' in whole, (lang, field, whole)

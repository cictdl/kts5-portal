"""
The sign-in of the institutions without a mailed code, for the genuine institutions on the last day (1.2.217): what an independent
test of 1.2.216 found.

* Every number that stands in the coordinator's field signs in, as the form, a list of a Nodal Institution or a correction in the
  Console left it; no number is read across a slash, a comma or a word.
* The sign-in page takes long forms of a number, does not offer the visitor's own number, and tells the Head of two institutions
  how to open the other.
* A code of 1.2.215 that has run out leads to the e-mail address and the mobile number; the wait names another connection; the page
  after a registration offers the sign-in.

    python -m pytest tests/test_signin_numbers_1126.py -q
"""
import pytest

from test_signin_no_code_1126 import EMAIL, MOBILE, _app, _client, _mails, _make, _sign_in, _signed_in

A, B = "9811111111", "9822222222"


@pytest.fixture(autouse=True)
def fresh_limiter():
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def _numbers(value):
    from kts.campus import _coordinator_numbers
    return _coordinator_numbers({"coord_mobile": value})


# the shapes of the field that the test of 1.2.216 tried; the first thirteen signed in already, the other twelve did not
SHAPES = [
    ("98110 11111", ["9811011111"]), ("+91-98110-11111", ["9811011111"]), (f"{A} / {B}", [A, B]), (f"{A}, {B}", [A, B]),
    (f"{A} or {B}", [A, B]), (f"Dr. K: {A}", [A]), (f"{A} (new no.)", [A]), (f"{A}/044 2254 1234 (office)", [A, "4422541234"]),
    (f"{A} [M], {B} [R]", [A, B]), (f"o{A}", [A]), (f"{A}*", [A]), ("98220-12345/46", ["9822012345"]),
    (f"(M) {A}; (O) 044-22541234", [A, "4422541234"]),
    (f"{A} {B}", [A, B]), (f"{A} & {B}", [A, B]), (f"{A} and {B}", [A, B]), (f"{A} (O) 044-22541234", [A, "4422541234"]),
    (f"{A} (WhatsApp {B})", [A, B]), (f"{A} Extn 123", [A]), (f"{A}\\{B}", [A, B]), (f"{A}:{B}", [A, B]), (f"{A} . {B}", [A, B]),
    (f"{A} उर्फ {B}", [A, B]), (f"+91 {A} +91 {B}", [A, B]),
]


@pytest.mark.parametrize("value, expected", SHAPES)
def test_every_number_of_the_field(value, expected):
    assert _numbers(value) == expected


@pytest.mark.parametrize("value, expected", [
    ("+91 (0) 90000 00001", ["9000000001"]), ("0091 9000000001", ["9000000001"]), ("tel:+919876543210", ["9876543210"]),
    ("९८११११११११", [A]), ("‪+91 98111 11111‬", [A]), ("98 11 11 11 11", [A]), ("981-111-1111", [A]),
    ("9198765432/10", ["9198765432"]),         # not 9876543210, read across the slash
    ("9876543210,9123456780", ["9876543210", "9123456780"]),
    ("N/A", []), ("", []), ("90000 0000", []), ("0000000000", []), ("900000000100", []), ("9" * 20, []), ("12345", []),
])
def test_what_is_read_and_what_is_not(value, expected):
    assert _numbers(value) == expected


@pytest.mark.parametrize("stored, typed", [(f"{A} {B}", A), (f"{A} {B}", B), (f"{A} & {B}", B), (f"{A} Extn 123", A),
                                           (f"{A} (WhatsApp {B})", B), (f"+91 {A} +91 {B}", "+91 " + B)])
def test_the_institution_signs_in_with_each_number(stored, typed):
    from kts.db import execute
    app, iid = _app()
    with app.app_context():
        execute("UPDATE institutions SET coord_mobile = ? WHERE id = ?", (stored, iid))
    client, r = _sign_in(app, EMAIL, typed)
    assert r.status_code == 302 and _signed_in(client)
    _c, r = _sign_in(app, EMAIL, "9833333333")
    assert r.status_code == 400


def test_no_number_across_a_slash_signs_in():
    from kts.db import execute
    app, iid = _app()
    with app.app_context():
        execute("UPDATE institutions SET coord_mobile = '9198765432/10' WHERE id = ?", (iid,))
    _c, r = _sign_in(app, EMAIL, "9876543210")
    assert r.status_code == 400
    client, r = _sign_in(app, EMAIL, "9198765432")
    assert r.status_code == 302 and _signed_in(client)


def test_the_page_for_a_genuine_institution():
    app, _iid = _app()
    page = app.test_client().get("/institution/login").get_data(as_text=True)
    field = page[page.index('<input type="tel" id="mobile"'):]
    field = field[:field.index(">")]
    assert 'maxlength="32"' in field and 'autocomplete="off"' in field and "tel-national" not in field
    assert ("If your e-mail address serves more than one institution, each opens with the mobile number of\n      its own Institutional "
            "Coordinator: sign out, then sign in with that number.") in page.replace("\r\n", "\n")
    # a long form of the number, as a browser now sends it whole
    client, r = _sign_in(app, EMAIL, "+91 (0) 90000 00001")
    assert len("+91 (0) 90000 00001") > 16 and r.status_code == 302 and _signed_in(client)


def test_a_code_of_before_leads_to_the_number():
    from datetime import timedelta
    import re
    from kts import campus
    from kts.db import set_setting
    app, _iid = _app()
    with app.app_context():
        set_setting("inst.code_mail", "1")
    client, token = _client(app)
    client.post("/institution/login", data={"_csrf": token, "email": EMAIL})
    code = re.search(r"\n    (\d{6})\n", _mails(app, EMAIL)[-1]["body"]).group(1)
    with app.app_context():
        set_setting("inst.code_mail", "0")
    real = campus.now_ist
    try:
        campus.now_ist = lambda: real() + timedelta(minutes=61)
        r = client.post("/institution/code", data={"_csrf": token, "code": code})
    finally:
        campus.now_ist = real
    page = r.get_data(as_text=True)
    assert r.status_code == 400 and "The code has expired: sign in with the e-mail address and the mobile number below." in page
    assert 'name="mobile"' in page and "ask for a new one" not in page
    # with the codes mailed, as before
    with app.app_context():
        set_setting("inst.code_mail", "1")
    r = client.post("/institution/code", data={"_csrf": token, "code": "123456"})
    assert "The code has expired: ask for a new one." in r.get_data(as_text=True)


def test_the_page_after_a_registration_offers_the_sign_in():
    from kts.db import query
    app, iid = _app()
    with app.app_context():
        ref = query("SELECT ref FROM institutions WHERE id = ?", (iid,), one=True)["ref"]
    client = app.test_client()
    with client.session_transaction() as s:
        s["hei_applied"] = iid
    page = client.get(f"/institutions/register/done/{ref}?lang=en").get_data(as_text=True)
    assert '<a class="btn" href="/institution/login">Institution sign-in</a>' in page
    assert MOBILE not in page

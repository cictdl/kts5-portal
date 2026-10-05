"""
The public pages: the language switch, the limits of registration, status look-up and contact
form, dates typed into the address, the language tags of the streams of the Thirukkural, the
alternate links, the Content-Security-Policy, the files that were uploaded and the small routes.

    python -m pytest tests -q

Every application built here works inside the temporary folder of tests/conftest.py. The
limiter belongs to the process, not to an application, so every test starts with an empty one.
"""
import csv
import io
import os
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import pytest
from markupsafe import escape

from conftest import ROOT, TMP, make_app

TEMPLATES = sorted((ROOT / "templates").rglob("*.html"))
SCRIPT = (ROOT / "static" / "js" / "portal.js").read_text(encoding="utf-8")
STYLES = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 200
PDF = b"%PDF-1.4\n%%EOF\n"
SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><circle cx="20" cy="20" r="18"/>'
       b'<script>document.title = "ran"</script></svg>\n')
HOME = "http://localhost"  # the address of the portal as the test client asks for it
FIRST = "first@tests.example"
STAFF_PASSWORD = "Staff-" + TMP.name[-8:] + "-4K"


@pytest.fixture(autouse=True)
def empty_limiter():
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def _text(key, lang="en"):
    """The text of a key as it stands in a page."""
    from kts.i18n import CATALOG
    return str(escape(CATALOG[lang][key]))


def _page(client, path, **kwargs):
    r = client.get(path, **kwargs)
    assert r.status_code == 200, path
    return r.data.decode("utf-8")


def _codes():
    from kts.i18n import LANG_INFO
    return list(LANG_INFO)


def _staff(app, email=FIRST, role=None):
    """
    A client that has signed in: as the first administrator, who has set his password, or as a
    member of staff with the given role, whose account is made here.
    """
    from werkzeug.security import generate_password_hash
    from kts.db import execute, query, utcnow
    password = STAFF_PASSWORD if role else os.environ["KTS_ADMIN_PASSWORD"]
    with app.app_context():
        if role:
            agency = query("SELECT id FROM agencies ORDER BY id LIMIT 1", one=True)["id"] if role == "agency" else None
            execute("INSERT INTO users(email, name, password_hash, role, agency_id, active, must_change_password, created_at) "
                    "VALUES(?,?,?,?,?,1,0,?)", (email, "Test " + role, generate_password_hash(password), role, agency, utcnow()))
        else:
            execute("UPDATE users SET must_change_password = 0 WHERE email = ?", (email,))
    client = app.test_client()
    client.get("/console/login")
    with client.session_transaction() as s:
        token = s["_csrf"]
    r = client.post("/console/login", data={"_csrf": token, "email": email, "password": password})
    assert r.status_code == 302
    return client


def _put(app, *names, content):
    """Files in the upload folder, as save_upload leaves them there."""
    folder = Path(app.config["UPLOAD_DIR"])
    for name in names:
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(content)


# ---- B1 · language switch ----------------------------------------------------------

def _switch(app, address, referrer=None, client=None):
    client = client or app.test_client()
    return client.get(address, headers={"Referer": referrer} if referrer is not None else {})


SWITCH = [
    # the page the visitor came from, without its 'lang'
    (HOME + "/about", "/about"),
    (HOME + "/about?lang=bn", "/about"),
    (HOME + "/thirukkural?lang=hi&ch=5", "/thirukkural?ch=5"),
    (HOME + "/thirukkural?ch=5&lang=bn", "/thirukkural?ch=5"),
    (HOME + "/thirukkural?ch=5&lang=bn&l=ksn", "/thirukkural?ch=5&l=ksn"),
    (HOME + "/daily-kural?lang=ur&d=2026-10-02&lang=ks&l=te", "/daily-kural?d=2026-10-02&l=te"),
    (HOME + "/resources?q=a%26b+c&lang=ta&cat=video", "/resources?q=a%26b+c&cat=video"),
    (HOME + "/merit-list?language=x&lang=", "/merit-list?language=x"),
    (HOME + "/?lang=sat", "/"),
    (HOME, "/"),
    ("http://LOCALHOST/about", "/about"),
    # another host, also one whose name merely starts like the portal's
    ("https://example.org/landing?x=1", "/"),
    ("https://example.org/", "/"),
    ("http://localhost.example.org/x", "/"),
    ("http://localhost@example.org/x", "/"),
    ("http://example.org@localhost/x", "/"),
    ("http://localhost:8080/about", "/"),
    # an address that a browser would read as another host
    (HOME + "//example.org/x", "/"),
    (HOME + "/\\example.org/x", "/"),
    (HOME + "/\t/example.org/x", "/"),
    # no address of a page
    ("//localhost/about", "/"),
    ("/about", "/"),
    ("ftp://localhost/about", "/"),
    ("javascript:alert(1)", "/"),
    ("http://[::1/about", "/"),
    ("", "/"),
    (None, "/"),
    # the switch itself
    (HOME + "/lang/hi", "/"),
    (HOME + "/lang/hi/", "/"),
    (HOME + "/lang?code=hi", "/"),
    (HOME + "/language", "/language"),
]


@pytest.mark.parametrize("address", ["/lang/ta", "/lang?code=ta"])
@pytest.mark.parametrize("referrer, target", SWITCH)
def test_switch_leads_to_a_page_of_the_portal(app, address, referrer, target):
    r = _switch(app, address, referrer)
    assert r.status_code == 302 and r.headers["Location"] == target
    assert "example.org" not in r.data.decode("utf-8")


@pytest.mark.parametrize("address", ["/lang/ta", "/lang?code=ta"])
def test_switch_on_an_address_with_lang(app, address):
    """The 23 alternate links advertise addresses with ?lang=; the menu has to work on them."""
    client = app.test_client()
    came = "/thirukkural?lang=hi&ch=5"
    assert '<html lang="hi"' in _page(client, came)
    r = _switch(app, address, HOME + came, client)
    assert r.headers["Location"] == "/thirukkural?ch=5"
    page = _page(client, r.headers["Location"])
    assert '<html lang="ta" dir="ltr"' in page and 'id="k41"' in page and 'id="k1"' not in page
    # and the choice stays on the pages that follow
    assert '<html lang="ta"' in _page(client, "/programme")


def test_switch_to_an_unknown_language(app):
    client = app.test_client()
    r = _switch(app, "/lang/zz", HOME + "/about?lang=hi", client)
    assert r.status_code == 302 and r.headers["Location"] == "/about"
    assert not [c for c in r.headers.getlist("Set-Cookie") if c.startswith("lang=")]
    r = _switch(app, "/lang/zz", "https://example.org/")
    assert r.headers["Location"] == "/"


def test_switch_under_a_path_prefix():
    own = make_app(URL_PREFIX="/kts5")
    for referrer, target in [(HOME + "/kts5/about?lang=hi", "/kts5/about"), (HOME + "/kts5/thirukkural?ch=5", "/kts5/thirukkural?ch=5"),
                             (HOME + "/kts5/lang/hi", "/kts5/"), (HOME + "/kts5", "/kts5"), (HOME + "/other/page", "/kts5/"),
                             (HOME + "/kts5x/page", "/kts5/"), ("https://example.org/kts5/about", "/kts5/"), (None, "/kts5/")]:
        r = _switch(own, "/kts5/lang/ta", referrer)
        assert r.status_code == 302 and r.headers["Location"] == target, referrer


def test_switch_behind_a_web_server_with_a_host_header_of_its_own():
    """ARR and nginx ask the portal as 127.0.0.1:<port>; the visitor names it as BASE_URL does."""
    own = make_app(BASE_URL="https://Portal.Example/")
    for referrer, target in [("https://portal.example/about", "/about"),
                             ("https://PORTAL.example/thirukkural?ch=5&lang=hi", "/thirukkural?ch=5"),
                             ("http://portal.example/about", "/about"),
                             (HOME + "/about", "/about"),
                             # another host, another port, a name that merely starts or ends like it
                             ("https://example.org/about", "/"),
                             ("https://portal.example:8443/about", "/"),
                             ("https://portal.example.org/about", "/"),
                             ("https://my-portal.example/about", "/"),
                             ("https://portal.example@example.org/about", "/"),
                             ("https://portal.example//example.org/x", "/"),
                             ("https://portal.example/lang/hi", "/")]:
        r = _switch(own, "/lang/ta", referrer)
        assert r.status_code == 302 and r.headers["Location"] == target, referrer


@pytest.mark.parametrize("base", ["portal.example", "", "/", "http://", "https://[::1", "//", "mailto:office@portal.example"])
def test_switch_with_a_base_address_that_names_no_host(base):
    own = make_app(BASE_URL=base)
    for referrer, target in [(HOME + "/about", "/about"), ("http:///about", "/"), ("https:/about", "/"), ("http://", "/"),
                             ("https://portal.example/about", "/"), ("http://[::1/about", "/")]:
        r = _switch(own, "/lang/ta", referrer)
        assert r.status_code == 302 and r.headers["Location"] == target, referrer


def _lang_cookie(response):
    found = [c for c in response.headers.getlist("Set-Cookie") if c.startswith("lang=")]
    assert len(found) == 1
    name_value, *flags = [part.strip() for part in found[0].split(";")]
    return name_value, {flag.split("=")[0].lower(): flag.partition("=")[2] for flag in flags}


@pytest.mark.parametrize("address", ["/lang/ta", "/lang?code=ta"])
def test_cookie_of_the_language(app, address):
    value, flags = _lang_cookie(_switch(app, address))
    assert value == "lang=ta"
    assert "httponly" in flags and flags["samesite"] == "Lax" and flags["path"] == "/"
    assert flags["max-age"] == str(365 * 24 * 60 * 60)
    assert "secure" not in flags  # the tests run without https, as the session cookie says
    assert app.config["SESSION_COOKIE_SECURE"] is False


def test_cookie_of_the_language_under_https():
    own = make_app(SESSION_COOKIE_SECURE=True)
    r = own.test_client().get("/lang/ta", base_url="https://localhost")
    value, flags = _lang_cookie(r)
    assert value == "lang=ta" and "secure" in flags and "httponly" in flags and flags["samesite"] == "Lax"
    session = [c for c in r.headers.getlist("Set-Cookie") if c.startswith("session=")]
    assert session and "Secure" in session[0] and "HttpOnly" in session[0]


def test_script_does_not_read_cookies():
    assert "cookie" not in SCRIPT.lower()


# ---- B2 · limits: registration, status look-up, contact form -----------------------------

def _files(app):
    folder = Path(app.config["UPLOAD_DIR"])
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file())


def _register(app, n, ip="198.51.100.40", photo=PNG, idproof=PNG, **changed):
    """One application, complete and correct unless something is changed."""
    client = app.test_client()
    client.get("/register")
    with client.session_transaction() as s:
        token = s["_csrf"]
        s["_captcha"] = "7"
    form = {
        "_csrf": token, "full_name": f"Student {n}", "gender": "F", "dob": "2004-05-06", "category": "General",
        "mobile": f"98765{n:05d}", "email": f"student{n}@tests.example", "state": "Kerala",
        "college_name": "Government College Thrissur", "college_type": "Government college", "college_state": "Kerala",
        "course_level": "Undergraduate", "year_of_study": "2nd year", "pref_lang": "hi", "declare_true": "1",
        "declare_participate": "1", "declare_consent": "1", "captcha": "7",
    }
    if photo is not None:
        form["photo"] = (io.BytesIO(photo), "photo.png")
    if idproof is not None:
        form["idproof"] = (io.BytesIO(idproof), "id.png")
    form.update(changed)
    return client.post("/register", data=form, content_type="multipart/form-data", environ_base={"REMOTE_ADDR": ip})


def _stored(app):
    from kts.db import query
    with app.app_context():
        return query("SELECT COUNT(*) AS n FROM applications", one=True)["n"]


def test_refused_registration_leaves_no_file():
    own = make_app(RATE_REGISTER_PER_HOUR=2)
    assert _files(own) == []
    for n in (1, 2):
        r = _register(own, n)
        assert r.status_code == 302 and "/register/done/" in r.headers["Location"]
    assert len(_files(own)) == 4 and _stored(own) == 2
    before = _files(own)
    for n in (3, 4, 5):
        r = _register(own, n)
        assert r.status_code == 400 and _text("reg.err_rate") in r.data.decode("utf-8")
    assert _files(own) == before and _stored(own) == 2
    # somebody else is not held up
    r = _register(own, 6, ip="198.51.100.41")
    assert r.status_code == 302
    assert len(_files(own)) == 6 and _stored(own) == 3


def _notice(key, lang="en"):
    """The notice at the top of a page."""
    return f'<div class="alert error" role="status">{_text(key, lang)}</div>'


def _marked(page):
    """The fields that a page marks as wrong, and the texts that stand under them."""
    return (re.findall(r'<div class="field[^"]*\bhas-err\b[^"]*">\s*<label for="([^"]+)"', page),
            re.findall(r'<span class="err">(.*?)</span>', page))


def test_refused_registration_is_said_at_the_top():
    own = make_app(RATE_REGISTER_PER_HOUR=1)
    assert _register(own, 1).status_code == 302
    # the limit is no mistake of the applicant: no field is marked, least of all the security question
    r = _register(own, 2)
    page = r.data.decode("utf-8")
    assert r.status_code == 400 and _notice("reg.err_rate") in page
    assert _marked(page) == ([], []) and "has-err" not in page
    assert page.count(_text("reg.err_rate")) == 1 and _text("reg.err_fix") not in page
    assert _text("common.captcha_help") in page
    # what was typed stays in the form, nothing of it is stored
    assert 'value="Student 2"' in page and 'value="student2@tests.example"' in page
    assert _stored(own) == 1 and len(_files(own)) == 2
    # a mistake is marked as before, and said before the limit
    r = _register(own, 3, captcha="8")
    page = r.data.decode("utf-8")
    assert r.status_code == 400 and _notice("reg.err_fix") in page and _text("reg.err_rate") not in page
    assert _marked(page) == (["captcha"], [_text("reg.err_captcha")])
    r = _register(own, 3, mobile="12345")
    assert _marked(r.data.decode("utf-8")) == (["mobile"], [_text("reg.err_mobile")])
    # an applicant who is known already is told so, limit or not
    r = _register(own, 1)
    page = r.data.decode("utf-8")
    assert _notice("reg.err_fix") in page and _text("reg.err_rate") not in page
    assert _marked(page)[1] == [_text("reg.err_dup_mobile"), _text("reg.err_dup_email")]
    assert _stored(own) == 1 and len(_files(own)) == 2
    # the refusals were not counted: after the hour the place is free
    from kts.utils import limiter
    assert len(limiter._hits[("register", "198.51.100.40")][1]) == 1


def test_only_stored_applications_are_counted():
    own = make_app(RATE_REGISTER_PER_HOUR=2)
    for n in range(1, 6):
        assert _register(own, n, captcha="8").status_code == 400
        assert _register(own, n, mobile="12345").status_code == 400
        assert _register(own, n, idproof=b"no picture").status_code == 400
    assert _files(own) == [] and _stored(own) == 0
    assert _register(own, 1).status_code == 302 and _register(own, 2).status_code == 302
    assert _register(own, 3).status_code == 400
    assert len(_files(own)) == 4


@pytest.mark.parametrize("bad, key", [("idproof", "reg.err_idproof"), ("photo", "reg.err_photo")])
def test_one_upload_fails_and_the_other_is_removed(bad, key):
    own = make_app(RATE_REGISTER_PER_HOUR=3)
    r = _register(own, 1, **{bad: b"this is no picture"})
    assert r.status_code == 400 and _text(key) in r.data.decode("utf-8")
    assert _files(own) == [] and _stored(own) == 0
    # a file that is empty, a file that is missing altogether
    for content in (b"", None):
        r = _register(own, 1, **{bad: content})
        assert r.status_code == 400 and _text(key) in r.data.decode("utf-8")
        assert _files(own) == [] and _stored(own) == 0
    # the same applicant with both files
    assert _register(own, 1).status_code == 302
    assert len(_files(own)) == 2


def _look_up(app, ip="198.51.100.50", **changed):
    client = app.test_client()
    client.get("/status")
    with client.session_transaction() as s:
        token = s["_csrf"]
    form = dict({"_csrf": token, "app_no": "KTS5-2026-000001", "dob": "2004-05-06", "last4": "0001"}, **changed)
    return client.post("/status", data=form, environ_base={"REMOTE_ADDR": ip}).data.decode("utf-8")


def test_status_counts_failed_look_ups_only():
    own = make_app(RATE_STATUS_FAILS_PER_15MIN=3)
    assert _register(own, 1).status_code == 302
    for _ in range(10):
        assert "Student 1" in _look_up(own)
    for _ in range(3):
        assert "Student 1" in _look_up(own)  # a look-up that finds the application costs nothing
        page = _look_up(own, last4="9999")
        assert _text("status.not_found") in page and "Student 1" not in page
    # the limit is reached: also the right details are refused, and the refusal is not counted
    for _ in range(3):
        page = _look_up(own)
        assert _text("reg.err_rate") in page and "Student 1" not in page and _text("status.not_found") not in page
    from kts.utils import limiter
    assert len(limiter._hits[("status", "198.51.100.50")][1]) == 3
    assert "Student 1" in _look_up(own, ip="198.51.100.51")


def test_status_limit_is_the_setting(app):
    assert app.config["RATE_STATUS_FAILS_PER_15MIN"] == 300
    own = make_app(RATE_STATUS_FAILS_PER_15MIN=30)
    for n in range(30):
        # another number each time: one number is refused after 6 failures from one address
        assert _text("status.not_found") in _look_up(own, ip="198.51.100.52", app_no=f"KTS5-2026-9{n:05d}")
    assert _text("reg.err_rate") in _look_up(own, ip="198.51.100.52", app_no="KTS5-2026-999999")
    assert _text("status.not_found") in _look_up(own, ip="198.51.100.53", app_no="KTS5-2026-999999")


def test_status_limit_per_number_and_address():
    own = make_app(RATE_CAND_FAILS_APP_PER_15MIN=4)
    assert _register(own, 1).status_code == 302
    for n in range(4):
        # small letters and capitals are one number
        page = _look_up(own, last4=f"900{n}", app_no="kts5-2026-000001" if n else "KTS5-2026-000001")
        assert _text("status.not_found") in page, n
    # closed for this address, also with the right details, and the refusal is not counted
    for last4 in ("9004", "0001"):
        page = _look_up(own, last4=last4)
        assert _text("reg.err_rate") in page and "Student 1" not in page
    from kts.utils import limiter
    assert len(limiter._hits[("status_app", "KTS5-2026-000001|198.51.100.50")][1]) == 4
    assert len(limiter._hits[("status", "198.51.100.50")][1]) == 4
    # another number from this address, and this number from another address
    assert _text("status.not_found") in _look_up(own, app_no="KTS5-2026-000002")
    assert "Student 1" in _look_up(own, ip="198.51.100.51")
    # the key is cut, whatever is typed
    _look_up(own, ip="198.51.100.54", app_no="k" * 40)
    assert ("status_app", "K" * 32 + "|198.51.100.54") in limiter._hits


def _write(app, ip="198.51.100.60", **changed):
    client = app.test_client()
    client.get("/contact")
    with client.session_transaction() as s:
        token = s["_csrf"]
        s["_captcha"] = "7"
    form = {"_csrf": token, "name": "A visitor", "email": "visitor@tests.example", "subject": "A question",
            "body": "When does the registration close?", "topic": "general", "captcha": "7"}
    form.update(changed)
    return client.post("/contact", data=form, environ_base={"REMOTE_ADDR": ip}).data.decode("utf-8")


def test_contact_limit_is_the_setting():
    own = make_app(RATE_CONTACT_PER_HOUR=7)
    from kts.db import query
    for _ in range(7):
        assert _text("reg.err_rate") not in _write(own)
    assert _text("reg.err_rate") in _write(own)
    with own.app_context():
        assert query("SELECT COUNT(*) AS n FROM messages", one=True)["n"] == 7
    assert _text("reg.err_rate") not in _write(own, ip="198.51.100.61")


def test_refused_message_is_said_at_the_top():
    own = make_app(RATE_CONTACT_PER_HOUR=1)
    from kts.db import query
    assert _text("contact.sent") in _write(own)
    page = _write(own)
    assert _notice("reg.err_rate") in page and page.count(_text("reg.err_rate")) == 1
    assert _marked(page) == ([], []) and "has-err" not in page and _text("contact.sent") not in page
    assert _text("common.captcha_help") in page
    # what was typed stays in the form, and the message is not stored
    assert 'value="A visitor"' in page and ">When does the registration close?</textarea>" in page
    with own.app_context():
        assert query("SELECT COUNT(*) AS n FROM messages", one=True)["n"] == 1
    # a mistake is marked as before, and said before the limit
    page = _write(own, captcha="8")
    assert _marked(page) == (["captcha"], [_text("reg.err_captcha")]) and _text("reg.err_rate") not in page
    page = _write(own, email="no address")
    assert _marked(page) == (["email"], [_text("reg.err_email")]) and _text("reg.err_rate") not in page
    from kts.utils import limiter
    assert len(limiter._hits[("contact", "198.51.100.60")][1]) == 1
    # the notice is shown once and does not wait for the next page
    client = own.test_client()
    assert _text("reg.err_rate") not in _page(client, "/contact")


def test_no_limit_is_written_into_the_code():
    source = (ROOT / "kts" / "public.py").read_text(encoding="utf-8")
    calls = re.findall(r"limiter\.(?:allow|blocked)\(([^\n]*)", source)
    assert [call.split(",")[0] for call in calls] == ['"register"', '"status"', '"status_app"', '"contact"']
    for call, name in zip(calls, ("RATE_REGISTER_PER_HOUR", "RATE_STATUS_FAILS_PER_15MIN",
                                  "RATE_CAND_FAILS_APP_PER_15MIN", "RATE_CONTACT_PER_HOUR")):
        assert f'current_app.config["{name}"]' in call, call


# ---- B3 · dates typed into the address ---------------------------------------------------

def _calendar(client, query):
    r = client.get("/daily-kural/calendar.csv" + query)
    assert r.status_code == 200 and r.mimetype == "text/csv", query
    rows = list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
    assert len(rows) == 201, query
    return rows[1:]


@pytest.mark.parametrize("start", ["9999-12-31", "9999-06-16", "2101-01-01", "2019-12-31", "0001-01-01", "garbage", "",
                                   "2026-02-30", "99999-01-01", "-1"])
def test_calendar_with_a_date_out_of_range(app, start):
    rows = _calendar(app.test_client(), "?start=" + start)
    assert rows[0][1] in (date.today().isoformat(), (date.today() - timedelta(days=1)).isoformat())


@pytest.mark.parametrize("start, last", [("2020-01-01", "2020-07-18"), ("2100-12-31", "2101-07-18"), ("2026-11-29", "2027-06-16")])
def test_calendar_with_a_date_in_range(app, start, last):
    rows = _calendar(app.test_client(), "?l=hi&start=" + start)
    assert rows[0][1] == start and rows[-1][1] == last
    assert all(row[-1] for row in rows)


@pytest.mark.parametrize("day, shown", [("9999-12-31", None), ("0001-01-01", None), ("2101-01-01", None), ("2019-12-31", None),
                                        ("garbage", None), ("2100-12-31", "2100-12-31"), ("2020-01-01", "2020-01-01"),
                                        ("2026-11-29", "2026-11-29")])
def test_daily_kural_with_a_date_typed_in(app, day, shown):
    page = _page(app.test_client(), "/daily-kural?d=" + day)
    value = re.search(r'<input type="date" id="d" name="d" value="([^"]*)"', page).group(1)
    if shown:
        assert value == shown
    else:
        assert value in (date.today().isoformat(), (date.today() - timedelta(days=1)).isoformat())


# ---- B4 · a couplet without text in a stream -----------------------------------------------

LAST_DAY_OF_CYCLE = "2029-08-22"  # couplet 1330, which the Kashmiri stream in Nastaliq does not have


def _stream_blocks(page):
    """(attributes, text) of every element that carries text of a stream other than Tamil."""
    found = re.findall(r'<div((?: class="trans")?(?: style="[^"]*")? dir="(?:ltr|rtl)" lang="[^"]+")>(.*?)</div>', page, re.S)
    return [(attrs, re.sub(r"<br>|\s+", " ", text).strip()) for attrs, text in found if 'lang="ta"' not in attrs]


@pytest.mark.parametrize("query", ["&l=ksn", "&lang=ks", "&l=ksn&lang=ur"])
def test_daily_kural_falls_back_to_english(app, query):
    from kts import kural as K
    k = K.kural(1330)
    assert K.daily_number(date.fromisoformat(LAST_DAY_OF_CYCLE)) == 1330 and K.lines(k, "ksn") == []
    page = _page(app.test_client(), f"/daily-kural?d={LAST_DAY_OF_CYCLE}{query}")
    blocks = _stream_blocks(page)
    assert len(blocks) == 1
    attrs, text = blocks[0]
    assert 'dir="ltr" lang="en"' in attrs
    assert text == str(escape(" ".join(K.lines(k, "en"))))
    assert not re.search(r"<(div|p)[^>]* lang=[^>]*>\s*</(div|p)>", page)
    # the menu keeps the stream that was chosen
    assert '<option value="ksn" selected>' in page
    # the day before has the text of the stream itself
    page = _page(app.test_client(), f"/daily-kural?d=2029-08-21{query}")
    attrs, text = _stream_blocks(page)[0]
    assert 'dir="rtl" lang="ks-Arab"' in attrs and text == str(escape(" ".join(K.lines(K.kural(1329), "ksn"))))


def test_calendar_has_a_dash_for_a_couplet_without_text(app):
    rows = _calendar(app.test_client(), f"?l=ksn&start={LAST_DAY_OF_CYCLE}")
    assert rows[0][2] == "1330" and rows[0][-1] == "—"
    assert rows[1][2] == "1" and len(rows[1][-1]) > 10
    assert all(row[-1] for row in rows)


# ---- B5 · language tags of the streams -------------------------------------------------------

SCRIPTS = {"Arab": ("ARABIC", "Arabic"), "Deva": ("DEVANAGARI", "Devanagari"), "Knda": ("KANNADA", "Kannada"),
           "Beng": ("BENGALI", "Bengali"), "Mtei": ("MEETEI", "Meetei Mayek")}


def test_lang_tag():
    from kts import kural as K
    assert [K.lang_tag(s) for s in ("ksn", "ks", "mei", "mni", "gom", "kok", "sat")] == \
        ["ks-Arab", "ks-Deva", "mni-Mtei", "mni-Beng", "kok-Deva", "kok-Knda", "sat-Deva"]
    for stream in ("hi", "ta", "en", "ur", "bn", "as", "te", "bho", "sa"):
        assert K.lang_tag(stream) == stream
    # no code of the corpus that is not a language tag reaches a page
    tags = {K.lang_tag(code) for code in K.corpus()["meta"]["languages"]}
    assert not tags & {"ksn", "mei", "gom", "tac", "ena", "enm"}
    assert all(re.fullmatch(r"[a-z]{2,3}(-[A-Z][a-z]{3})?", tag) for tag in tags), tags


def test_lang_tag_names_the_script_of_the_text():
    """The table is checked against the data: meta.json and the letters of couplet 1."""
    from kts import kural as K
    k = K.kural(1)
    for stream, tag in K.LANG_TAGS.items():
        info = K.lang_info(stream)
        assert info, stream
        language, _, script = tag.partition("-")
        assert language == {"gom": "kok", "ksn": "ks", "mei": "mni"}.get(info["group"], info["group"]) or language == info["group"]
        if not script:
            continue
        letters, name = SCRIPTS[script]
        assert info["script"] == name, stream
        text = "".join(K.lines(k, stream))
        seen = {unicodedata.name(c).split()[0] for c in text if c.isalpha()}
        assert seen == {letters}, (stream, seen)
    # a stream without an entry is written in the usual script of its language
    usual = {"as": "Bengali", "bn": "Bengali", "brx": "Devanagari", "doi": "Devanagari", "gu": "Gujarati", "hi": "Devanagari",
             "kn": "Kannada", "mai": "Devanagari", "ml": "Malayalam", "mr": "Devanagari", "ne": "Devanagari", "or": "Odia",
             "pa": "Gurmukhi", "sa": "Devanagari", "ta": "Tamil", "te": "Telugu", "ur": "Arabic", "en": "Latin",
             "bho": "Devanagari"}
    for stream, info in K.corpus()["meta"]["languages"].items():
        if stream not in K.LANG_TAGS:
            assert usual[stream] == info["script"], stream


def test_filter_is_registered(app):
    from kts import kural as K
    assert app.jinja_env.filters["langtag"] is K.lang_tag


PAGES = ["/", "/thirukkural", "/thirukkural/1", "/daily-kural", "/register"]


@pytest.mark.parametrize("code", _codes())
def test_pages_in_every_language(app, code):
    from kts import kural as K
    from kts.i18n import LANG_INFO
    assert len(LANG_INFO) == 23
    allowed = set(LANG_INFO) | {K.lang_tag(s) for s in K.corpus()["meta"]["languages"]}
    client = app.test_client()
    for path in PAGES:
        page = _page(client, f"{path}?lang={code}")
        assert f'<html lang="{code}" dir="{LANG_INFO[code]["dir"]}"' in page, path
        assert 'lang="ksn"' not in page and 'lang="mei"' not in page and 'lang="gom"' not in page, path
        assert set(re.findall(r'\slang="([^"]*)"', page)) <= allowed, path
    # the stream of this interface language, with its tag and its direction
    stream = LANG_INFO[code]["corpus"]
    if stream != "ta":
        attrs = f'dir="{K.lang_info(stream).get("dir", "ltr")}" lang="{K.lang_tag(stream)}"'
        assert _page(client, f"/thirukkural?lang={code}").count(f'<div class="trans" {attrs}>') == 10
        assert f'<div class="trans" {attrs}>' in _page(client, f"/?lang={code}")
        assert _page(client, f"/daily-kural?d=2026-10-02&lang={code}").count(attrs) == 1


def _streams():
    from kts import kural as K
    return [code for code, info in K.corpus()["meta"]["languages"].items() if code != "ta"]


@pytest.mark.parametrize("stream", _streams())
def test_every_stream_carries_its_tag(app, stream):
    from kts import kural as K
    attrs = f'dir="{K.lang_info(stream).get("dir", "ltr")}" lang="{K.lang_tag(stream)}"'
    client = app.test_client()
    page = _page(client, f"/thirukkural?ch=2&l={stream}")
    assert re.findall(r'<div class="trans" ([^>]*)>', page) == [attrs] * 10
    assert _page(client, f"/daily-kural?d=2026-10-02&l={stream}").count(f'<div style="margin-top:10px;font-size:1.15rem" {attrs}>') == 1
    # the menus and the links go on with the code of the stream
    assert f'<option value="{stream}" selected>' in page or stream in ("tac", "ena", "enm")
    assert f"/thirukkural?ch=3&amp;l={stream}" in page


def test_templates_print_streams_through_the_filter():
    """<html lang>, the menu and the footer list carry the interface language; a stream carries its tag."""
    printed = {}
    for path in TEMPLATES:
        for value in re.findall(r'\slang="\{\{\s*(.*?)\s*\}\}"', path.read_text(encoding="utf-8")):
            printed.setdefault(value, set()).add(path.relative_to(ROOT / "templates").as_posix())
    plain = {value: where for value, where in printed.items() if not value.endswith("|langtag")}
    assert plain == {"lang": {"base.html", "candidate/exam_paper.html", "public/certificate.html", "public/letter.html",
                              "quiz/layout.html"},
                     "L.code": {"base.html", "public/orientation.html", "quiz/layout.html"}}
    assert set(printed) - set(plain) == {"stream|langtag", "info.code|langtag", "shown|langtag", "kotd_lang|langtag",
                                         "qlang|langtag"}


def test_style_sheet_selects_the_tags():
    assert '[lang="ur"], [lang="ks-Arab"] { font-family: "Noto Nastaliq Urdu"' in STYLES
    assert '[lang="mni-Mtei"] { font-family: "Noto Sans Meetei Mayek"' in STYLES
    assert '"ksn"' not in STYLES and '"mei"' not in STYLES
    # a selector that takes a prefix would set the Devanagari stream ks-Deva in Nastaliq
    assert ":lang(" not in STYLES and '[lang|=' not in STYLES and '[lang^=' not in STYLES
    # the rules of the Kashmiri and Urdu interface are those of <html lang>, as before
    assert 'html[lang="ur"] body, html[lang="ks"] body { line-height: 2.1; }' in STYLES
    for tag in re.findall(r'\[lang="([^"]+)"\]', STYLES):
        assert tag in ("en", "ur", "ks", "sat", "mni", "bn", "as", "ta", "ks-Arab", "mni-Mtei"), tag


# ---- B6 · single couplet: the script variants ---------------------------------------------

def _single(client, n, query=""):
    page = _page(client, f"/thirukkural/{n}{query}")
    return re.findall(r'<div class="stream">\s*<div class="lang"><bdi>(.*?)</bdi><small dir="ltr">(.*?)</small></div>\s*'
                      r'<div dir="(ltr|rtl)" lang="([^"]+)">(.*?)</div>', page, re.S)


def test_single_couplet_shows_the_variants(app):
    from kts import kural as K
    client = app.test_client()
    streams = _single(client, 1)
    tags = [tag for _native, _name, _dir, tag, _text in streams]
    assert len(tags) == 27 and len(set(tags)) == 27
    for base, variant in (("ks-Deva", "ks-Arab"), ("kok-Knda", "kok-Deva"), ("mni-Beng", "mni-Mtei")):
        assert tags.index(variant) == tags.index(base) + 1
    assert tags[0] == "ta" and tags[-2:] == ["en", "bho"]
    by_tag = {tag: (native, name, direction, text) for native, name, direction, tag, text in streams}
    for stream in ("ksn", "gom", "mei"):
        info = K.lang_info(stream)
        native, name, direction, text = by_tag[K.lang_tag(stream)]
        assert native == info["native"] and name == f'{info["name"]} · {info["script"]}'
        assert direction == info.get("dir", "ltr")
        assert text == "<br>".join(str(escape(line)) for line in K.lines(K.kural(1), stream))
    assert by_tag["ks-Arab"][2] == "rtl" and by_tag["ur"][2] == "rtl" and by_tag["ks-Deva"][2] == "ltr"


@pytest.mark.parametrize("query", ["", "?lang=ks", "?lang=kok"])
def test_single_couplet_without_text_in_a_variant(app, query):
    tags = [tag for _native, _name, _dir, tag, _text in _single(app.test_client(), 1330, query)]
    assert "ks-Arab" not in tags and "ks-Deva" in tags and "kok-Deva" in tags and "mni-Mtei" in tags
    assert len(tags) == 26


def test_pickers_are_as_before(app):
    from kts import kural as K
    assert [info["code"] for info in K.languages()] == ["ta"] + [c for c in K.SCHEDULED if c != "ta"] + K.EXTRA
    assert len(K.languages(variants=True)) == len(K.languages()) + 3
    page = _page(app.test_client(), "/resources")
    assert 'value="ksn"' not in page


# ---- B7 · alternate links ------------------------------------------------------------------

def _alternates(page):
    return re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)">', page)


def test_alternates_keep_the_parameters(app):
    page = _page(app.test_client(), "/thirukkural?ch=5&lang=bn")
    links = _alternates(page)
    assert [code for code, _ in links] == _codes() + ["x-default"]
    for code, address in links[:-1]:
        assert address == f"{HOME}/thirukkural?ch=5&amp;lang={code}"
    assert links[-1] == ("x-default", f"{HOME}/thirukkural?ch=5")
    # every parameter, in its order, whatever it holds
    page = _page(app.test_client(), "/resources?lang=hi&q=a%26b+%22c%22&cat=video&lang=ta&l=")
    links = dict(_alternates(page))
    assert links["ur"] == f"{HOME}/resources?q=a%26b+%22c%22&amp;cat=video&amp;l=&amp;lang=ur"
    assert links["x-default"] == f"{HOME}/resources?q=a%26b+%22c%22&amp;cat=video&amp;l="
    # a parameter given twice stays twice
    links = dict(_alternates(_page(app.test_client(), "/merit-list?state=Kerala&outcome=all&state=Goa")))
    assert links["hi"] == f"{HOME}/merit-list?state=Kerala&amp;outcome=all&amp;state=Goa&amp;lang=hi"


@pytest.mark.parametrize("path", ["/", "/about", "/thirukkural/7", "/daily-kural", "/register", "/status", "/contact"])
def test_alternates_of_a_page(app, path):
    links = _alternates(_page(app.test_client(), path))
    assert len(links) == 24
    assert links[0] == ("en", f"{HOME}{path}?lang=en") and links[-1] == ("x-default", f"{HOME}{path}")
    # each of the addresses shows the page in its language
    client = app.test_client()
    for code, address in links[:3] + links[-3:-1]:
        assert f'<html lang="{code}"' in _page(client, address.replace("&amp;", "&")[len(HOME):])


@pytest.mark.parametrize("path", ["/", "/about", "/thirukkural?ch=5&lang=bn"])
def test_head_and_get_agree(app, path):
    client = app.test_client()
    got = client.get(path)
    head = client.head(path)
    assert head.status_code == 200 and head.data == b""
    assert head.headers["Content-Length"] == str(len(got.data))


@pytest.mark.parametrize("path, status", [("/no-such-page", 404), ("/no-such-page?lang=hi", 404), ("/static/nope.css", 404),
                                          ("/thirukkural/1331", 404), ("/resources/999999", 404), ("/notices/999999?lang=ta", 404),
                                          ("/merit-list.csv", 404), ("/console/logout", 405), ("/candidate/nothing", 404)])
def test_error_page_has_no_alternates(path, status):
    own = make_app(RATE_CONTACT_PER_HOUR=10)  # an application of its own: the merit list is not published here
    r = own.test_client().get(path)
    page = r.data.decode("utf-8")
    assert r.status_code == status and '<span class="eyebrow">' in page
    assert "hreflang" not in page.split("</head>")[0] and 'rel="alternate"' not in page


@pytest.mark.parametrize("path", ["/candidate/login", "/console/login"])
def test_no_alternates_behind_a_sign_in(app, path):
    assert 'rel="alternate"' not in _page(app.test_client(), path)


def test_no_alternates_after_a_post(app):
    r = _register(app, 77, captcha="8")
    assert r.status_code == 400 and 'rel="alternate"' not in r.data.decode("utf-8")


def test_alternates_under_a_path_prefix():
    own = make_app(URL_PREFIX="/kts5")
    links = dict(_alternates(_page(own.test_client(), "/kts5/thirukkural?ch=5")))
    assert links["ta"] == f"{HOME}/kts5/thirukkural?ch=5&amp;lang=ta" and links["x-default"] == f"{HOME}/kts5/thirukkural?ch=5"


# ---- B8 · Content-Security-Policy, no script inside the pages ----------------------------------

POLICY = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
          "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")


@pytest.mark.parametrize("path, status", [("/", 200), ("/register", 200), ("/thirukkural?lang=ks", 200), ("/no-such-page", 404),
                                          ("/console/logout", 405), ("/console/login", 200), ("/candidate/login", 200),
                                          ("/static/nope.css", 404), ("/files/resources/nope.pdf", 404), ("/lang/ta", 302),
                                          ("/candidate/", 302)])
def test_content_security_policy(app, path, status):
    r = app.test_client().get(path)
    assert r.status_code == status and r.mimetype == "text/html"
    assert r.headers.getlist("Content-Security-Policy") == [POLICY]


@pytest.mark.parametrize("path", ["/static/js/portal.js", "/static/css/portal.css", "/static/img/favicon.png", "/favicon.ico",
                                  "/healthz", "/robots.txt", "/daily-kural/calendar.csv"])
def test_policy_is_for_pages_only(app, path):
    r = app.test_client().get(path)
    assert r.status_code == 200 and r.mimetype != "text/html"
    assert "Content-Security-Policy" not in r.headers
    # the other headers stay
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "SAMEORIGIN"


def test_a_pdf_carries_no_policy():
    """The browser shows a PDF in a viewer of its own, which the policy of the pages would stop."""
    own = make_app(RATE_CONTACT_PER_HOUR=10)
    from kts.db import execute, utcnow
    folder = Path(own.config["UPLOAD_DIR"])
    pdf = b"%PDF-1.4\n%%EOF\n"
    for name in ("resources/guide.pdf", "notices/circular.pdf"):
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(pdf)
    with own.app_context():
        rid = execute("INSERT INTO resources(title, category, file_path, file_name, created_at, updated_at) VALUES(?,?,?,?,?,?)",
                      ("Study guide", "study", "resources/guide.pdf", "Study guide.pdf", utcnow(), utcnow()))
    client = own.test_client()
    for path in (f"/resources/{rid}", "/files/resources/guide.pdf", "/files/notices/circular.pdf"):
        r = client.get(path)
        assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data == pdf, path
        assert "Content-Security-Policy" not in r.headers, path
        assert "attachment" not in r.headers.get("Content-Disposition", ""), path
        assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "SAMEORIGIN", path
    # the pages of the same application carry it
    assert client.get("/resources").headers.getlist("Content-Security-Policy") == [POLICY]


def test_an_svg_picture_carries_the_policy():
    """Opened by itself an SVG picture is a document of the portal, and an uploaded one may hold a script."""
    own = make_app(ADMIN_EMAIL=FIRST)
    from kts.db import execute, utcnow
    _put(own, "resources/picture.svg", "notices/picture.svg", "tasks/picture.svg", "documents/picture.svg", content=SVG)
    _put(own, "tasks/report.pdf", "documents/plan.pdf", content=PDF)
    with own.app_context():
        rid = execute("INSERT INTO resources(title, category, file_path, file_name, created_at, updated_at) VALUES(?,?,?,?,?,?)",
                      ("A picture", "poster", "resources/picture.svg", "A picture.svg", utcnow(), utcnow()))
    visitor, staff = own.test_client(), _staff(own)
    # the four routes that hand out what was uploaded
    asked = [(visitor, f"/resources/{rid}"), (visitor, "/files/resources/picture.svg"), (visitor, "/files/notices/picture.svg"),
             (staff, "/console/files/resources/picture.svg"), (staff, "/console/files/notices/picture.svg"),
             (staff, "/console/files/tasks/picture.svg"), (staff, "/console/files/documents/picture.svg"),
             (staff, "/hub/files/tasks/picture.svg"), (staff, "/hub/files/documents/picture.svg")]
    for client, path in asked:
        r = client.get(path)
        assert r.status_code == 200 and r.mimetype == "image/svg+xml" and r.data == SVG, path
        assert r.headers.getlist("Content-Security-Policy") == [POLICY], path
        # shown, not handed out as a download
        assert "attachment" not in r.headers.get("Content-Disposition", ""), path
        assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "SAMEORIGIN", path
    # a picture of the portal itself
    r = visitor.get("/static/img/kts5-lockup.svg")
    assert r.status_code == 200 and r.mimetype == "image/svg+xml"
    assert r.headers.getlist("Content-Security-Policy") == [POLICY]
    # a PDF carries none behind the sign-in either
    for path in ("/console/files/tasks/report.pdf", "/hub/files/tasks/report.pdf", "/hub/files/documents/plan.pdf"):
        r = staff.get(path)
        assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data == PDF, path
        assert "Content-Security-Policy" not in r.headers, path


# ---- B8a · the folder of a file that was uploaded --------------------------------------------

def _answer(client, path):
    """The status of the answer to an address that reaches the portal as it is written here."""
    from urllib.parse import unquote
    r = client.get(path)
    assert r.request.path == unquote(path), path
    r.close()
    return r.status_code


@pytest.mark.parametrize("way", ["notices/../", "resources/../", "notices/%2e%2e/", "notices/.%2e/", "resources/..%2f",
                                 "notices/./../", "notices/x/../../", "notices/../notices/../", "./"])
def test_the_folder_is_tested_on_the_path_as_it_will_be_opened(way):
    own = make_app(ADMIN_EMAIL=FIRST)
    _put(own, "photos/student.png", "idproofs/student.png", content=PNG)
    _put(own, "notices/circular.pdf", "resources/guide.pdf", "tasks/report.pdf", "documents/plan.pdf", content=PDF)
    visitor, chief = own.test_client(), _staff(own)
    content = _staff(own, "content@tests.example", role="content")
    agency = _staff(own, "agency@tests.example", role="agency")
    for folder in ("photos", "idproofs"):
        name = f"{folder}/student.png"
        # a visitor, and the agencies in their hub: these folders are no address
        assert _answer(visitor, f"/files/{name}") == 404 and _answer(visitor, f"/files/{way}{name}") == 404, name
        for hub in ("tasks/../", "documents/%2e%2e/", way):
            assert _answer(agency, f"/hub/files/{name}") == 404 and _answer(agency, f"/hub/files/{hub}{name}") == 404, (hub, name)
        # a member of staff without the right to see applications
        assert _answer(content, f"/console/files/{name}") == 403 and _answer(content, f"/console/files/{way}{name}") == 403, name
        assert _answer(agency, f"/console/files/{way}{name}") == 403, name
    # with the right to see them the file is handed out
    assert _answer(chief, "/console/files/photos/student.png") == 200
    assert _answer(chief, "/console/files/idproofs/student.png") == 200
    # the files that everybody may have
    for client, path in ((visitor, "/files/notices/circular.pdf"), (visitor, "/files/resources/guide.pdf"),
                         (visitor, "/files/resources/../notices/circular.pdf"), (visitor, "/files/notices/./circular.pdf"),
                         (content, "/console/files/tasks/report.pdf"), (content, "/console/files/resources/guide.pdf"),
                         (agency, "/hub/files/tasks/report.pdf"), (agency, "/hub/files/documents/plan.pdf"),
                         (agency, "/hub/files/tasks/../documents/plan.pdf")):
        assert _answer(client, path) == 200, path
    # no way leads out of the upload folder
    assert Path(own.config["DATABASE"]).name == "test.sqlite3" and Path(own.config["UPLOAD_DIR"]).name == "uploads"
    for client, path in ((visitor, "/files/notices/../../instance/test.sqlite3"), (visitor, "/files/../instance/test.sqlite3"),
                         (visitor, "/files/notices/../../uploads/photos/student.png"),
                         (content, "/console/files/../instance/test.sqlite3"),
                         (content, "/console/files/notices/../../uploads/photos/student.png"),
                         (chief, "/console/files/../instance/test.sqlite3"),
                         (agency, "/hub/files/tasks/../../instance/test.sqlite3")):
        assert _answer(client, path) == 404, path


@pytest.mark.parametrize("spelt", ["Photos", "PHOTOS", "photos.", "photos::$INDEX_ALLOCATION", "notices/../Photos",
                                   "IdProofs", "idproofs.", "idproofs::$INDEX_ALLOCATION", "uploads", ".."])
def test_a_folder_has_one_name_only(spelt):
    """Windows opens "Photos" and "photos." as the folder photos; the portal knows the folders by their names."""
    own = make_app(ADMIN_EMAIL=FIRST)
    _put(own, "photos/student.png", "idproofs/student.png", content=PNG)
    chief = _staff(own)
    content = _staff(own, "content@tests.example", role="content")
    agency = _staff(own, "agency@tests.example", role="agency")
    for client in (content, agency, chief):
        assert _answer(client, f"/console/files/{spelt}/student.png") == 404, spelt
    for folder in ("photos", "idproofs"):
        assert _answer(content, f"/console/files/{folder}/student.png") == 403
        assert _answer(agency, f"/console/files/{folder}/student.png") == 403
        r = chief.get(f"/console/files/{folder}/student.png")
        assert r.status_code == 200 and r.data == PNG
        r.close()


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.relative_to(ROOT / "templates").as_posix())
def test_template_has_no_script_of_its_own(path):
    source = path.read_text(encoding="utf-8")
    tags = re.findall(r"<[a-zA-Z][^<>]*>", re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "x", source, flags=re.S))
    for tag in tags:
        assert not re.search(r"""[\s"'/]on[a-z]+\s*=""", tag, re.I), tag
        assert not re.search(r"""=\s*["']?\s*(javascript|vbscript|data)\s*:""", tag, re.I), tag
        assert not re.match(r"<(iframe|frame|object|embed|base|style|video|audio|source)\b", tag, re.I), tag
        if re.match(r"<script\b", tag, re.I):
            assert 'type="application/json"' in tag or " src=" in tag, tag
    assert not re.search(r"javascript\s*:", source, re.I)
    # what a page loads comes from the portal itself
    for address in re.findall(r"""<(?:script|img|link)\b[^>]*?\b(?:src|href)=["']([^"']*)""", source):
        # a data address made by the portal: the QR code, the signature of the certificate
        assert address.startswith(("{{ url_for(", "{{ qr }}", "{{ address }}", "{{ signature }}")), address


def test_print_and_confirm_are_attributes():
    for name, count in (("public/register_done.html", 1), ("public/daily.html", 1), ("candidate/admit_card.html", 1)):
        source = (ROOT / "templates" / name).read_text(encoding="utf-8")
        assert len(re.findall(r'<button class="[^"]*" type="button" data-print>', source)) == count, name
    source = (ROOT / "templates" / "console" / "application.html").read_text(encoding="utf-8")
    assert 'name="action" value="withdraw" data-confirm="Withdraw this application?">' in source
    assert 'name="action" value="reset_exam" data-confirm="Delete this test attempt so the candidate can retake it?">' in source
    # the script acts on them; the question of the test (#exam-app) is no button and gets no click handler
    assert 'document.querySelectorAll("[data-print]")' in SCRIPT and "window.print()" in SCRIPT
    assert 'document.querySelectorAll("button[data-confirm], a[data-confirm]")' in SCRIPT
    assert 'document.querySelectorAll("form[data-confirm]")' in SCRIPT
    assert '"[data-confirm]"' not in SCRIPT
    paper = (ROOT / "templates" / "candidate" / "exam_paper.html").read_text(encoding="utf-8")
    assert re.search(r'<main [^>]*id="exam-app"[^>]* data-confirm=', paper)


def test_print_button_in_the_pages(app):
    page = _page(app.test_client(), "/daily-kural")
    assert f'<button class="btn sm ghost" type="button" data-print>{_text("common.print")}</button>' in page
    assert "onclick" not in page


def test_version_of_style_sheet_and_script():
    linked = {}
    for path in TEMPLATES:
        for name, version in re.findall(r"filename='((?:css|js)/portal\.(?:css|js))'\) \}\}\?v=(\d+)", path.read_text(encoding="utf-8")):
            linked.setdefault(path.relative_to(ROOT / "templates").as_posix(), []).append((name, version))
    expected = {name: [("css/portal.css", "10"), ("js/portal.js", "10")]
                for name in ("base.html", "candidate/exam_paper.html", "console/base.html")}
    # the certificate has a style sheet of its own and the script for its print button
    expected["public/certificate.html"] = [("js/portal.js", "10")]
    expected["public/letter.html"] = [("js/portal.js", "10")]
    # the pages of the classroom quiz have a frame of their own, with the style sheet and the script of the portal
    expected["quiz/layout.html"] = [("css/portal.css", "10"), ("js/portal.js", "10")]
    assert linked == expected
    for path in TEMPLATES:
        assert not re.search(r"portal\.(css|js)'\) \}\}(?!\?v=10\")", path.read_text(encoding="utf-8")), path


# ---- B9 · alt texts of the logos ----------------------------------------------------------------

@pytest.mark.parametrize("code", ["en", "hi", "ta", "ur", "sat"])
def test_alt_texts_in_the_language_of_the_page(app, code):
    page = _page(app.test_client(), f"/about?lang={code}")
    for logo, key, times in (("moe", "site.ministry", 2), ("cict", "site.organiser", 1), ("iitm", "agency.iitm.name", 1),
                             ("bhu", "agency.bhu.name", 1), ("bbs", "agency.bbs.name", 1)):
        found = re.findall(rf'<img [^>]*src="/static/img/logos/{logo}\.png" alt="([^"]*)"', page)
        assert found == [_text(key, code)] * times, (code, logo)
    assert re.findall(r'<img [^>]*src="/static/img/cict-logo\.png" alt="([^"]*)"', page) == [_text("site.organiser", code)]
    # no key for this one: the English stays
    assert re.findall(r'<img [^>]*src="/static/img/logos/goi\.png" alt="([^"]*)"', page) == ["Government of India"] * 2
    if code != "en":
        for english in ("Ministry of Education", "Central Institute of Classical Tamil", "Indian Institute of Technology Madras",
                        "Banaras Hindu University", "Bharatiya Bhasha Samiti"):
            assert f'alt="{english}' not in page, english


def test_alt_texts_use_keys_that_exist():
    from kts.i18n import CATALOG
    source = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    keys = re.findall(r"""alt="\{\{ t\('([^']+)'\) \}\}\"""", source)
    assert len(keys) == 8
    for key in keys:
        for code in _codes():
            assert CATALOG[code].get(key), (code, key)
    # 540 texts, the two that ask for English entries in the registration form, the heading of the
    # social-media links, the nodal officers, the 19 of the timeline (version 1.1.5) and the 59 of
    # the bank details of the selected students (version 1.2.0), the 25 of the page that explains
    # them (1.2.1), the 3 of the certificate of recognition (1.2.2), the 2 of that of merit (1.2.3),
    # the 2 of the confirmation letter (1.2.5), the 62 of the classroom quiz (1.2.8) and the 10 of the
    # certificate of participation in the inauguration (1.2.10), the 41 of the research papers (1.2.11) and
    # the 3 tabs of the videos in the repository (1.2.12) and the tab of music (1.2.13)
    assert len(CATALOG["en"]) == 771


def test_chapter_names_keep_the_english(app):
    page = _page(app.test_client(), "/thirukkural?lang=bn")
    assert "கடவுள் வாழ்த்து</span>" in page and "· The Praise of God</span></h2>" in page


# ---- B10 · small routes ---------------------------------------------------------------------

def test_favicon(app):
    r = app.test_client().get("/favicon.ico")
    assert r.status_code == 200 and r.mimetype == "image/png"
    assert r.data == (ROOT / "static" / "img" / "favicon.png").read_bytes() and r.data[:8] == PNG[:8]
    assert "max-age=86400" in r.headers["Cache-Control"] and "no-store" not in r.headers["Cache-Control"]
    assert r.headers.get("ETag") and r.headers.get("Last-Modified")
    again = app.test_client().get("/favicon.ico", headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304 and again.data == b""
    assert app.test_client().head("/favicon.ico").headers["Content-Length"] == str(len(r.data))


def test_robots(app):
    r = app.test_client().get("/robots.txt")
    assert r.status_code == 200 and r.mimetype == "text/plain"
    lines = r.data.decode("utf-8").splitlines()
    assert lines == ["User-agent: *", "Disallow: /console/", "Disallow: /candidate/", "Disallow: /hub/", "Disallow: /lang"]


def test_healthz_tells_the_version(app):
    from kts.version import VERSION
    answer = app.test_client().get("/healthz").get_json()
    assert answer["ok"] is True and answer["version"] == VERSION == "1.2.15" and answer["time"]
    assert sorted(answer) == ["ok", "time", "version"]


# ---- B11 · numbers in an address ---------------------------------------------------------------

LARGEST = 9223372036854775807  # the largest number that the database holds


@pytest.mark.parametrize("number", [str(LARGEST), str(LARGEST + 1), "99999999999999999999", "0009223372036854775808",
                                    "9" * 18, "9" * 19, "7" * 5000], ids=lambda number: number[:24])
def test_a_number_without_a_row_is_not_found(app, number):
    client = app.test_client()
    for path in ("/notices/", "/resources/", "/thirukkural/"):
        r = client.get(path + number)
        assert r.status_code == 404 and '<span class="eyebrow">404</span>' in r.data.decode("utf-8"), path
    # behind the sign-in: a number of 18 digits may be a row, a longer one is no address of the portal
    for path in ("/console/applications/{}", "/console/exam/sessions/{}", "/console/notices/{}/edit", "/hub/tasks/{}",
                 "/hub/documents/{}/download"):
        r = client.get(path.format(number))
        if len(number) <= 18:
            assert r.status_code == 302 and r.headers["Location"] == "/console/login", path
        else:
            assert r.status_code == 404, path


def test_a_number_without_a_row_after_the_sign_in():
    import os
    own = make_app(ADMIN_EMAIL="first@tests.example")
    client = own.test_client()
    client.get("/console/login")
    with client.session_transaction() as s:
        token = s["_csrf"]
    r = client.post("/console/login", data={"_csrf": token, "email": "first@tests.example",
                                            "password": os.environ["KTS_ADMIN_PASSWORD"]})
    assert r.status_code == 302
    with own.app_context():
        from kts.db import execute
        execute("UPDATE users SET must_change_password = 0")
    assert client.get("/console/applications").status_code == 200
    for number in ("9" * 18, str(LARGEST + 1), "99999999999999999999", "7" * 5000):
        for path in ("/console/applications/{}", "/console/exam/sessions/{}", "/console/notices/{}/edit",
                     "/console/users/{}/edit", "/hub/tasks/{}", "/hub/documents/{}/download"):
            assert client.get(path.format(number)).status_code == 404, (path, number[:24])


def test_numbers_with_a_row_are_found():
    own = make_app(RATE_CONTACT_PER_HOUR=10)
    from flask import url_for
    from kts.db import execute, utcnow
    with own.app_context():
        nid = execute("INSERT INTO notices(title, body, created_at, updated_at) VALUES(?,?,?,?)",
                      ("A notice", "Its text", utcnow(), utcnow()))
        rid = execute("INSERT INTO resources(title, url, created_at, updated_at) VALUES(?,?,?,?)",
                      ("A link", "https://example.org/", utcnow(), utcnow()))
    client = own.test_client()
    assert "A notice" in _page(client, f"/notices/{nid}")
    # zeros in front, as before
    assert "A notice" in _page(client, f"/notices/000{nid}")
    r = client.get(f"/resources/{rid}")
    assert r.status_code == 302 and r.headers["Location"] == "https://example.org/"
    assert client.get("/thirukkural/1330").status_code == 200 and client.get("/thirukkural/1331").status_code == 404
    # what is no number was no address before and is none now
    for path in (f"/notices/-{nid}", f"/notices/{nid}.5", f"/notices/{nid}x", f"/notices/+{nid}"):
        assert client.get(path).status_code == 404, path
    with own.test_request_context("/"):
        assert url_for("public.notice", nid=nid) == f"/notices/{nid}"
        assert url_for("public.resource_open", rid=rid) == f"/resources/{rid}"
        assert url_for("public.kural_single", n=1330) == "/thirukkural/1330"
        assert url_for("public.notice", nid=10 ** 17) == "/notices/100000000000000000"


def test_every_number_in_an_address_has_the_limit(app):
    rules = [rule for rule in app.url_map.iter_rules() if "<int:" in rule.rule]
    assert len(rules) >= 15
    for rule in rules:
        for converter in rule._converters.values():
            if type(converter).__name__ in ("IntegerConverter", "_RowNumber"):
                assert converter.regex == r"\d{1,18}", rule.rule


# ---- the data of the developer stays untouched ------------------------------------------------

def test_everything_happened_in_the_temporary_folder(app):
    for name in ("DATABASE", "INSTANCE_DIR", "UPLOAD_DIR"):
        assert TMP.resolve() in Path(app.config[name]).resolve().parents, name

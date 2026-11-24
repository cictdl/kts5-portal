"""
Fewer sign-in codes for the institutions (1.2.212). CICT, 24 November 2026: "can we remove Participating institutions Institution
sign-in without code because of gmail limit?"; offered the choice, with what a sign-in without a code would open to anybody who
knows the address: "Fewer code mails". So the code stays, and

* a code is valid for 60 minutes (15 before): a mail that comes late still signs in;
* a coordinator (or Head) who signs in with the code stays signed in on that device for 30 days (a cookie of its own, signed with
  the key of the portal, HttpOnly, SameSite=Lax): no new code each day. Signing out ends it on that device; an address that is no
  longer the institution's, or a declined institution, does not open with it. The Console keeps its 8 hours.

    python -m pytest tests/test_inst_device_1124.py -q
"""
import re
import time

from conftest import make_app
from test_campus import _coordinator, _mails, _portal

COOKIE = "kts_inst"


def _inst(app):
    from test_progress import _inst as make
    from kts.db import query
    iid = make(app, "Device College", state="Kerala")
    with app.app_context():
        return query("SELECT * FROM institutions WHERE id = ?", (iid,), one=True)


def _cookie(client):
    return client.get_cookie(COOKIE)


def test_the_code_is_valid_for_an_hour():
    from kts import campus
    assert campus.CODE_MINUTES == 60 and campus.DEVICE_DAYS == 30
    app = _portal()
    inst = _inst(app)
    client = app.test_client()
    client.get("/institution/login")
    with client.session_transaction() as s:
        token = s["_csrf"]
    page = client.post("/institution/login", data={"_csrf": token, "email": inst["coord_email"]}).get_data(as_text=True)
    assert "It is valid for 60 minutes." in page and "15 minutes" not in page
    assert "It is valid for 60 minutes." in _mails(app, inst["coord_email"])[-1]["body"]
    # 61 minutes later the code has expired; 59 minutes later it still signs in
    from datetime import datetime, timedelta
    code = re.search(r"\n    (\d{6})\n", _mails(app, inst["coord_email"])[-1]["body"]).group(1)
    with client.session_transaction() as s:
        until = datetime.fromisoformat(s["inst_login"]["until"])
    now = campus.now_ist()
    assert now + timedelta(minutes=59) < until <= now + timedelta(minutes=61)
    real = campus.now_ist
    try:
        campus.now_ist = lambda: real() + timedelta(minutes=61)
        late = client.post("/institution/code", data={"_csrf": token, "code": code})
        assert late.status_code == 400 and "The code has expired" in late.get_data(as_text=True)
    finally:
        campus.now_ist = real
    client.post("/institution/login", data={"_csrf": token, "email": inst["coord_email"]})
    code = re.search(r"\n    (\d{6})\n", _mails(app, inst["coord_email"])[-1]["body"]).group(1)
    try:
        campus.now_ist = lambda: real() + timedelta(minutes=59)
        r = client.post("/institution/code", data={"_csrf": token, "code": code})
    finally:
        campus.now_ist = real
    assert r.status_code == 302 and r.headers["Location"].endswith("/institution")


def test_signed_in_on_the_device_for_30_days():
    app = _portal()
    inst = _inst(app)
    client, _token = _coordinator(app, inst)
    # the cookie of the device: signed, HttpOnly, SameSite=Lax, for 30 days
    c = _cookie(client)
    assert c is not None and c.value and inst["coord_email"] not in c.value
    # a browser that has only that cookie (the session of the portal is over) is signed in
    other = app.test_client()
    other.set_cookie(COOKIE, c.value)
    page = other.get("/institution")
    assert page.status_code == 200 and "Device College" in page.get_data(as_text=True)
    # ... and the Console keeps its 8 hours
    assert app.permanent_session_lifetime.total_seconds() == 8 * 3600


def test_the_cookie_of_the_device_is_set_with_its_attributes():
    app = _portal()
    inst = _inst(app)
    client = app.test_client()
    client.get("/institution/login")
    with client.session_transaction() as s:
        token = s["_csrf"]
    client.post("/institution/login", data={"_csrf": token, "email": inst["coord_email"]})
    code = re.search(r"\n    (\d{6})\n", _mails(app, inst["coord_email"])[-1]["body"]).group(1)
    r = client.post("/institution/code", data={"_csrf": token, "code": code})
    header = next(h for h in r.headers.getlist("Set-Cookie") if h.startswith(COOKIE + "="))
    assert "HttpOnly" in header and "SameSite=Lax" in header and "Path=/" in header
    assert re.search(r"Max-Age=2592000\b", header)


def test_what_does_not_open():
    from kts import campus
    from kts.db import execute
    app = _portal()
    inst = _inst(app)
    client, token = _coordinator(app, inst)
    value = _cookie(client).value

    def opens(v):
        other = app.test_client()
        other.set_cookie(COOKIE, v)
        r = other.get("/institution")
        return r.status_code == 200 and "Device College" in r.get_data(as_text=True)

    assert opens(value)
    # a cookie changed by hand
    assert not opens(value[:-2] + ("AA" if not value.endswith("AA") else "BB"))
    assert not opens("not-a-cookie")
    # one of more than 30 days
    with app.test_request_context():
        old = campus._device_signer().dumps({"e": inst["coord_email"], "i": inst["id"]})
    real = time.time
    try:
        time.time = lambda: real() + 31 * 24 * 3600
        assert not opens(old)
    finally:
        time.time = real
    # an address that is no longer the institution's
    with app.app_context():
        execute("UPDATE institutions SET coord_email = 'new.coordinator@device.example' WHERE id = ?", (inst["id"],))
    assert not opens(value)
    with app.app_context():
        execute("UPDATE institutions SET coord_email = ? WHERE id = ?", (inst["coord_email"], inst["id"]))
    assert opens(value)
    # a declined institution
    with app.app_context():
        execute("UPDATE institutions SET status = 'declined' WHERE id = ?", (inst["id"],))
    assert not opens(value)


def test_signing_out_ends_it_on_the_device():
    app = _portal()
    inst = _inst(app)
    client, token = _coordinator(app, inst)
    r = client.post("/institution/logout", data={"_csrf": token})
    assert r.status_code == 302
    header = next(h for h in r.headers.getlist("Set-Cookie") if h.startswith(COOKIE + "="))
    assert re.search(r"Max-Age=0\b|expires=Thu, 01 Jan 1970", header, flags=re.I)
    assert _cookie(client) is None or not _cookie(client).value
    r = client.get("/institution")
    assert r.status_code == 302 and "/institution/login" in r.headers["Location"]

"""
The sign-in of an institution without a mailed code (1.2.216). CICT, 26 November 2026: "i want sign-in codes stopped"; and, asked
how an institution signs in then: "only sign in code for the nodal officers should go".

* The sign-in codes of the participating institutions are not mailed any more (the setting inst.code_mail, off; Console >
  Settings > Mail brings them back). The Institutional Coordinator or the Head of the Institution signs in with the e-mail address
  of the registration and the mobile number of the coordinator given there: no mail is sent. Only the tries that fail count (20 in
  an hour from one address of the network); a wrong number and an address that the portal does not know are answered alike.
* A code that still waits in the queue is not sent.
* The mail of the account of a Nodal Officer, with its temporary password, goes at once, past a pause of the Console.
* The texts that tell an institution how it signs in follow the setting: the page of the sign-in, four texts of the catalogue in
  the 23 languages (<key>_nc), the help page, the mails that invite an institution to nominate and remind it.

The tests made before 1.2.216 sign in with the mailed code (tests/conftest.py switches it on).

    python -m pytest tests/test_signin_no_code_1126.py -q
"""
import json
import re
from pathlib import Path

import pytest
from markupsafe import escape

from conftest import make_app
from test_campus import _mails, _portal
from test_mailq import T0, Server, _app as _mail_app, _rows, server  # noqa: F401  (the fixture of the mail server of the tests)
from test_progress import _inst as _make

EMAIL, HEAD, MOBILE = "coord@plain.college.example", "head@plain.college.example", "9000000001"
KEYS = ["guide.i2", "nl.s1", "nl.art_c1", "hs.c1"]
ERROR = "The e-mail address and the mobile number do not match the registration of an institution."
ROOT = Path(__file__).resolve().parent.parent


class Inline:
    """A thread of the tests: it runs at once, so that the test sees what the thread did."""

    def __init__(self, target, args=(), name=None, daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture(autouse=True)
def fresh_limiter():
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def _no_codes(app):
    """The portal as it is from 1.2.216: no sign-in code is mailed to an institution."""
    from kts.db import set_setting
    with app.app_context():
        set_setting("inst.code_mail", "0")
    return app


def _app():
    app = _no_codes(_portal())
    return app, _make(app, "Plain College")      # coord@plain.college.example, head@plain.college.example, 9000000001


def _client(app):
    client = app.test_client()
    client.get("/institution/login")
    with client.session_transaction() as s:
        return client, s["_csrf"]


def _sign_in(app, email=EMAIL, mobile=MOBILE):
    client, token = _client(app)
    return client, client.post("/institution/login", data={"_csrf": token, "email": email, "mobile": mobile})


def _audit(app, action):
    from kts.db import query
    with app.app_context():
        return [dict(r) for r in query("SELECT * FROM audit_log WHERE action = ? ORDER BY id", (action,))]


def _signed_in(client):
    r = client.get("/institution")
    return r.status_code == 200


# ---- the setting -------------------------------------------------------------------------------------------------------------------

def test_the_codes_are_off_by_default_and_the_console_has_the_switch():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS, execute, get_setting
    assert DEFAULT_SETTINGS["inst.code_mail"] == "0"
    groups = {group: items for group, items in SETTING_GROUPS}
    rows = {k: (label, kind) for k, label, kind in groups["Mail"]}
    assert rows["inst.code_mail"] == ("Sign-in codes mailed to the participating institutions (off: an institution signs in with the "
                                      "e-mail address and the coordinator's mobile number of its registration, and no mail is sent)", "bool")
    assert rows["mail.paused"][0] == ("Sending paused (new mails wait in the queue; the mail of the account of a Nodal Officer and, "
                                      "while they are mailed, the sign-in codes of the institutions go at once all the same)")
    # a portal on which nobody has saved the setting: no code
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key = 'inst.code_mail'")
        assert get_setting("inst.code_mail") != "1"
    page = app.test_client().get("/institution/login").get_data(as_text=True)
    assert 'name="mobile"' in page and "Send me the code" not in page
    # the release itself sends nothing
    assert _mails(app) == []


# ---- the page and the sign-in ------------------------------------------------------------------------------------------------------

def test_the_page_asks_for_the_address_and_the_mobile_number():
    app, _iid = _app()
    page = app.test_client().get("/institution/login").get_data(as_text=True)
    assert ("signs in with the e-mail address and\n    the mobile number of the Institutional Coordinator given when the institution "
            "registered. No code is mailed and no password is needed.") in page.replace("\r\n", "\n")
    assert 'type="email" id="email" name="email"' in page and 'type="tel" id="mobile" name="mobile"' in page
    assert "Mobile number of the Institutional Coordinator, as given at registration (10 digits)" in page
    assert ">Sign in</button>" in page and "You stay signed in on this device for 30 days." in page
    assert "The number is the one in the line “Institutional Coordinator” of the mail" in page and 'class="alert info"' not in page
    for gone in ("six-digit", "Send me the code", 'id="code"', "Ask for a new code"):
        assert gone not in page, gone


def test_the_coordinator_signs_in_and_no_mail_is_sent():
    app, iid = _app()
    client, r = _sign_in(app)
    assert r.status_code == 302 and r.headers["Location"].endswith("/institution")
    assert _signed_in(client) and "Plain College" in client.get("/institution").get_data(as_text=True)
    assert _mails(app) == []                                          # no mail at all
    log = _audit(app, "institution_login")
    assert [(row["entity_id"], row["detail"]) for row in log] == [(iid, f"{EMAIL} (e-mail address and mobile number)")]
    assert _audit(app, "institution_code_sent") == [] and _audit(app, "institution_login_refused") == []
    # signed in on the device for 30 days, as with the code (1.2.212)
    c = client.get_cookie("kts_inst")
    assert c is not None and c.http_only and c.max_age == 30 * 24 * 3600
    other = app.test_client()
    other.set_cookie("kts_inst", c.value)
    assert _signed_in(other)
    # the sign-in page leads a signed-in institution to its page
    assert client.get("/institution/login").status_code == 302


@pytest.mark.parametrize("email, mobile", [
    (EMAIL, "+91 90000 00001"), (EMAIL, "090000-00001"), (EMAIL, " 90000 00001 "), ("  Coord@Plain.College.Example ", MOBILE),
    (HEAD, MOBILE),      # the Head of the Institution, with the mobile number of the coordinator
    (EMAIL, "९००००००००१"), (EMAIL, "৯০০০০০০০০১"), (EMAIL, "+௯௧ ௯௦௦௦௦ ௦௦௦௦௧"),      # typed with the digits of Hindi, Bengali, Tamil
])
def test_the_number_as_people_write_it_and_the_head(email, mobile):
    app, _iid = _app()
    client, r = _sign_in(app, email, mobile)
    assert r.status_code == 302 and _signed_in(client)
    assert _mails(app) == []


@pytest.mark.parametrize("email, mobile", [
    (EMAIL, "9000000002"),                    # a wrong number
    (EMAIL, ""), (EMAIL, "90000"), (EMAIL, "0000000000"), (EMAIL, "900000000100"),
    (EMAIL, "९००००००००२"),                    # a wrong number in the digits of Hindi
    (EMAIL, "9222222222"),                    # the telephone of the Head is not asked for
    ("nobody@plain.college.example", MOBILE),  # an address that the portal does not know
    ("coord@declined.college.example", "9000000001"),
])
def test_a_wrong_pair_does_not_sign_in(email, mobile):
    from kts.db import execute
    app, iid = _app()
    _make(app, "Declined College", status="declined")
    with app.app_context():
        execute("UPDATE institutions SET head_phone = '9222222222' WHERE id = ?", (iid,))
    client, r = _sign_in(app, email, mobile)
    page = r.get_data(as_text=True)
    assert r.status_code == 400 and ERROR in page and 'name="mobile"' in page
    assert f'value="{email}"' in page                                  # the address stays in the form, the number does not
    assert mobile == "" or mobile not in page
    assert client.get("/institution").status_code == 302 and client.get_cookie("kts_inst") is None
    assert _mails(app) == [] and _audit(app, "institution_login") == []


def test_an_unknown_address_is_answered_as_a_wrong_number():
    app, iid = _app()
    _c, wrong = _sign_in(app, EMAIL, "9000000002")
    _c, unknown = _sign_in(app, "nobody@elsewhere.example", "9000000002")
    strip = lambda r: re.sub(r'value="[^"]*"', "", r.get_data(as_text=True))  # noqa: E731  (the token and the address typed)
    assert wrong.status_code == unknown.status_code == 400 and strip(wrong) == strip(unknown)
    # the audit log notes each refusal, also that of an address that the portal does not know: the same work for both
    assert [(row["entity_id"], row["detail"]) for row in _audit(app, "institution_login_refused")] == [
        (iid, EMAIL), (None, "nobody@elsewhere.example")]


def test_an_institution_without_a_number_is_not_opened_by_an_empty_one():
    from kts.db import execute
    app, iid = _app()
    with app.app_context():
        execute("UPDATE institutions SET coord_mobile = '' WHERE id = ?", (iid,))
    for mobile in ("", "0", "9000000001"):
        client, r = _sign_in(app, EMAIL, mobile)
        assert r.status_code == 400 and not _signed_in(client)


def test_what_is_typed_is_shown_safely():
    app, _iid = _app()
    _c, r = _sign_in(app, '"><svg/onload=alert(1)>@x.in', MOBILE)
    page = r.get_data(as_text=True)
    assert r.status_code == 400 and "<svg/onload" not in page and "&lt;svg/onload" in page
    _c, r = _sign_in(app, "not an address", MOBILE)
    assert r.status_code == 400 and ERROR not in r.get_data(as_text=True)


def test_two_institutions_of_one_address_each_with_its_number():
    from kts.db import query
    app, iid = _app()
    second = _make(app, "Second College", status="pending", coord_email=EMAIL, coord_mobile="9000000002")
    client, r = _sign_in(app, EMAIL, "9000000002")
    assert r.status_code == 302
    with client.session_transaction() as s:
        assert s["inst_id"] == second and s["inst_email"] == EMAIL
    # ... and that sign-in opens that institution only: the other one of the address has another number
    assert client.get(f"/institution/switch/{iid}").status_code == 404
    assert "Plain College" not in client.get("/institution").get_data(as_text=True)
    client, r = _sign_in(app, EMAIL, MOBILE)
    with client.session_transaction() as s:
        assert s["inst_id"] == iid
    assert client.get(f"/institution/switch/{second}").status_code == 404
    assert "Second College" not in client.get("/institution").get_data(as_text=True)
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM outbox", one=True)["n"] == 0


def test_twenty_tries_that_fail_in_an_hour_and_no_more():
    from kts import campus, i18n
    assert campus.MOBILE_TRIES == 20
    app, _iid = _app()
    for n in range(20):
        _c, r = _sign_in(app, EMAIL, f"90000000{n + 10}")
        assert r.status_code == 400, n
    client, r = _sign_in(app)                                           # the right number, too late
    assert r.status_code == 429 and "Too many tries from this connection in the last hour." in r.get_data(as_text=True)
    assert "or from another connection (for example the mobile data of a phone)" in r.get_data(as_text=True)      # 1.2.217
    assert not _signed_in(client) and i18n.text("reg.err_rate", "en")
    assert len(_audit(app, "institution_login_refused")) == 20


def test_the_sign_ins_that_succeed_do_not_count():
    app, _iid = _app()
    for n in range(14):
        client, r = _sign_in(app)
        assert r.status_code == 302, n
    for n in range(9):
        _sign_in(app, EMAIL, "9111111111")
    client, r = _sign_in(app)
    assert r.status_code == 302 and _signed_in(client)


# ---- the code, while the setting is on ---------------------------------------------------------------------------------------------

def test_with_the_setting_on_the_code_is_mailed_as_before():
    from kts.db import set_setting
    app, _iid = _app()
    with app.app_context():
        set_setting("inst.code_mail", "1")
    client, token = _client(app)
    page = client.get("/institution/login").get_data(as_text=True)
    assert "The portal mails a six-digit code; no password is needed." in page and "Send me the code" in page
    assert 'name="mobile"' not in page
    r = client.post("/institution/login", data={"_csrf": token, "email": EMAIL, "mobile": MOBILE})
    assert r.status_code == 200 and "a six-digit code has been mailed" in r.get_data(as_text=True) and not _signed_in(client)
    mail = _mails(app, EMAIL)[-1]
    assert mail["subject"] == "KTS 5.0: your sign-in code" and mail["priority"] == -1
    # a code asked for before the codes were stopped still signs in
    with app.app_context():
        set_setting("inst.code_mail", "0")
    wrong = client.post("/institution/code", data={"_csrf": token, "code": "000000x"})
    assert wrong.status_code == 400 and 'id="code"' in wrong.get_data(as_text=True)
    code = re.search(r"\n    (\d{6})\n", mail["body"]).group(1)
    r = client.post("/institution/code", data={"_csrf": token, "code": code})
    assert r.status_code == 302 and _signed_in(client)
    assert _audit(app, "institution_login")[-1]["detail"] == EMAIL


# ---- the queue ---------------------------------------------------------------------------------------------------------------------

def _waiting(app, to, subject):
    from kts.db import execute, utcnow
    with app.app_context():
        return execute("INSERT INTO outbox(to_addr, subject, body, status, created_at, priority) VALUES(?,?,?,?,?,?)",
                       (to, subject, "Body", "queued", utcnow(), -1))


def test_a_code_that_still_waits_is_not_sent(server):
    from kts import mailq
    from kts.utils import INST_CODE_SUBJECT
    assert INST_CODE_SUBJECT == "KTS 5.0: your sign-in code"
    app = _no_codes(_mail_app(paused=1))
    _waiting(app, "coord@x.example", INST_CODE_SUBJECT)
    _waiting(app, "nodal@x.example", "Your KTS 5.0 portal account")
    assert mailq.run_once(app, T0)["sent"] == 1 and server.sent == ["nodal@x.example"]
    rows = {r["to_addr"]: r for r in _rows(app)}
    assert (rows["coord@x.example"]["status"], rows["coord@x.example"]["error"]) == ("failed", mailq.CODES_OFF)
    assert rows["nodal@x.example"]["status"] == "sent"
    # with the codes on, one that waits goes, as since 1.2.207
    from kts.db import set_setting
    with app.app_context():
        set_setting("inst.code_mail", "1")
    _waiting(app, "coord2@x.example", INST_CODE_SUBJECT)
    assert mailq.run_once(app, T0)["sent"] == 1 and server.sent[-1] == "coord2@x.example"


def test_the_account_of_a_nodal_officer_goes_at_once_past_a_pause(server, monkeypatch):
    from kts import mailq, utils
    monkeypatch.setattr(utils.threading, "Thread", Inline)
    app = _no_codes(_mail_app(daily_limit=0, paused=1))      # the day's mails all sent, and sending paused in the Console
    with app.test_request_context():
        from kts.admin import _create_account
        _create_account("nodal.kl@tests.example", "Dr. Nodal", "nodal", states=["Kerala"])
        _create_account("viewer@tests.example", "A Viewer", "viewer")
    rows = {r["to_addr"]: r for r in _rows(app)}
    nodal, viewer = rows["nodal.kl@tests.example"], rows["viewer@tests.example"]
    assert nodal["subject"] == viewer["subject"] == "Your KTS 5.0 portal account" and "Temporary password: Kts5-" in nodal["body"]
    assert (nodal["status"], nodal["priority"]) == ("sent", -1) and server.sent == ["nodal.kl@tests.example"]
    assert (viewer["status"], viewer["priority"]) == ("queued", 0)
    assert mailq.run_once(app, T0)["waiting"] == "paused" and server.sent == ["nodal.kl@tests.example"]


# ---- the texts ---------------------------------------------------------------------------------------------------------------------

def test_the_four_texts_without_the_code_in_the_23_languages():
    from kts import i18n
    assert i18n.NOCODE == frozenset(KEYS) and not (i18n.NOCODE & i18n.UNDATED)
    assert len(i18n.CATALOG) == 23 and len(i18n.CATALOG["en"]) == 1561
    en = i18n.CATALOG["en"]
    assert en["guide.i2_nc"] == ("Sign in with the e-mail address of the Institutional Coordinator or of the Head of the Institution "
                                 "and the mobile number of the Institutional Coordinator given at registration. No code is mailed; "
                                 "there is no password.")
    assert en["nl.s1_nc"] == ("The Institutional Coordinator signs in at {portal}/institution/login with the e-mail address and the "
                              "mobile number given at registration; no code is mailed, there is no password. Please see that the Head "
                              "of the Institution, the Institutional Coordinator and the Faculty Supervisor/Guide are named there "
                              "with e-mail and mobile.")
    assert en["nl.art_c1_nc"] == ("{portal}/institution/login — the Institutional Coordinator signs in with the e-mail and the mobile "
                                  "number given at registration; no code is mailed, no password.")
    assert en["hs.c1_nc"] == ("Open {inst_login} and enter the e-mail address of the Institutional Coordinator or of the Head of the "
                              "Institution, and the mobile number of the Institutional Coordinator given at registration. No code is "
                              "mailed; there is no password.")
    seen = {key: set() for key in KEYS}
    for code, cat in i18n.CATALOG.items():
        for key in KEYS:
            old, new = cat[key], cat[key + "_nc"]
            assert new and new == new.strip() and "\n" not in new and new != old, (code, key)
            assert sorted(re.findall(r"\{[a-z_]+\}", new)) == sorted(re.findall(r"\{[a-z_]+\}", old)), (code, key)
            assert not re.search(r"\d", new), (code, key)             # no minutes and no number of digits of a code
            assert new not in seen[key], (code, key)                 # each language has its own text
            seen[key].add(new)
        assert "{portal}/institution/login" in cat["nl.s1_nc"] and "{portal}/institution/login" in cat["nl.art_c1_nc"], code


def test_the_texts_follow_the_setting():
    from kts import i18n
    from kts.db import set_setting
    en, hi = i18n.CATALOG["en"], i18n.CATALOG["hi"]
    assert i18n.text("guide.i2", "en") == en["guide.i2_nc"]            # outside the portal no code is promised
    app = _no_codes(make_app(ADMIN_PASSWORD=None))
    with app.app_context():
        for key in KEYS:
            assert i18n.text(key, "en") == en[key + "_nc"] and i18n.text(key, "hi") == hi[key + "_nc"], key
        set_setting("inst.code_mail", "1")
        for key in KEYS:
            assert i18n.text(key, "en") == en[key] and i18n.text(key, "hi") == hi[key], key


def _in_page(page, text):
    """The text is on the page, around what fills its placeholders."""
    return all(str(escape(part)) in page for part in re.split(r"\{[a-z_]+\}", text) if part.strip())


def test_the_guide_and_the_steps_in_every_language():
    from kts import i18n
    from kts.db import set_setting
    app = _no_codes(make_app(ADMIN_PASSWORD=None))
    client = app.test_client()
    for code, cat in i18n.CATALOG.items():
        guide = client.get(f"/how-to-take-part/institutions?lang={code}").get_data(as_text=True)
        steps = client.get(f"/how-to-submit-the-student?lang={code}").get_data(as_text=True)
        assert _in_page(guide, cat["guide.i2_nc"]) and not _in_page(guide, cat["guide.i2"]), code
        assert _in_page(steps, cat["hs.c1_nc"]) and not _in_page(steps, cat["hs.c1"]), code
        # the other pages that carry these texts: the assessment, and how to take part
        for path in ("/examination", "/how-to-take-part"):
            page = client.get(f"{path}?lang={code}").get_data(as_text=True)
            assert not _in_page(page, cat["guide.i2"]) and not _in_page(page, cat["hs.c1"]), (code, path)
    with app.app_context():
        set_setting("inst.code_mail", "1")
    for code in ("en", "hi", "ta", "ur"):
        cat = i18n.CATALOG[code]
        guide = client.get(f"/how-to-take-part/institutions?lang={code}").get_data(as_text=True)
        steps = client.get(f"/how-to-submit-the-student?lang={code}").get_data(as_text=True)
        assert _in_page(guide, cat["guide.i2"]) and not _in_page(guide, cat["guide.i2_nc"]), code
        assert _in_page(steps, cat["hs.c1"]) and not _in_page(steps, cat["hs.c1_nc"]), code


def test_the_letter_of_the_nodal_institution():
    from kts import letters
    app = _no_codes(make_app(ADMIN_PASSWORD=None))
    with app.app_context():
        line = letters.fill("nl.s1", "en", {"portal": "kts.cict.in"})
        assert line.startswith("The Institutional Coordinator signs in at kts.cict.in/institution/login with the e-mail address and "
                               "the mobile number given at registration; no code is mailed, there is no password.")
        assert "a sign-in code is mailed" not in line


def test_the_help_page():
    from kts.db import set_setting
    app = _no_codes(make_app(ADMIN_PASSWORD=None))
    client = app.test_client()
    new = {"en": "and the mobile number of the Institutional Coordinator given at registration: no code is mailed.",
           "hi": "ईमेल पते और पंजीकरण के समय दिए गए संस्थान समन्वयक के मोबाइल नंबर से",
           "ta": "பதிவின்போது அளித்த நிறுவன ஒருங்கிணைப்பாளரின் அலைபேசி எண்ணையும் கொண்டு"}
    old = {"en": "a six-digit code is mailed to you.", "hi": "आपको छह अंकों का कोड ईमेल किया जाता है।",
           "ta": "ஆறு இலக்கக் குறியீடு உங்களுக்கு மின்னஞ்சலில் அனுப்பப்படும்."}
    for code in new:
        page = client.get(f"/help?lang={code}").get_data(as_text=True)
        assert new[code] in page and old[code] not in page, code
    with app.app_context():
        set_setting("inst.code_mail", "1")
    for code in new:
        page = client.get(f"/help?lang={code}").get_data(as_text=True)
        assert old[code] in page and new[code] not in page, code


def test_the_mails_that_tell_an_institution_how_it_signs_in():
    from kts import heis, progress
    from kts.db import query, set_setting
    from kts.utils import inst_signin_words
    app, iid = _app()
    with app.test_request_context():
        assert inst_signin_words() == (" and the mobile number of the Institutional Coordinator given at registration "
                                       "(no code is mailed; there is no password)")
        row = query("SELECT * FROM institutions WHERE id = ?", (iid,), one=True)
        heis.mail_decision(row)
        reminder = progress.mails_for(progress.institutions(ids=[iid])[0], "start")[0][2]
    invitation = _mails(app)[-1]["body"]
    assert ("with the e-mail address of the Institutional Coordinator or of the Head of the Institution and the mobile number of the "
            "Institutional Coordinator given at registration (no code is mailed; there is no password). There you may") in invitation
    assert ("Sign in to the institution's page with this e-mail address and the mobile number of the Institutional Coordinator given "
            "at registration (no code is mailed, no password): ") in reminder
    assert "six-digit" not in invitation and "a code is mailed to you" not in reminder
    with app.app_context():
        set_setting("inst.code_mail", "1")
    with app.test_request_context():
        assert inst_signin_words() == " (a six-digit code is mailed; there is no password)"
        assert inst_signin_words(short=True) == " (a code is mailed to you, no password)"
        heis.mail_decision(row)
        reminder = progress.mails_for(progress.institutions(ids=[iid])[0], "start")[0][2]
    assert "of the Head of the Institution (a six-digit code is mailed; there is no password). There you may" in _mails(app)[-1]["body"]
    assert "with this e-mail address (a code is mailed to you, no password): " in reminder


# ---- what a sign-in opens (the independent review of the release, 26 November 2026) -------------------------------------------------

def test_a_made_up_institution_with_the_address_of_another_does_not_open_it():
    """
    Anybody can register an institution with somebody else's e-mail address (the form is open). The number that he proves is his
    own: it opens his own institution and no other of that address. (Up to 1.2.215 the code went to the mailbox of the address.)
    """
    app, victim = _app()
    stranger = _make(app, "Stranger College", head_email=EMAIL, coord_email="someone@else.example", coord_mobile="9333333333")
    client, r = _sign_in(app, EMAIL, "9333333333")
    assert r.status_code == 302
    page = client.get("/institution").get_data(as_text=True)
    assert "Stranger College" in page and "Plain College" not in page
    assert client.get(f"/institution/switch/{victim}").status_code == 404
    with client.session_transaction() as s:
        assert s["inst_id"] == stranger
    assert "Plain College" not in client.get("/institution").get_data(as_text=True)
    assert client.get("/institution/students.xlsx").status_code == 200       # his own list, not the other's
    # nor with the cookie of the device alone
    other = app.test_client()
    other.set_cookie("kts_inst", client.get_cookie("kts_inst").value)
    assert other.get(f"/institution/switch/{victim}").status_code == 404
    page = other.get("/institution").get_data(as_text=True)
    assert "Stranger College" in page and "Plain College" not in page
    assert _audit(app, "institution_switch") == []


def test_the_institutions_of_one_coordinator_open_together():
    app, iid = _app()
    second = _make(app, "Second College", coord_email=EMAIL, coord_mobile="+91 90000 00001")
    client, r = _sign_in(app)
    assert r.status_code == 302 and "Second College" in client.get("/institution").get_data(as_text=True)
    assert client.get(f"/institution/switch/{second}").status_code == 302
    assert "Second College" in client.get("/institution").get_data(as_text=True)
    assert [(a["entity_id"], a["detail"]) for a in _audit(app, "institution_switch")] == [(second, EMAIL)]
    assert client.get(f"/institution/switch/{iid}").status_code == 302


def test_the_session_and_the_cookie_carry_a_mark_not_the_number():
    from kts import campus
    app, iid = _app()
    client, r = _sign_in(app)
    with client.session_transaction() as s:
        mark, token = s["inst_m"], s["_csrf"]
        assert len(mark) == 32 and MOBILE not in json.dumps({k: str(v) for k, v in dict(s).items()})
    with app.test_request_context():
        data = campus._device_signer().loads(client.get_cookie("kts_inst").value)
        assert data == {"e": EMAIL, "i": iid, "m": mark} and mark == campus._number_mark(MOBILE)
    # signing out ends it on the device
    r = client.post("/institution/logout", data={"_csrf": token})
    assert r.status_code == 302 and client.get_cookie("kts_inst") is None
    with client.session_transaction() as s:
        assert "inst_m" not in s and "inst_id" not in s and "inst_email" not in s
    assert client.get("/institution").status_code == 302


def test_a_number_corrected_in_the_console_ends_the_sign_ins_made_with_the_old_one():
    from kts.db import execute
    app, iid = _app()
    client, r = _sign_in(app)
    cookie = client.get_cookie("kts_inst").value
    assert _signed_in(client)
    with app.app_context():
        execute("UPDATE institutions SET coord_mobile = '9000000009' WHERE id = ?", (iid,))
    assert client.get("/institution").status_code == 302                    # the session
    other = app.test_client()
    other.set_cookie("kts_inst", cookie)
    assert other.get("/institution").status_code == 302                     # the cookie of the device
    _c, r = _sign_in(app)
    assert r.status_code == 400                                             # the old number
    client, r = _sign_in(app, EMAIL, "9000000009")
    assert r.status_code == 302 and _signed_in(client)
    # an address that is no longer the institution's, and a declined institution, as with the code (1.2.212)
    with app.app_context():
        execute("UPDATE institutions SET status = 'declined' WHERE id = ?", (iid,))
    assert client.get("/institution").status_code == 302


@pytest.mark.parametrize("stored, typed", [
    ("+91 90000 00001", MOBILE), ("090000 00001", MOBILE), ("0091 9000000001", MOBILE), ("+91 (0) 90000 00001", MOBILE),
    ("90000 00001 / 91234 56780", MOBILE), ("90000 00001 / 91234 56780", "91234 56780"), ("9000000001, 044-22541234", MOBILE),
    ("90000 00001 or 9123456780", "9123456780"), ("९००००००००१", MOBILE), ("9000000001", "९००००००००१"),
])
def test_a_number_kept_as_people_write_it(stored, typed):
    from kts.db import execute
    app, iid = _app()
    with app.app_context():
        execute("UPDATE institutions SET coord_mobile = ? WHERE id = ?", (stored, iid))
    client, r = _sign_in(app, EMAIL, typed)
    assert r.status_code == 302 and _signed_in(client)


@pytest.mark.parametrize("stored", ["N/A", "90000 0000", "", "0000000000", "900000000100"])
def test_a_number_that_cannot_be_read_opens_nothing(stored):
    from kts.db import execute
    app, iid = _app()
    with app.app_context():
        execute("UPDATE institutions SET coord_mobile = ? WHERE id = ?", (stored, iid))
    for typed in (stored, MOBILE, ""):
        client, r = _sign_in(app, EMAIL, typed)
        assert r.status_code == 400 and not _signed_in(client), typed


def test_the_form_of_before_the_update_is_asked_for_the_number():
    app, _iid = _app()
    client, token = _client(app)
    for _ in range(25):                        # the old form had the address alone: nothing is counted, nothing is refused
        r = client.post("/institution/login", data={"_csrf": token, "email": EMAIL})
    page = r.get_data(as_text=True)
    assert r.status_code == 200 and '<div class="alert info">No code is mailed any more. Enter the mobile number of the' in page
    assert ERROR not in page and 'name="mobile"' in page and f'value="{EMAIL}"' in page
    assert _audit(app, "institution_login_refused") == [] and _mails(app) == []
    r = client.post("/institution/login", data={"_csrf": token, "email": EMAIL, "mobile": MOBILE})
    assert r.status_code == 302 and _signed_in(client)


def test_the_limit_is_of_one_address_of_the_network_and_ends_after_the_hour():
    from kts.utils import limiter
    app, _iid = _app()

    def post(ip, mobile, email=EMAIL):
        client = app.test_client()
        client.get("/institution/login", environ_base={"REMOTE_ADDR": ip})
        with client.session_transaction() as s:
            token = s["_csrf"]
        return client.post("/institution/login", data={"_csrf": token, "email": email, "mobile": mobile}, environ_base={"REMOTE_ADDR": ip})

    for n in range(20):                        # wrong numbers and unknown addresses count alike
        assert post("198.51.100.7", "9111111111", EMAIL if n % 2 else "nobody@x.example").status_code == 400, n
    assert post("198.51.100.7", MOBILE).status_code == 429
    assert post("198.51.100.8", MOBILE).status_code == 302          # another address of the network is not held back
    real = limiter._clock
    try:
        limiter._clock = lambda: real() + 3601
        assert post("198.51.100.7", MOBILE).status_code == 302      # after the hour
    finally:
        limiter._clock = real


def test_a_sign_in_with_the_code_opens_the_institutions_of_the_address_as_before():
    from kts.db import set_setting
    app, _iid = _app()
    second = _make(app, "Second College", coord_email=EMAIL, coord_mobile="9000000002")
    with app.app_context():
        set_setting("inst.code_mail", "1")
    client, token = _client(app)
    client.post("/institution/login", data={"_csrf": token, "email": EMAIL})
    code = re.search(r"\n    (\d{6})\n", _mails(app, EMAIL)[-1]["body"]).group(1)
    assert client.post("/institution/code", data={"_csrf": token, "code": code}).status_code == 302
    with client.session_transaction() as s:
        assert "inst_m" not in s
    assert "Second College" in client.get("/institution").get_data(as_text=True)
    assert client.get(f"/institution/switch/{second}").status_code == 302


def test_the_console_checks_the_number_that_the_institution_signs_in_with():
    from test_public_fixes import _staff
    from kts import heis
    from kts.db import query
    app = _no_codes(make_app(ADMIN_PASSWORD=None))
    iid = _make(app, "Plain College")
    staff = _staff(app, "chief1126@tests.example", role="superadmin")
    page = staff.get(f"/console/institutions/{iid}/edit")
    assert page.status_code == 200 and "Coordinator: mobile (the institution signs in with it)" in page.get_data(as_text=True)
    with app.app_context():
        row = dict(query("SELECT * FROM institutions WHERE id = ?", (iid,), one=True))
    ref = json.loads((ROOT / "data" / "states.json").read_text(encoding="utf-8"))
    with staff.session_transaction() as s:
        token = s["_csrf"]
    form = {f: row.get(f) or "" for f in heis.FIELDS}
    form.update(_csrf=token, itype=ref["college_types"][0], head_designation="Principal", head_phone="04422540000",
                coord_designation="Professor")

    def stored():
        with app.app_context():
            return query("SELECT coord_mobile FROM institutions WHERE id = ?", (iid,), one=True)["coord_mobile"]

    for bad in ("N/A", "90000 0000"):
        r = staff.post(f"/console/institutions/{iid}/edit", data={**form, "coord_mobile": bad})
        assert r.status_code == 200 and "a 10-digit mobile number: the institution signs in with it" in r.get_data(as_text=True), bad
        assert stored() == "9000000001"
    r = staff.post(f"/console/institutions/{iid}/edit", data={**form, "coord_mobile": "90000 00009"})
    assert r.status_code == 302 and stored() == "90000 00009"
    client, r = _sign_in(app, EMAIL, "9000000009")
    assert r.status_code == 302 and _signed_in(client)
    _c, r = _sign_in(app)
    assert r.status_code == 400


def test_a_code_is_not_put_back_in_the_queue(server):
    from kts.db import execute, query
    from kts.utils import INST_CODE_SUBJECT, send_again
    app = _no_codes(_mail_app(paused=1))
    _waiting(app, "coord@x.example", INST_CODE_SUBJECT)
    _waiting(app, "other@x.example", "Another mail")
    with app.test_request_context():
        execute("UPDATE outbox SET status = 'failed', error = 'refused'")
        send_again(query("SELECT * FROM outbox"))
    assert {r["to_addr"]: r["status"] for r in _rows(app)} == {"coord@x.example": "failed", "other@x.example": "queued"}


def test_the_wrong_codes_are_counted_on_the_server_too():
    """The count of the session lies in the visitor's own cookie: the first cookie sent again began at nought (the review)."""
    from kts.db import set_setting
    app, _iid = _app()
    with app.app_context():
        set_setting("inst.code_mail", "1")
    client, token = _client(app)
    client.post("/institution/login", data={"_csrf": token, "email": EMAIL})
    first = client.get_cookie("session").value                      # the session with the code asked for and no wrong try
    code = re.search(r"\n    (\d{6})\n", _mails(app, EMAIL)[-1]["body"]).group(1)
    wrong = "000000" if code != "000000" else "111111"
    answers = []
    for _ in range(7):
        client.set_cookie("session", first)                          # the first cookie again, each time
        answers.append(client.post("/institution/code", data={"_csrf": token, "code": wrong}).get_data(as_text=True))
    assert all("The code is wrong." in a for a in answers[:5]) and all("Too many wrong codes" in a for a in answers[5:])
    client.set_cookie("session", first)
    r = client.post("/institution/code", data={"_csrf": token, "code": code})
    assert r.status_code == 400 and not _signed_in(client)           # the code is spent
    # a new code works as before
    client, token = _client(app)
    client.post("/institution/login", data={"_csrf": token, "email": EMAIL})
    code = re.search(r"\n    (\d{6})\n", _mails(app, EMAIL)[-1]["body"]).group(1)
    assert client.post("/institution/code", data={"_csrf": token, "code": code}).status_code == 302

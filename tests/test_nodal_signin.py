"""
The sign-in reminder to the Nodal Officers whose Console account has never been signed in to (version 1.2.136): from Console >
Nodal officers, to all of them or to one, and every third morning with the morning mail; what the mail says.

    python -m pytest tests -q
"""
from datetime import datetime

from test_nodal_access import _nodal, _portal, _token
from test_public_fixes import _staff

SUBJECT = "KTS 5.0: your Console account awaits your first sign-in"


def _at(day, hour, minute=0):
    from kts.utils import IST
    return datetime(2026, 10, day, hour, minute, tzinfo=IST)


def _account(app, email, states, created="2026-10-27T10:00:00+00:00", name="Dr. New Officer", active=1):
    """An account of a Nodal Officer made by CICT, never signed in to."""
    from werkzeug.security import generate_password_hash
    from kts.db import execute
    with app.app_context():
        return execute("INSERT INTO users(email, name, password_hash, role, active, must_change_password, created_at, states, designation) "
                       "VALUES(?,?,?,?,?,1,?,?,?)", (email, name, generate_password_hash("Kts5-test-only"), "nodal", active, created,
                                                    "|".join(states), "Registrar"))


def _outbox(app, to_addr=None):
    from kts.db import query
    with app.app_context():
        return query("SELECT * FROM outbox" + (" WHERE to_addr = ?" if to_addr else "") + " ORDER BY id", (to_addr,) if to_addr else ())


def test_what_the_mail_says():
    from kts import nodal
    from kts.db import execute, get_setting, query, utcnow
    app, _ids = _portal()   # two applications of Kerala await verification
    uid = _account(app, "new.kerala@tests.example", ["Kerala"])
    with app.app_context():
        from kts.db import set_setting
        set_setting("reg.end", "2026-11-24")   # the tests' portal keeps registration open far ahead
        for n, (name, status) in enumerate((("Kochi College", "accepted"), ("Kannur College", "pending"), ("Listed College", "identified"))):
            execute("INSERT INTO institutions(ref, name, itype, state, district, inst_key, status, created_at, updated_at) "
                    "VALUES(?, ?, 'Government college', 'Kerala', 'Kochi', ?, ?, ?, ?)", (f"KTS5-HEI-7{n:04d}", name, f"name:{name}|kerala", status, utcnow(), utcnow()))
        u = query("SELECT * FROM users WHERE id = ?", (uid,), one=True)
        assert [x["email"] for x in nodal.not_signed_in()] == ["new.kerala@tests.example"]
        subject, body = nodal.signin_mail(u)
        contact = get_setting("contact.email")
    base = app.config["BASE_URL"]
    assert subject == f"{SUBJECT} (Kerala and Lakshadweep)"
    assert body.startswith("Dear Dr. New Officer,\n\nYour account as Nodal Officer for Kerala and Lakshadweep on the KTS 5.0 portal ")
    assert "was created on 27 October 2026 and the temporary password was mailed to this address; the account has not been signed in to yet." in body
    assert "• The institutions of Kerala and Lakshadweep register on the portal up to 18 November 2026: 2 registered so far, 1 awaiting your decision." in body
    assert "• The Nodal Institution selects the 21 Participating Institutions that Annexure-I prescribes by 19 November 2026, with a reserve list, in the Console (Institutions)." in body
    assert ("• Each selected institution nominates one student by 24 November 2026; the Nodal Officers verify the nominations by 5 December 2026. "
            "2 application(s) await your verification already.") in body
    assert f"\nSign in: {base}/console/login\nE-mail: new.kerala@tests.example\n" in body
    assert 'Password: the temporary password in the mail "Your KTS 5.0 portal account" of 27 October 2026. The portal asks you to set a password of your own at the first sign-in.' in body
    assert f"If that mail cannot be found, write to {contact} and CICT will send a new temporary password." in body
    assert "The video guide for Nodal Officers (13 minutes): https://www.youtube.com/watch?v=V3JtCOfqIzo" in body
    assert f"The Nodal Institutions and the numbers of Annexure-I: {base}/nodal-institutions" in body
    assert body.endswith("\n\nCentral Institute of Classical Tamil, Chennai") and "Kts5-test-only" not in body
    # an officer of a State with nothing yet, and no date of the account
    uid2 = _account(app, "new.goa@tests.example", ["Goa"], created="")
    with app.app_context():
        subject, body = nodal.signin_mail(query("SELECT * FROM users WHERE id = ?", (uid2,), one=True))
    assert subject.endswith("(Goa)") and "was created and the temporary password" in body and ": 0 registered so far." in body
    assert "await your verification" not in body and 'mail "Your KTS 5.0 portal account". The portal' in body


def test_the_console_reminds_them_all_or_one():
    from kts.db import query
    app, _ids = _portal()
    new = _account(app, "new.kerala@tests.example", ["Kerala"])
    _account(app, "new.goa@tests.example", ["Goa"], name="Dr. Goa Officer")
    _account(app, "off.bihar@tests.example", ["Bihar"], name="Dr. Disabled", active=0)
    assam = _nodal(app, "assam@tests.example", ["Assam"])   # has signed in
    admin = _staff(app, "admin@tests.example", "superadmin")
    page = admin.get("/console/nodal").get_data(as_text=True)
    assert "Accounts of Nodal Officers not signed in to yet: <b>2</b>" in page
    assert 'value="remind_signin" data-confirm="Send a sign-in reminder now to every Nodal Officer who has not signed in yet?">✉ Remind the 2 officer(s) who have not signed in yet</button>' in page
    kerala = page.split("Central University of Kerala")[1].split("</tr>")[0]
    assert '<span class="pill saffron">not signed in yet</span>' in kerala and f'<input type="hidden" name="uid" value="{new}">' in kerala
    assert "Remind to sign in" in kerala and "reminded" not in kerala
    assam_row = page.split("Assam University")[1].split("</tr>")[0]
    assert "Remind to sign in" not in assam_row and "last sign-in" in assam_row
    bihar = page.split("Central University of South Bihar")[1].split("</tr>")[0]
    assert '<span class="pill grey">disabled</span>' in bihar and "Remind to sign in" not in bihar
    # all of them: the two active accounts never signed in to
    r = admin.post("/console/nodal", data={"_csrf": _token(admin), "action": "remind_signin"}, follow_redirects=True)
    assert "A sign-in reminder is queued to 2 Nodal Officer(s) who have not signed in yet" in r.get_data(as_text=True)
    rows = _outbox(app)
    assert [(m["to_addr"], m["subject"]) for m in rows] == [("new.kerala@tests.example", f"{SUBJECT} (Kerala and Lakshadweep)"),
                                                            ("new.goa@tests.example", f"{SUBJECT} (Goa)")]
    assert all(m["status"] == "queued" for m in rows)
    page = admin.get("/console/nodal").get_data(as_text=True)
    kerala = page.split("Central University of Kerala")[1].split("</tr>")[0]
    assert "· reminded " in kerala
    # one of them; an officer who has signed in gets none
    r = admin.post("/console/nodal", data={"_csrf": _token(admin), "action": "remind_signin", "uid": new}, follow_redirects=True)
    assert "queued to 1 Nodal Officer(s)" in r.get_data(as_text=True) and len(_outbox(app, "new.kerala@tests.example")) == 2
    with app.app_context():
        assam_id = query("SELECT id FROM users WHERE email = 'assam@tests.example'", one=True)["id"]
    r = admin.post("/console/nodal", data={"_csrf": _token(admin), "action": "remind_signin", "uid": assam_id}, follow_redirects=True)
    assert "No reminder sent: the officer has signed in already, or the account is disabled." in r.get_data(as_text=True)
    assert len(_outbox(app)) == 3
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM audit_log WHERE action = 'nodal_signin_reminder'", one=True)["n"] == 3
    # not for a Nodal Officer
    assert assam.post("/console/nodal", data={"_csrf": _token(assam), "action": "remind_signin"}).status_code == 403
    # an officer who signed in but has not set a password yet is told so, and is not reminded to sign in
    with app.app_context():
        from kts.db import execute, utcnow
        execute("UPDATE users SET last_login_at = ? WHERE id = ?", (utcnow(), new))
    page = admin.get("/console/nodal").get_data(as_text=True)
    kerala = page.split("Central University of Kerala")[1].split("</tr>")[0]
    assert '<span class="pill saffron">password not yet set</span>' in kerala and "Remind to sign in" not in kerala
    assert "Accounts of Nodal Officers not signed in to yet: <b>1</b>" in page


def test_every_third_morning_with_the_morning_mail():
    from kts import nodal
    from kts.db import execute, set_setting, utcnow
    app, _ids = _portal()   # two applications of Kerala await: the officer of Kerala gets the morning mail every day
    _nodal(app, "kerala@tests.example", ["Kerala"])
    _account(app, "new.goa@tests.example", ["Goa"], created="2026-10-10T08:00:00+00:00")
    with app.app_context():
        set_setting("reg.start", "2026-10-15")
        set_setting("verify.end", "2026-10-31")
    assert nodal.daily(app, _at(16, 8, 5)) == 2          # the morning mail of Kerala, and the sign-in reminder (6 days after the account)
    assert [m["subject"] for m in _outbox(app, "new.goa@tests.example")] == [f"{SUBJECT} (Goa)"]
    assert nodal.daily(app, _at(17, 8, 5)) == 1          # the next day: the morning mail only
    assert nodal.daily(app, _at(18, 8, 5)) == 1
    assert nodal.daily(app, _at(19, 8, 5)) == 2          # three days after the reminder: again
    assert len(_outbox(app, "new.goa@tests.example")) == 2
    with app.app_context():
        from kts.db import query
        stamp = query("SELECT signin_reminded_at FROM users WHERE email = 'new.goa@tests.example'", one=True)["signin_reminded_at"]
        assert stamp.startswith("2026-10-19T08:05")   # the day of the last reminder, on the account
        execute("UPDATE users SET last_login_at = ? WHERE email = 'new.goa@tests.example'", (utcnow(),))   # signed in at last
    assert nodal.daily(app, _at(22, 8, 5)) == 1          # no more
    assert len(_outbox(app, "new.goa@tests.example")) == 2
    # a disabled account is left alone
    _account(app, "off.bihar@tests.example", ["Bihar"], created="2026-10-01T08:00:00+00:00", active=0)
    assert nodal.daily(app, _at(23, 8, 5)) == 1

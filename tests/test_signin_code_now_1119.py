"""
The sign-in code of the institution's page, sent at once (1.2.207). CICT, 19 November 2026: "KTS 5.0: your sign-in code have to be
sent as soon as possible. no wait. do it".

The code leaves the moment it is asked for, in a thread of its own, outside the queue and its limits and a pause of the Console.
If the mail server does not take it, it waits in the queue before every other mail and the sender's next round tries it again,
past the limits. The other mails keep the queue and its limits.

    python -m pytest tests/test_signin_code_now_1119.py -q
"""
import smtplib
from datetime import timedelta

import pytest

from test_mailq import T0, Server, _app, _queue, _rows, server  # noqa: F401  (the fixture of the mail server of the tests)
from test_reserve_1111 import _insert

EMAIL = "coord@codecollege.example"


class Inline:
    """A thread of the tests: it runs at once, so that the test sees what the thread did."""

    def __init__(self, target, args=(), name=None, daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture(autouse=True)
def inline_threads(monkeypatch):
    from kts import utils
    from kts.utils import limiter
    monkeypatch.setattr(utils.threading, "Thread", Inline)
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def _ask_for_the_code(app):
    client = app.test_client()
    client.get("/institution/login")
    with client.session_transaction() as s:
        token = s["_csrf"]
    r = client.post("/institution/login", data={"_csrf": token, "email": EMAIL})
    assert r.status_code == 200 and "a six-digit code has been mailed" in r.get_data(as_text=True)
    return client


def _codes(app):
    return [r for r in _rows(app) if r["subject"] == "KTS 5.0: your sign-in code"]


def test_the_code_leaves_at_once_past_the_limits_and_a_pause(server):
    from kts import mailq
    app = _app(daily_limit=0, paused=1)      # the day's mails all sent, and sending paused in the Console
    _insert(app, "Code College", "Kerala", "Kochi", "accepted", None, coord_email=EMAIL)
    _queue(app, "student@x.in")              # a mail to one person, which waits
    _ask_for_the_code(app)
    code = _codes(app)
    assert len(code) == 1 and code[0]["status"] == "sent" and code[0]["priority"] == -1 and code[0]["sent_at"]
    assert server.sent == [EMAIL]
    # the other mails keep the queue and its limits
    assert mailq.run_once(app, T0)["waiting"] == "paused" and server.sent == [EMAIL]
    assert [r["status"] for r in _rows(app) if r["to_addr"] == "student@x.in"] == ["queued"]


def test_a_code_the_server_does_not_take_waits_first_and_goes_past_the_limits(server):
    from kts import mailq
    app = _app(per_minute=1, daily_limit=1)
    _insert(app, "Code College", "Kerala", "Kochi", "accepted", None, coord_email=EMAIL)
    _queue(app, "first@x.in", "second@x.in")
    server.answer = smtplib.SMTPServerDisconnected("the connection was closed")
    _ask_for_the_code(app)
    code = _codes(app)[0]
    assert code["status"] == "queued" and code["priority"] == -1 and "closed" in code["error"] and server.sent == []
    server.answer = None
    # the next round: the code first, then the room of the limits for the others
    assert mailq.run_once(app, T0)["sent"] == 2 and server.sent == [EMAIL, "first@x.in"]
    assert _codes(app)[0]["status"] == "sent"
    # the limit of 24 hours reached: the others wait, a code that waits still goes
    _ask_for_the_code(app)
    assert server.sent == [EMAIL, "first@x.in", EMAIL]
    later = T0 + timedelta(minutes=3)
    assert mailq.run_once(app, later)["waiting"] in ("daily limit", "limit per minute")
    # a pause of the Console does not hold a code that waits either
    from kts.db import set_setting
    with app.app_context():
        set_setting("mail.paused", "1")
    server.answer = smtplib.SMTPServerDisconnected("closed again")
    _ask_for_the_code(app)
    server.answer = None
    assert mailq.run_once(app, later + timedelta(minutes=1))["sent"] == 1 and server.sent[-1] == EMAIL
    assert [r["status"] for r in _rows(app) if r["to_addr"] == "second@x.in"] == ["queued"]


def test_google_refusing_for_the_day_holds_it_as_every_mail(server):
    from kts import mailq
    app = _app()
    _insert(app, "Code College", "Kerala", "Kochi", "accepted", None, coord_email=EMAIL)
    server.answer = smtplib.SMTPDataError(550, b"5.4.5 Daily user sending quota exceeded")
    _ask_for_the_code(app)
    assert _codes(app)[0]["status"] == "queued"
    # the sender meets the refusal too and pauses for the hour; the code goes when Google takes mails again
    assert mailq.run_once(app, T0)["waiting"] == "daily quota of the mail account used up"
    server.answer = None
    assert mailq.run_once(app, T0 + timedelta(minutes=5))["waiting"] == "daily quota of the mail account used up"
    assert mailq.run_once(app, T0 + timedelta(minutes=61))["sent"] == 1 and server.sent == [EMAIL]


def test_the_outbox_counts_the_code_among_the_mails_to_one_person(server):
    from kts import mailq
    app = _app()
    _insert(app, "Code College", "Kerala", "Kochi", "accepted", None, coord_email=EMAIL)
    server.answer = smtplib.SMTPServerDisconnected("closed")
    _ask_for_the_code(app)
    _queue(app, "list@x.in", bulk=True)
    with app.app_context():
        f = mailq.figures(T0)
    assert (f["waiting_one"], f["waiting_list"]) == (1, 1)


def test_without_a_mail_server_the_code_waits_in_the_outbox():
    from conftest import make_app
    app = make_app(ADMIN_PASSWORD=None)
    _insert(app, "Code College", "Kerala", "Kochi", "accepted", None, coord_email=EMAIL)
    _ask_for_the_code(app)
    code = _codes(app)[0]
    assert code["status"] == "queued" and code["priority"] == -1 and code["next_try"] is None


def test_the_label_of_the_pause():
    from kts.admin import SETTING_GROUPS
    rows = {k: label for _g, items in SETTING_GROUPS for k, label, _kind in items}
    assert rows["mail.paused"] == ("Sending paused (new mails wait in the queue; the mail of the account of a Nodal Officer and, while "
                                   "they are mailed, the sign-in codes of the institutions go at once all the same)")      # 1.2.216

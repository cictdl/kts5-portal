"""
The outbox as a queue (version 1.2.35): mails go out in the background, within the limits of the mail
account, those to one person before those of lists, and a failure for a passing reason is tried again.

    python -m pytest tests -q
"""
import smtplib
from datetime import datetime, timedelta, timezone

import pytest

from conftest import make_app
from test_public_fixes import _staff

T0 = datetime(2026, 10, 15, 4, 0, tzinfo=timezone.utc)


class Server:
    """A mail server of the tests: it takes the mails, or answers as it is told to."""
    sent = []
    answer = None        # an exception for the next mails
    login_answer = None  # an exception for the sign-in
    logins = 0

    def __init__(self, host, port, timeout=None):
        pass

    def starttls(self):
        pass

    def login(self, user, password):
        Server.logins += 1
        if Server.login_answer:
            raise Server.login_answer

    def send_message(self, msg):
        if Server.answer:
            raise Server.answer
        Server.sent.append(msg["To"])

    def quit(self):
        pass


@pytest.fixture
def server(monkeypatch):
    Server.sent, Server.answer, Server.login_answer, Server.logins = [], None, None, 0
    monkeypatch.setattr(smtplib, "SMTP", Server)
    return Server


def _app(**limits):
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None, SMTP_HOST="smtp.gmail.com", SMTP_PORT=587, SMTP_USER="kts@cict.in",
                   SMTP_PASSWORD="x", SMTP_FROM="kts@cict.in")
    with app.app_context():
        for key, value in limits.items():
            set_setting("mail." + key, str(value))
    return app


def _queue(app, *addresses, bulk=False):
    from kts.utils import send_later, send_mail
    with app.test_request_context():
        if bulk:
            send_later([(a, "Stipend paid", "Body") for a in addresses])
        else:
            for a in addresses:
                send_mail(a, "Application received", "Body")


def _rows(app):
    from kts.db import query
    with app.app_context():
        return [dict(r) for r in query("SELECT * FROM outbox ORDER BY id")]


def test_a_mail_is_only_queued_by_the_page_and_sent_by_the_sender(server):
    from kts import mailq
    app = _app()
    _queue(app, "a@tests.example")
    assert server.sent == [] and _rows(app)[0]["status"] == "queued"
    assert mailq.run_once(app, T0)["sent"] == 1
    row = _rows(app)[0]
    assert server.sent == ["a@tests.example"] and row["status"] == "sent" and row["sent_at"]
    # the sender of the tests is not a thread: the tests call it
    assert "kts_mailq" not in app.extensions


def test_the_mails_to_one_person_go_before_those_of_a_list(server):
    from kts import mailq
    app = _app(per_minute=3)
    _queue(app, "l1@x.in", "l2@x.in", "l3@x.in", bulk=True)
    _queue(app, "p1@x.in", "p2@x.in")
    assert mailq.run_once(app, T0)["sent"] == 3
    assert server.sent == ["p1@x.in", "p2@x.in", "l1@x.in"]


def test_the_limits_of_a_minute_and_of_24_hours(server):
    from kts import mailq
    app = _app(per_minute=4, daily_limit=6)
    _queue(app, *[f"s{i}@x.in" for i in range(10)], bulk=True)
    real_now = mailq._now
    try:
        mailq._now = lambda: T0
        assert mailq.run_once(app, T0)["sent"] == 4
        # in the same minute nothing more
        assert mailq.run_once(app, T0 + timedelta(seconds=20)) == {"sent": 0, "failed": 0, "retry": 0, "waiting": "limit per minute"}
        mailq._now = lambda: T0 + timedelta(minutes=2)
        assert mailq.run_once(app, T0 + timedelta(minutes=2))["sent"] == 2
        mailq._now = lambda: T0 + timedelta(minutes=5)
        assert mailq.run_once(app, T0 + timedelta(minutes=5))["waiting"] == "daily limit"
        # a day after the first ones, room again
        mailq._now = lambda: T0 + timedelta(hours=24, minutes=3)
        assert mailq.run_once(app, T0 + timedelta(hours=24, minutes=3))["sent"] == 4
    finally:
        mailq._now = real_now
    assert len(server.sent) == 10


def test_a_passing_failure_is_tried_again_later_and_a_refusal_fails_at_once(server):
    from kts import mailq
    app = _app()
    _queue(app, "busy@x.in")
    server.answer = smtplib.SMTPResponseException(451, b"4.3.0 Mail server temporarily rejected message")
    assert mailq.run_once(app, T0)["retry"] == 1
    row = _rows(app)[0]
    assert row["status"] == "queued" and row["attempts"] == 1 and row["next_try"] > T0.isoformat()
    # not before its time
    assert mailq.run_once(app, T0 + timedelta(minutes=1))["sent"] == 0
    server.answer = None
    assert mailq.run_once(app, T0 + timedelta(minutes=3))["sent"] == 1
    # an address that does not exist: failed at once
    _queue(app, "nobody@x.in")
    server.answer = smtplib.SMTPRecipientsRefused({"nobody@x.in": (550, b"5.1.1 The email account does not exist")})
    assert mailq.run_once(app, T0 + timedelta(minutes=10))["failed"] == 1
    assert _rows(app)[1]["status"] == "failed" and "does not exist" in _rows(app)[1]["error"]


def test_five_tries_at_most(server):
    from kts import mailq
    app = _app()
    _queue(app, "flaky@x.in")
    server.answer = smtplib.SMTPResponseException(421, b"4.7.0 Try again later")
    moment = T0
    for _ in range(mailq.MAX_ATTEMPTS):
        mailq.run_once(app, moment)
        moment += timedelta(hours=1)
    row = _rows(app)[0]
    assert row["status"] == "failed" and row["attempts"] == mailq.MAX_ATTEMPTS


def test_the_daily_quota_of_google_pauses_the_sender(server):
    from kts import mailq
    app = _app()
    _queue(app, "a@x.in", "b@x.in", "c@x.in")
    server.answer = smtplib.SMTPDataError(550, b"5.4.5 Daily user sending quota exceeded.")
    result = mailq.run_once(app, T0)
    assert result["sent"] == 0 and result["waiting"] == "daily quota of the mail account used up"
    assert [r["status"] for r in _rows(app)] == ["queued"] * 3 and all(r["attempts"] == 0 for r in _rows(app))
    server.answer = None
    assert mailq.run_once(app, T0 + timedelta(minutes=30))["waiting"] == "daily quota of the mail account used up"
    assert mailq.run_once(app, T0 + timedelta(minutes=61))["sent"] == 3


def test_a_wrong_password_never_makes_the_mails_fail(server):
    from kts import mailq
    app = _app()
    _queue(app, "a@x.in")
    server.login_answer = smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
    for minutes in (0, 20, 40):
        mailq.run_once(app, T0 + timedelta(minutes=minutes))
    row = _rows(app)[0]
    assert row["status"] == "queued" and row["attempts"] == 0 and "Password not accepted" in row["error"]
    server.login_answer = None
    assert mailq.run_once(app, T0 + timedelta(minutes=60))["sent"] == 1


def test_a_claim_of_a_sender_that_stopped_goes_back_to_the_queue(server):
    from kts import mailq
    from kts.db import execute
    app = _app()
    _queue(app, "a@x.in")
    with app.app_context():
        execute("UPDATE outbox SET status = 'sending', next_try = ?", ((T0 - timedelta(minutes=30)).isoformat(),))
    assert mailq.run_once(app, T0)["sent"] == 1


def test_paused_and_without_a_mail_server(server):
    from kts import mailq
    app = _app(paused=1)
    _queue(app, "a@x.in")
    assert mailq.run_once(app, T0)["waiting"] == "paused" and server.sent == []
    plain = make_app(ADMIN_PASSWORD=None)
    assert mailq.run_once(plain, T0)["waiting"] == "mail is not configured"


def test_a_registration_does_not_wait_for_the_mail_server(server):
    from test_public_fixes import _register
    app = _app()
    app.config["RATE_REGISTER_PER_HOUR"] = 50
    assert _register(app, 1).status_code == 302
    assert server.sent == [] and server.logins == 0
    assert [r["status"] for r in _rows(app)] == ["queued"]


def test_the_console_shows_the_queue_and_pauses_it(server):
    app = _app()
    _queue(app, "a@x.in", "b@x.in", bulk=True)
    _queue(app, "c@x.in")
    admin = _staff(app, "admin@tests.example", "admin")
    page = admin.get("/console/outbox").get_data(as_text=True)
    assert "<b>1</b> to one person · <b>2</b> of lists" in page and "of at most 1800 in the last 24 hours" in page
    with admin.session_transaction() as s:
        token = s["_csrf"]
    page = admin.post("/console/outbox", data={"_csrf": token, "action": "pause"}, follow_redirects=True).get_data(as_text=True)
    assert "Sending is paused" in page and '<span class="pill kumkum">paused</span>' in page
    page = admin.post("/console/outbox", data={"_csrf": token, "action": "resume"}, follow_redirects=True).get_data(as_text=True)
    assert "Sending goes on." in page and '<span class="pill green">sending</span>' in page
    settings = admin.get("/console/settings").get_data(as_text=True)
    assert 'name="mail.daily_limit"' in settings and 'name="mail.per_minute"' in settings

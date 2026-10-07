"""
The mail outbox: a test message with the answer of the mail server, and the waiting messages sent again.

    python -m pytest tests -q
"""
import smtplib

import pytest

from conftest import make_app
from test_public_fixes import _staff


class FakeSMTP:
    """A mail server of the tests: it takes what is sent, or refuses the sign-in."""
    sent = []
    refuse = False

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        if FakeSMTP.refuse:
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")

    def send_message(self, msg):
        FakeSMTP.sent.append((msg["To"], msg["Subject"], msg["From"]))


@pytest.fixture
def server(monkeypatch):
    FakeSMTP.sent, FakeSMTP.refuse = [], False
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


def _post(client, **data):
    with client.session_transaction() as s:
        token = s["_csrf"]
    return client.post("/console/outbox", data={"_csrf": token, **data}, follow_redirects=True).get_data(as_text=True)


def test_a_test_message_through_the_mail_server(server):
    app = make_app(ADMIN_PASSWORD=None, SMTP_HOST="smtp.gmail.com", SMTP_PORT=587, SMTP_USER="kts@cict.in",
                   SMTP_PASSWORD="app-password-of-the-tests", SMTP_FROM="kts@cict.in")
    admin = _staff(app, "admin@tests.example", "admin")
    page = admin.get("/console/outbox").get_data(as_text=True)
    assert "<code>smtp.gmail.com</code> · port 587 · STARTTLS" in page and "<code>kts@cict.in</code>" in page
    # the password is never shown, only whether it is set
    assert "app-password-of-the-tests" not in page and 'password <span class="pill green">set</span>' in page
    assert 'value="admin@tests.example"' in page
    page = _post(admin, action="test", to="someone@cict.in")
    assert "The test message was sent to someone@cict.in." in page
    assert server.sent == [("someone@cict.in", "KTS 5.0 portal: test message", "kts@cict.in")]
    # a refused sign-in is reported with the words of the server
    server.refuse = True
    page = _post(admin, action="test", to="someone@cict.in")
    assert "The test message could not be sent:" in page and "Username and Password not accepted" in page
    assert "Enter the e-mail address" in _post(admin, action="test", to="not an address")


def test_the_waiting_messages_are_sent_again(server):
    app = make_app(ADMIN_PASSWORD=None, SMTP_HOST="smtp.gmail.com", SMTP_USER="kts@cict.in", SMTP_PASSWORD="x")
    from kts.db import execute, query, utcnow
    with app.app_context():
        for n, status in enumerate(("queued", "failed", "sent")):
            execute("INSERT INTO outbox(to_addr, subject, body, status, created_at) VALUES(?,?,?,?,?)",
                    (f"student{n}@tests.example", f"Subject {n}", "Body", status, utcnow()))
    admin = _staff(app, "admin@tests.example", "admin")
    assert "2 message(s) are waiting or failed" in admin.get("/console/outbox").get_data(as_text=True)
    import kts.admin as admin_module
    threads = []
    real = admin_module.send_again

    def keep(rows):
        threads.append(real(rows))
        return threads[-1]

    admin_module.send_again = keep
    try:
        page = _post(admin, action="again")
    finally:
        admin_module.send_again = real
    threads[0].join(10)
    assert "2 waiting or failed message(s) are being sent again" in page
    assert sorted(to for to, _s, _f in server.sent) == ["student0@tests.example", "student1@tests.example"]
    with app.app_context():
        assert [r["status"] for r in query("SELECT status FROM outbox ORDER BY id")] == ["sent", "sent", "sent"]


def test_without_mail_the_test_message_waits(server):
    app = make_app(ADMIN_PASSWORD=None)
    admin = _staff(app, "admin@tests.example", "admin")
    page = admin.get("/console/outbox").get_data(as_text=True)
    assert "Mail is not configured: every message waits" in page and "Send them again" not in page
    page = _post(admin, action="test", to="someone@cict.in")
    assert "Mail is not configured: the test message waits" in page and server.sent == []
    assert "Mail is not configured: nothing can be sent." in _post(admin, action="again")
    viewer = _staff(app, "viewer@tests.example", "viewer")
    assert viewer.get("/console/outbox").status_code == 403

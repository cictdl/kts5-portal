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


class FakeSocket:
    def close(self):
        pass


def test_the_check_of_the_connection_names_the_step_that_fails(server, monkeypatch):
    import socket
    open_ports = {587, 465}

    def connect(address, timeout=None):
        if address[1] not in open_ports:
            raise ConnectionRefusedError("refused")
        return FakeSocket()

    monkeypatch.setattr(socket, "create_connection", connect)
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, proto=0: [(2, 1, 6, "", ("142.250.4.108", port))])
    monkeypatch.setattr(FakeSMTP, "ehlo", lambda self: (250, b"smtp.gmail.com at your service"), raising=False)
    monkeypatch.setattr(FakeSMTP, "quit", lambda self: None, raising=False)
    monkeypatch.setattr(FakeSMTP, "starttls", lambda self: (220, b"Ready to start TLS"))
    # the sign-in in its three steps, as the check makes it: the server answers each command
    answers = {"AUTH": (334, b"VXNlcm5hbWU6")}
    sent = []

    def docmd(self, cmd, args=""):
        sent.append(cmd)
        if cmd == "AUTH":
            return answers["AUTH"]
        if len(sent) == 2:
            return 334, b"UGFzc3dvcmQ6"
        return answers.get("password", (235, b"2.7.0 Accepted"))

    monkeypatch.setattr(FakeSMTP, "docmd", docmd, raising=False)
    monkeypatch.setattr(FakeSMTP, "esmtp_features", {"auth": " LOGIN PLAIN XOAUTH2"}, raising=False)
    import kts.utils as utils
    monkeypatch.setattr(utils, "peer_certificate", lambda host, port=465, timeout=10: ("smtp.gmail.com", "Google Trust Services, WR2"))
    app = make_app(ADMIN_PASSWORD=None, SMTP_HOST="smtp.gmail.com", SMTP_PORT=587, SMTP_USER="kts@cict.in",
                   SMTP_PASSWORD="abcdefghijklmnop", SMTP_FROM="kts@cict.in")
    admin = _staff(app, "admin@tests.example", "admin")
    page = _post(admin, action="check")
    assert page.count('<span class="pill green">ok</span>') == 11 and "Sign-in, 3: the password" in page
    assert "issued by Google Trust Services" in page and "16 letters a–z" in page
    # the password itself is never on the page, not even encoded
    import base64
    assert "abcdefghijklmnop" not in page and base64.b64encode(b"abcdefghijklmnop").decode() not in page
    assert "142.250.4.108" in page
    # a refused password is told with the words of the server
    answers["password"] = (535, b"5.7.8 Username and Password not accepted")
    page = _post(admin, action="check")
    assert "Username and Password not accepted" in page and page.count('<span class="pill kumkum">failed</span>') == 1
    # a line cut at the password: the step says so
    def cut(self, cmd, args=""):
        if cmd == "AUTH":
            return 334, b"VXNlcm5hbWU6"
        raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")

    monkeypatch.setattr(FakeSMTP, "docmd", cut)
    page = _post(admin, action="check")
    assert "Sign-in, 2: the name kts@cict.in" in page and "SMTPServerDisconnected" in page
    # a certificate that is not Google's: something on the way opens the line
    monkeypatch.setattr(utils, "peer_certificate", lambda host, port=465, timeout=10: ("smtp.gmail.com", "Hosting Antivirus CA"))
    page = _post(admin, action="check")
    assert "not a certificate of Google" in page
    # the hosting company closes port 587: the check says so, and stops before the greeting
    open_ports.discard(587)
    page = _post(admin, action="check")
    assert "Reach port 587" in page and "ConnectionRefusedError" in page and "KTS_SMTP_PORT=465" in page


def test_the_form_of_the_password_is_described_never_the_password():
    from kts.utils import password_form
    assert password_form("abcdefghijklmnop") == (True, "16 letters a–z, the form of a Google app password")
    ok, words = password_form("abcd efgh ijkl mnop")
    assert not ok and "19 characters with spaces" in words and "abcd" not in words
    assert password_form("")[1] == "empty"
    assert "capital letters, digits, other characters" in password_form("Abc123!")[1]


def test_port_465_is_encrypted_from_the_start(server, monkeypatch):
    used = []

    class FakeSSL(FakeSMTP):
        def __init__(self, host, port, timeout=None):
            used.append(("ssl", port))

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSSL)
    app = make_app(ADMIN_PASSWORD=None, SMTP_HOST="smtp.gmail.com", SMTP_PORT=465, SMTP_USER="kts@cict.in",
                   SMTP_PASSWORD="x", SMTP_FROM="kts@cict.in")
    admin = _staff(app, "admin@tests.example", "admin")
    assert "The test message was sent to someone@cict.in." in _post(admin, action="test", to="someone@cict.in")
    assert used == [("ssl", 465)] and server.sent[-1][0] == "someone@cict.in"


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

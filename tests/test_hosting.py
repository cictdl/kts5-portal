"""
The hosting layer: the visitor's address behind the web server, the limits on sign-in attempts,
the first administrator, the settings file instance/portal.env, the headers and the error pages.

    python -m pytest tests -q

Every application built here works inside the temporary folder of tests/conftest.py. The
limiter belongs to the process, not to an application, so every test starts with an empty one.
"""
import http.client
import importlib.util
import json
import logging
import os
import re
import sqlite3
import stat
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode

import pytest
from markupsafe import escape

from conftest import ROOT, TMP, add_candidates, make_app

FIRST = "first@tests.example"
STAFF = "staff@tests.example"
AGENCY = "agency@tests.example"
STAFF_PASSWORD = "Staff-" + TMP.name[-8:] + "-4K"
NEW_PASSWORD = "Sangamam2026X"
APP_NO = "KTS5-2026-000001"
CANDIDATE = {"app_no": APP_NO, "dob": "2004-05-06", "last4": "3210"}
# the read-only attribute of Windows keeps a file from being removed; elsewhere the folder decides
on_windows = pytest.mark.skipif(os.name != "nt", reason="needs the read-only attribute of Windows")


@pytest.fixture(autouse=True)
def empty_limiter():
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


@pytest.fixture(scope="module")
def site():
    """An application of its own with low limits, two members of staff and one candidate."""
    app = make_app(ADMIN_EMAIL=FIRST, RATE_LOGIN_FAILS_PER_15MIN=5, RATE_CAND_FAILS_IP_PER_15MIN=8,
                   RATE_CAND_FAILS_APP_PER_15MIN=3)
    from werkzeug.security import generate_password_hash
    from kts.db import execute, query, utcnow
    with app.app_context():
        agency = query("SELECT id FROM agencies ORDER BY id LIMIT 1", one=True)["id"]
        for email, role, agency_id in ((STAFF, "admin", None), (AGENCY, "agency", agency)):
            execute("INSERT INTO users(email, name, password_hash, role, agency_id, active, must_change_password, created_at) "
                    "VALUES(?,?,?,?,?,1,0,?)",
                    (email, "Test " + role, generate_password_hash(STAFF_PASSWORD), role, agency_id, utcnow()))
        execute("INSERT INTO applications(app_no, full_name, gender, dob, mobile, email, state, college_name, college_key, "
                "pref_lang, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (APP_NO, "Test Student", "F", CANDIDATE["dob"], "9876543210", "student@tests.example", "Kerala",
                 "Government College Thrissur", "name:government thrissur|kerala", "hi", utcnow(), utcnow()))
    return app


def _token(client, path="/console/login"):
    client.get(path)
    with client.session_transaction() as s:
        return s["_csrf"]


def _staff(app, email, password, ip="198.51.100.20", client=None):
    """One sign-in attempt of the staff from this address, by a visitor who is not signed in."""
    client = client or app.test_client()
    return client.post("/console/login", data={"_csrf": _token(client), "email": email, "password": password},
                       environ_base={"REMOTE_ADDR": ip})


def _candidate(app, ip="198.51.100.30", **changed):
    client = app.test_client()
    form = dict(CANDIDATE, _csrf=_token(client, "/candidate/login"), **changed)
    return client.post("/candidate/login", data=form, environ_base={"REMOTE_ADDR": ip})


def _opens(response, target=None):
    """True when the sign-in was accepted (and led to `target`). A failing test prints no password."""
    return response.status_code == 302 and target in (None, response.headers["Location"])


def _says(response, text):
    return response.status_code == 200 and text.encode("utf-8") in response.data


TOO_MANY = "Too many sign-in attempts"
INCORRECT = "Incorrect email or password."


def _text(key, lang="en"):
    """The text of a key as it stands in a page."""
    from kts.i18n import CATALOG
    return str(escape(CATALOG[lang][key]))


def _rows(app, sql, args=()):
    conn = sqlite3.connect(str(app.config["DATABASE"]))
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


# ---- A1 · serve.py: the arguments for Waitress -------------------------------

SERVE_ENV = ("KTS_BEHIND_PROXY", "KTS_TRUSTED_PROXY", "KTS_HTTPS", "KTS_HOST", "KTS_THREADS", "KTS_PORT",
             "HTTP_PLATFORM_PORT", "ASPNETCORE_PORT", "PORT")


def test_server_options_without_a_proxy(monkeypatch):
    import serve
    for name in SERVE_ENV:
        monkeypatch.delenv(name, raising=False)
    options = serve.server_options()
    assert options == {"host": "0.0.0.0", "port": 8905, "threads": 8, "url_scheme": "http", "ident": None,
                       "clear_untrusted_proxy_headers": True}
    monkeypatch.setenv("KTS_HOST", "127.0.0.1")
    monkeypatch.setenv("KTS_THREADS", "16")
    monkeypatch.setenv("KTS_HTTPS", "1")
    monkeypatch.setenv("ASPNETCORE_PORT", "23456")
    # without KTS_BEHIND_PROXY the address of a proxy means nothing
    monkeypatch.setenv("KTS_TRUSTED_PROXY", "10.0.0.5")
    options = serve.server_options()
    assert options == {"host": "127.0.0.1", "port": 23456, "threads": 16, "url_scheme": "https", "ident": None,
                       "clear_untrusted_proxy_headers": True}
    # a number of threads that is none does not stop the portal
    monkeypatch.setenv("KTS_THREADS", "many")
    assert serve.server_options()["threads"] == 8


def test_server_options_behind_a_proxy(monkeypatch):
    import serve
    from waitress.adjustments import Adjustments
    for name in SERVE_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("KTS_BEHIND_PROXY", "1")
    options = serve.server_options()
    assert options["trusted_proxy"] == "127.0.0.1"
    assert options["trusted_proxy_count"] == 1
    # the address and nothing else: scheme and host name are not taken from a header
    assert options["trusted_proxy_headers"] == {"x-forwarded-for"}
    assert options["clear_untrusted_proxy_headers"] is True
    assert options["ident"] is None and options["url_scheme"] == "http"
    monkeypatch.setenv("KTS_TRUSTED_PROXY", "10.0.0.5")
    assert serve.server_options()["trusted_proxy"] == "10.0.0.5"
    # Waitress takes them as they are
    adj = Adjustments(**dict(options, host="127.0.0.1", port=0))
    assert adj.trusted_proxy == "127.0.0.1" and adj.trusted_proxy_headers == {"x-forwarded-for"}
    assert adj.ident is None and adj.clear_untrusted_proxy_headers is True
    # any other value of the switch is "off"
    monkeypatch.setenv("KTS_BEHIND_PROXY", "yes")
    assert "trusted_proxy" not in serve.server_options()


# ---- A1, A2, A3 · a real Waitress server on 127.0.0.1 --------------------------

@contextmanager
def _serving(**env):
    """
    The portal behind Waitress on a free port of 127.0.0.1, built with server_options() as
    serve.py does. Gives (application, port).
    """
    import serve
    from flask import request, url_for
    from waitress.server import create_server
    from kts.utils import client_ip

    app = make_app(ADMIN_EMAIL=FIRST, BEHIND_PROXY=env.get("KTS_BEHIND_PROXY") == "1")

    def seen():
        return {"client_ip": client_ip(), "remote_addr": request.remote_addr, "scheme": request.scheme,
                "host": request.host, "forwarded_for": request.headers.get("X-Forwarded-For"),
                "forwarded_host": request.headers.get("X-Forwarded-Host"),
                "forwarded_proto": request.headers.get("X-Forwarded-Proto"),
                "about": url_for("public.about", _external=True)}

    app.add_url_rule("/seen", "seen", seen)

    saved = {name: os.environ.get(name) for name in SERVE_ENV}
    try:
        for name in SERVE_ENV:
            os.environ.pop(name, None)
        os.environ.update(env)
        options = serve.server_options()
    finally:
        for name, value in saved.items():
            os.environ.pop(name, None)
            if value is not None:
                os.environ[name] = value
    options.update(host="127.0.0.1", port=0, threads=2)
    server = create_server(app, **options)

    def run():
        try:
            server.run()
        except OSError:
            pass  # the test has closed the listening socket

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        yield app, int(server.effective_port)
    finally:
        server.close()
        thread.join(5)
        server.task_dispatcher.shutdown()


def _http(port, method, path, headers=None, body=None):
    """(status, headers, text) of one request on a connection of its own."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    try:
        conn.request(method, path, body=body, headers=dict(headers or {}, Connection="close"))
        resp = conn.getresponse()
        return resp.status, resp, resp.read().decode("utf-8")
    finally:
        conn.close()


@pytest.fixture(scope="module")
def behind_iis():
    with _serving(KTS_BEHIND_PROXY="1") as (app, port):
        yield app, port


def _seen(port, **headers):
    status, _resp, text = _http(port, "GET", "/seen", {name.replace("_", "-"): value for name, value in headers.items()})
    assert status == 200, text[:300]
    return json.loads(text)


def test_visitor_address_behind_the_web_server(behind_iis):
    _app, port = behind_iis
    # the ASP.NET Core Module appends 'address:port' to what the visitor sent
    seen = _seen(port, X_Forwarded_For="203.0.113.9, 198.51.100.7:51234")
    assert seen["client_ip"] == "198.51.100.7" and seen["remote_addr"] == "198.51.100.7"
    # two visitors are two addresses
    assert _seen(port, X_Forwarded_For="192.0.2.44:40111")["client_ip"] == "192.0.2.44"
    # an address without port, as nginx writes it
    assert _seen(port, X_Forwarded_For="203.0.113.9, 192.0.2.45")["client_ip"] == "192.0.2.45"
    # IPv6: Waitress leaves '[address]:port' as it is, client_ip() takes the address out
    seen = _seen(port, X_Forwarded_For="203.0.113.9, [2001:db8::7]:40112")
    assert seen["client_ip"] == "2001:db8::7"
    # a request that did not come through the web server has the address of its connection
    assert _seen(port)["client_ip"] == "127.0.0.1"


def test_other_forwarding_headers_are_not_believed(behind_iis):
    _app, port = behind_iis
    seen = _seen(port, X_Forwarded_For="198.51.100.7:51234", X_Forwarded_Host="example.org", X_Forwarded_Proto="https",
                 X_Forwarded_Port="8443", X_Forwarded_Prefix="//example.org", Forwarded="for=203.0.113.9;host=example.org")
    assert seen["client_ip"] == "198.51.100.7"
    assert seen["forwarded_host"] is None and seen["forwarded_proto"] is None
    assert seen["host"] == f"127.0.0.1:{port}" and seen["scheme"] == "http"
    assert seen["about"] == f"http://127.0.0.1:{port}/about"


def test_forwarded_prefix_changes_no_address(behind_iis):
    _app, port = behind_iis
    sent = {"X-Forwarded-For": "198.51.100.7:51234", "X-Forwarded-Prefix": "//example.org"}
    status, _resp, page = _http(port, "GET", "/", sent)
    assert status == 200
    assert "example.org" not in page
    assert 'href="/static/css/portal.css' in page and 'action="/lang"' in page
    status, _resp, plain = _http(port, "GET", "/", {"X-Forwarded-For": "198.51.100.7:51234"})
    assert re.findall(r'(?:href|src|action)="([^"]*)"', page) == re.findall(r'(?:href|src|action)="([^"]*)"', plain)
    status, resp, _body = _http(port, "GET", "/candidate/", sent)
    assert status == 302 and resp.getheader("Location") == "/candidate/login"
    status, resp, _body = _http(port, "GET", "/lang/ta", dict(sent, **{"X-Forwarded-Prefix": "/x"}))
    assert status == 302 and resp.getheader("Location") == "/"


def test_no_server_header(behind_iis):
    _app, port = behind_iis
    for path in ("/", "/healthz", "/static/css/portal.css", "/no-such-page", "/console/logout"):
        _status, resp, _body = _http(port, "GET", path)
        assert resp.getheader("Server") is None, path
        assert "waitress" not in str(resp.getheaders()).lower(), path
        assert resp.getheader("X-Content-Type-Options") == "nosniff" or path.startswith("/static/"), path


def test_failed_sign_in_is_recorded_with_the_visitor_address(behind_iis):
    app, port = behind_iis
    sent = {"X-Forwarded-For": "203.0.113.9, 198.51.100.77:50001"}
    _status, resp, page = _http(port, "GET", "/console/login", sent)
    cookie = resp.getheader("Set-Cookie").split(";")[0]
    token = re.search(r'name="_csrf" value="([^"]+)"', page).group(1)
    form = urlencode({"_csrf": token, "email": "nobody@tests.example", "password": "wrong"})
    status, _resp, page = _http(port, "POST", "/console/login", body=form,
                                headers=dict(sent, Cookie=cookie, **{"Content-Type": "application/x-www-form-urlencoded"}))
    assert status == 200 and "Incorrect email or password." in page
    rows = _rows(app, "SELECT ip FROM audit_log WHERE action = 'login_failed' AND detail = 'nobody@tests.example'")
    assert rows == [("198.51.100.77",)]


def test_refused_forwarding_header_costs_a_short_line_of_the_log(behind_iis, caplog):
    _app, port = behind_iis
    # a quotation mark that is never closed, before the entry that the module appends
    sent = {"X-Forwarded-For": '"' + "x" * 15000 + ", 198.51.100.7:51234"}
    with caplog.at_level(logging.WARNING):
        status, _resp, text = _http(port, "GET", "/", sent)
    assert status == 400 and "X-Forwarded-For" in text
    lines = [record.getMessage() for record in caplog.records if record.name == "waitress"]
    assert len(lines) == 1
    assert lines[0].startswith('Malformed proxy header "X-Forwarded-For" from "127.0.0.1"')
    assert len(lines[0]) < 500 and lines[0].endswith("x" * 50 + "...")
    # the portal goes on, and an ordinary request writes nothing
    caplog.clear()
    assert _seen(port, X_Forwarded_For="198.51.100.7:51234")["client_ip"] == "198.51.100.7"
    assert [record for record in caplog.records if record.name.startswith("waitress")] == []


def test_long_arguments_are_cut_for_waitress_alone(caplog):
    import serve
    assert [type(f) for f in logging.getLogger("waitress").filters].count(serve._ShortArguments) == 1
    assert logging.getLogger("waitress.queue").filters == [] and logging.getLogger().filters == []
    long = "y" * 5000
    with caplog.at_level(logging.INFO):
        logging.getLogger("waitress").warning("%s | %s | %d", long, "short", 7)
        logging.getLogger("waitress").warning("%(name)s is %(value)s", {"name": "one dictionary", "value": long})
        logging.getLogger("waitress").warning("no arguments " + long)
        logging.getLogger("kts").warning("%s", long)
    assert [record.getMessage() for record in caplog.records] == [
        "y" * 200 + "... | short | 7", "one dictionary is " + long, "no arguments " + long, long]


def test_without_a_proxy_the_header_of_a_visitor_counts_for_nothing():
    with _serving() as (_app, port):
        seen = _seen(port, X_Forwarded_For="203.0.113.9", X_Forwarded_Host="example.org", X_Forwarded_Prefix="/x")
        assert seen["client_ip"] == "127.0.0.1" and seen["remote_addr"] == "127.0.0.1"
        assert seen["forwarded_for"] is None and seen["forwarded_host"] is None
        assert seen["about"] == f"http://127.0.0.1:{port}/about"
        _status, resp, _body = _http(port, "GET", "/")
        assert resp.getheader("Server") is None


def test_https_comes_from_the_setting():
    with _serving(KTS_BEHIND_PROXY="1", KTS_HTTPS="1") as (_app, port):
        # as the module passes it: the Host header of the visitor, unchanged
        seen = _seen(port, Host="kts.example", X_Forwarded_For="198.51.100.7:51234", X_Forwarded_Proto="http")
        assert seen["scheme"] == "https" and seen["about"] == "https://kts.example/about"


# ---- A2 · no ProxyFix, the path prefix stays ---------------------------------

def test_proxy_fix_is_gone():
    app = make_app(BEHIND_PROXY=True)
    assert type(app.wsgi_app).__name__ == "method"  # Flask's own wsgi_app, nothing around it
    sent = {"X-Forwarded-For": "203.0.113.9", "X-Forwarded-Host": "example.org", "X-Forwarded-Proto": "https",
            "X-Forwarded-Prefix": "//example.org"}
    client = app.test_client()
    page = client.get("/", headers=sent).data.decode("utf-8")
    assert "example.org" not in page
    assert client.get("/candidate/", headers=sent).headers["Location"] == "/candidate/login"


def test_url_prefix_still_works():
    app = make_app(URL_PREFIX="/kts5", ADMIN_EMAIL=FIRST)
    client = app.test_client()
    r = client.get("/kts5/about")
    assert r.status_code == 200 and 'href="/kts5/static/css/portal.css' in r.data.decode("utf-8")
    assert client.get("/kts5/about/").status_code == 200
    r = client.get("/about")
    assert r.status_code == 404 and b"/kts5/" in r.data
    # the page asked for before the sign-in keeps the prefix
    r = client.get("/kts5/console/audit?page=2")
    assert r.status_code == 302 and r.headers["Location"] == "/kts5/console/login"
    with client.session_transaction() as s:
        assert s["next"] == "/kts5/console/audit?page=2"


# ---- A3 · client_ip() ---------------------------------------------------------

@pytest.mark.parametrize("seen, address", [
    ("198.51.100.7", "198.51.100.7"),
    ("198.51.100.7:51234", "198.51.100.7"),
    (" 198.51.100.7 ", "198.51.100.7"),
    ("[2001:db8::7]:40112", "2001:db8::7"),
    ("[2001:db8::7]", "2001:db8::7"),
    ("2001:db8::7", "2001:db8::7"),
    ("2001:0DB8:0:0:0:0:0:7", "2001:db8::7"),
    ("::ffff:198.51.100.7", "198.51.100.7"),
    ("[::ffff:198.51.100.7]:40112", "198.51.100.7"),
    ("::1", "::1"),
    ("unknown", "unknown"),
    ("198.51.100.7:http", "198.51.100.7:http"),
    ("[2001:db8::7]x", "[2001:db8::7]x"),
    ("", ""),
    ("x" * 100, "x" * 64),
])
def test_client_ip(app, seen, address):
    from kts.utils import client_ip, plain_address
    assert plain_address(seen) == address
    # what a visitor writes into a header is never read
    sent = {"X-Forwarded-For": "203.0.113.9", "X-Real-IP": "203.0.113.9", "Forwarded": "for=203.0.113.9"}
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": seen}, headers=sent):
        assert client_ip() == address


def test_client_ip_without_an_address(app):
    from kts.utils import client_ip, plain_address
    assert plain_address(None) == ""
    with app.test_request_context("/", headers={"X-Forwarded-For": "203.0.113.9"}) as ctx:
        ctx.request.environ.pop("REMOTE_ADDR", None)
        assert client_ip() == ""


# ---- A4 · the limiter and its numbers -------------------------------------------

def _limiter():
    from kts.utils import RateLimiter
    now = [5000.0]
    return RateLimiter(clock=lambda: now[0]), now


def test_limiter_blocked_and_hit():
    lim, now = _limiter()
    # asking costs nothing
    for _ in range(50):
        assert lim.blocked("login", "198.51.100.7", 3, 900) is False
    assert lim._hits == {}
    for _ in range(3):
        assert lim.blocked("login", "198.51.100.7", 3, 900) is False
        lim.hit("login", "198.51.100.7", 900)
    assert lim.blocked("login", "198.51.100.7", 3, 900) is True
    # another address and another bucket have counters of their own
    assert lim.blocked("login", "198.51.100.8", 3, 900) is False
    assert lim.blocked("status", "198.51.100.7", 3, 900) is False
    # the window moves on
    now[0] += 600
    lim.hit("login", "198.51.100.7", 900)
    now[0] += 301
    assert lim.blocked("login", "198.51.100.7", 3, 900) is False   # three have left, one is inside
    lim.hit("login", "198.51.100.7", 900)
    lim.hit("login", "198.51.100.7", 900)
    assert lim.blocked("login", "198.51.100.7", 3, 900) is True


def test_limiter_allow_checks_and_counts():
    lim, now = _limiter()
    assert [lim.allow("register", "198.51.100.7", 5, 3600) for _ in range(7)] == [True] * 5 + [False] * 2
    assert lim.allow("register", "198.51.100.8", 5, 3600) is True
    # a refusal is not counted: after the hour the five are free again
    now[0] += 3601
    assert [lim.allow("register", "198.51.100.7", 5, 3600) for _ in range(6)] == [True] * 5 + [False]


def test_limiter_forgets_addresses():
    lim, now = _limiter()
    lim.hit("status", "198.51.100.7", 900)
    assert ("status", "198.51.100.7") in lim._hits
    now[0] += 901
    # a key whose queue became empty leaves the table
    assert lim.blocked("status", "198.51.100.7", 30, 900) is False
    assert lim._hits == {}
    assert lim.allow("status", "198.51.100.7", 30, 900) is True
    assert list(lim._hits) == [("status", "198.51.100.7")]
    # addresses that never come back are cleared away as well
    for n in range(500):
        lim.hit("register", f"203.0.113.{n}", 3600)
        lim.allow("contact", f"203.0.113.{n}", 10, 3600)
    assert len(lim._hits) == 1001
    now[0] += 1000
    lim.hit("status", "198.51.100.9", 900)
    assert len(lim._hits) == 1001                   # 'register' and 'contact' are still inside their hour
    now[0] += 2700
    lim.hit("status", "198.51.100.9", 900)
    assert list(lim._hits) == [("status", "198.51.100.9")]


def _config(monkeypatch, lines=None, raw=None, **env):
    """config.py read anew, as at a start of the portal, with its own folder and settings file."""
    folder = Path(tempfile.mkdtemp(prefix="env-", dir=TMP))
    if raw is not None:
        (folder / "portal.env").write_bytes(raw)
    elif lines is not None:
        (folder / "portal.env").write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setenv("KTS_INSTANCE_DIR", str(folder))
    monkeypatch.setenv("KTS_DATABASE", str(folder / "test.sqlite3"))
    monkeypatch.setenv("KTS_UPLOAD_DIR", str(folder / "uploads"))
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location("config_read_anew", ROOT / "config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.Config.DATABASE == folder / "test.sqlite3"
    return module.Config, folder


RATES = {"RATE_REGISTER_PER_HOUR": ("KTS_RATE_REGISTER_PER_HOUR", 100),
         "RATE_CONTACT_PER_HOUR": ("KTS_RATE_CONTACT_PER_HOUR", 10),
         "RATE_STATUS_FAILS_PER_15MIN": ("KTS_RATE_STATUS_FAILS", 300),
         "RATE_LOGIN_FAILS_PER_15MIN": ("KTS_RATE_LOGIN_FAILS", 12),
         "RATE_CAND_FAILS_IP_PER_15MIN": ("KTS_RATE_CANDIDATE_FAILS_IP", 600),
         "RATE_CAND_FAILS_APP_PER_15MIN": ("KTS_RATE_CANDIDATE_FAILS_APP", 6)}


def test_rate_defaults(monkeypatch, app):
    config, _folder = _config(monkeypatch)
    for attribute, (_name, default) in RATES.items():
        assert getattr(config, attribute) == default, attribute
        assert app.config[attribute] == default, attribute
    assert config.TRUSTED_PROXY == "127.0.0.1" and config.HSTS is False and config.BEHIND_PROXY is False


def test_rates_from_the_environment(monkeypatch):
    env = {name: str(default * 3) for name, default in RATES.values()}
    config, _folder = _config(monkeypatch, KTS_TRUSTED_PROXY="10.0.0.5", KTS_HSTS="1", **env)
    for attribute, (_name, default) in RATES.items():
        assert getattr(config, attribute) == default * 3, attribute
    assert config.TRUSTED_PROXY == "10.0.0.5" and config.HSTS is True


@pytest.mark.parametrize("value", ["abc", "0", "-3", "1.5", " ", "12 per hour", "٣", "1234567890", "7" * 5000],
                         ids=lambda value: value[:12])
def test_a_rate_that_is_no_number_gives_the_default(monkeypatch, value):
    env = {name: value for name, _default in RATES.values()}
    config, _folder = _config(monkeypatch, KTS_SMTP_PORT=value, **env)
    for attribute, (_name, default) in RATES.items():
        assert getattr(config, attribute) == default, attribute
    assert config.SMTP_PORT == 587
    # each of them is named once; a value of spaces is no value
    named = sorted(["KTS_SMTP_PORT"] + [name for name, _default in RATES.values()]) if value.strip() else []
    assert sorted(config.SETTINGS_UNUSABLE) == named


def test_a_rate_has_nine_digits_at_most(monkeypatch):
    config, _folder = _config(monkeypatch, KTS_RATE_LOGIN_FAILS="123456789", KTS_RATE_STATUS_FAILS="0000000040")
    assert config.RATE_LOGIN_FAILS_PER_15MIN == 123456789
    # ten digits, whatever their value
    assert config.RATE_STATUS_FAILS_PER_15MIN == 300
    # Python refuses to read a number of more than 4300 digits: the portal must start all the same
    monkeypatch.delenv("KTS_RATE_LOGIN_FAILS")
    lines = ["KTS_RATE_LOGIN_FAILS=" + "9" * 5000, "KTS_SMTP_PORT=" + "1" * 4301]
    config, _folder = _config(monkeypatch, lines=lines)
    assert config.RATE_LOGIN_FAILS_PER_15MIN == 12 and config.SMTP_PORT == 587
    import serve
    monkeypatch.setenv("KTS_THREADS", "8" * 4400)
    assert serve.server_options()["threads"] == 8


# ---- A5 · sign-in of the staff -------------------------------------------------

def test_correct_staff_sign_ins_are_never_refused(site):
    for n in range(20):
        r = _staff(site, STAFF, STAFF_PASSWORD)
        assert _opens(r, "/console/"), n


def test_wrong_staff_sign_ins_are_refused_after_the_limit(site):
    limit = site.config["RATE_LOGIN_FAILS_PER_15MIN"]
    assert limit == 5
    for n in range(limit):
        # correct sign-ins between the wrong ones cost nothing
        r = _staff(site, STAFF, STAFF_PASSWORD)
        assert _opens(r), n
        r = _staff(site, STAFF if n % 2 else "nobody@tests.example", "wrong-password")
        assert _says(r, INCORRECT), n
    r = _staff(site, STAFF, "wrong-password")
    assert _says(r, TOO_MANY)
    # now the address is closed, also for the right password
    r = _staff(site, STAFF, STAFF_PASSWORD)
    assert _says(r, TOO_MANY)
    # a refused attempt is not counted and not recorded as a failure
    failed = _rows(site, "SELECT COUNT(*) FROM audit_log WHERE action = 'login_failed' AND ip = '198.51.100.20'")
    assert failed == [(limit,)]
    # another address is not concerned
    r = _staff(site, STAFF, STAFF_PASSWORD, ip="198.51.100.21")
    assert _opens(r)
    r = _staff(site, STAFF, "wrong-password", ip="198.51.100.21")
    assert _says(r, INCORRECT)


def test_the_limit_is_kept_for_fifteen_minutes(site, monkeypatch):
    from kts.utils import limiter
    start = limiter._clock()
    for _ in range(5):
        _staff(site, STAFF, "wrong-password")
    r = _staff(site, STAFF, STAFF_PASSWORD)
    assert _says(r, TOO_MANY)
    monkeypatch.setattr(limiter, "_clock", lambda: start + 899)
    r = _staff(site, STAFF, STAFF_PASSWORD)
    assert _says(r, TOO_MANY)
    monkeypatch.setattr(limiter, "_clock", lambda: start + 902)
    r = _staff(site, STAFF, STAFF_PASSWORD)
    assert _opens(r)


def _asked_then_signed_in(site, asked, email=STAFF, password=STAFF_PASSWORD, stored=None):
    client = site.test_client()
    r = client.get(asked)
    assert r.status_code == 302 and r.headers["Location"] == "/console/login"
    if stored is not None:
        with client.session_transaction() as s:
            s["next"] = stored
    r = _staff(site, email, password, client=client)
    assert _opens(r)
    with client.session_transaction() as s:
        assert "next" not in s and s["uid"]
    return r.headers["Location"]


@pytest.mark.parametrize("asked", ["/console/audit", "/console/applications?status=verified&page=2", "/hub/tasks",
                                   "/console/applications/"])
def test_sign_in_leads_to_the_page_asked_for(site, asked):
    assert _asked_then_signed_in(site, asked) == asked


@pytest.mark.parametrize("stored", ["//example.org/console", "/\\example.org", "https://example.org/", "example.org",
                                    "/\t/example.org", "", "javascript:alert(1)", 7])
def test_sign_in_leads_nowhere_else(site, stored):
    assert _asked_then_signed_in(site, "/console/audit", stored=stored) == "/console/"


def test_page_asked_for_is_not_used_for_everybody(site):
    # the agencies have their own entrance
    target = _asked_then_signed_in(site, "/console/audit", email=AGENCY)
    assert target == "/hub/"
    # who must change the password goes there first
    target = _asked_then_signed_in(site, "/console/audit", email=FIRST, password=os.environ["KTS_ADMIN_PASSWORD"])
    assert target == "/console/password"


def test_local_path():
    from kts.auth import _local_path
    assert _local_path("/console/audit") and _local_path("/kts5/console/applications?page=2")
    for value in (None, "", "console", "//example.org", "/\\example.org", "http://example.org", "/\n/example.org"):
        assert not _local_path(value), value


# ---- A6 · sign-in of the candidates ---------------------------------------------

def test_correct_candidate_sign_ins_are_never_refused(site):
    for n in range(20):
        r = _candidate(site)
        assert _opens(r, "/candidate/"), n
    # the application number may be typed in small letters
    r = _candidate(site, app_no=APP_NO.lower())
    assert _opens(r, "/candidate/")


def test_candidate_limit_per_number_and_address(site):
    limit = site.config["RATE_CAND_FAILS_APP_PER_15MIN"]
    assert limit == 3 and site.config["RATE_CAND_FAILS_IP_PER_15MIN"] == 8
    for n in range(limit):
        # small letters and capitals are one number
        r = _candidate(site, ip="198.51.100.40", last4="0000", app_no=APP_NO.lower() if n else APP_NO)
        assert _says(r, _text("status.not_found")), n
    # the number is closed for this address, also with the right details
    for app_no in (APP_NO, APP_NO.lower()):
        r = _candidate(site, ip="198.51.100.40", app_no=app_no)
        assert _says(r, _text("reg.err_rate")), app_no
    # and for this address only: nobody closes the sign-in of a candidate who is elsewhere
    r = _candidate(site, ip="198.51.100.99")
    assert _opens(r, "/candidate/")
    # another number from the same address is answered
    r = _candidate(site, ip="198.51.100.40", app_no="KTS5-2026-000002")
    assert _says(r, _text("status.not_found"))
    # a refused attempt is not recorded as a failure
    assert _rows(site, "SELECT COUNT(*) FROM audit_log WHERE action = 'candidate_login_failed' AND detail = ?",
                 (APP_NO,)) == [(limit,)]


def test_wrong_attempts_from_many_addresses_close_nothing(site):
    # application numbers are consecutive: whoever knows one knows them all
    for n in range(20):
        r = _candidate(site, ip=f"203.0.113.{n}", last4="0000")
        assert _says(r, _text("status.not_found")), n
    r = _candidate(site, ip="198.51.100.45")
    assert _opens(r, "/candidate/")


def test_candidate_limit_per_address(site):
    limit = site.config["RATE_CAND_FAILS_IP_PER_15MIN"]
    for n in range(limit):
        # a classmate at the same address signs in meanwhile
        r = _candidate(site, ip="198.51.100.50")
        assert _opens(r), n
        r = _candidate(site, ip="198.51.100.50", app_no=f"KTS5-2026-9{n:05d}")
        assert _says(r, _text("status.not_found")), n
    r = _candidate(site, ip="198.51.100.50")
    assert _says(r, _text("reg.err_rate"))
    r = _candidate(site, ip="198.51.100.51")
    assert _opens(r)


def test_candidate_key_is_cut_to_32_characters(site):
    from kts.utils import limiter
    long_number = "k" * 40
    _candidate(site, ip="198.51.100.60", app_no=long_number)
    assert sorted(limiter._hits) == [("cand_app", "K" * 32 + "|198.51.100.60"), ("cand_login", "198.51.100.60")]


def test_failed_sign_ins_are_recorded_cut(site):
    # what was typed may have any length up to the limit of a form
    r = _candidate(site, ip="198.51.100.61", app_no="kts5-" + "9" * 5000)
    assert _says(r, _text("status.not_found"))
    assert _rows(site, "SELECT detail FROM audit_log WHERE action = 'candidate_login_failed' AND ip = '198.51.100.61'") \
        == [("KTS5-" + "9" * 27,)]
    r = _staff(site, "A" * 5000 + "@tests.example", "wrong-password", ip="198.51.100.62")
    assert _says(r, INCORRECT)
    assert _rows(site, "SELECT detail FROM audit_log WHERE action = 'login_failed' AND ip = '198.51.100.62'") \
        == [("a" * 254,)]
    # an address and a number of the usual length are recorded as they are
    _staff(site, "nobody@tests.example", "wrong-password", ip="198.51.100.63")
    _candidate(site, ip="198.51.100.63", last4="0000", app_no="KTS5-2026-000002")
    assert _rows(site, "SELECT action, detail FROM audit_log WHERE ip = '198.51.100.63' ORDER BY id") \
        == [("login_failed", "nobody@tests.example"), ("candidate_login_failed", "KTS5-2026-000002")]


# ---- A6 · a campus behind one address, with the limits as they are delivered ------------------

@pytest.fixture(scope="module")
def campus():
    """An application with the limits of config.py and 90 candidates, the students of one campus."""
    app = make_app(ADMIN_EMAIL=FIRST)
    return app, add_candidates(app, 90)


def _student(app, student, ip, **changed):
    client = app.test_client()
    form = dict(student, _csrf=_token(client, "/candidate/login"), **changed)
    return client.post("/candidate/login", data=form, environ_base={"REMOTE_ADDR": ip})


def _status(app, student, ip, **changed):
    client = app.test_client()
    form = dict(student, _csrf=_token(client, "/status"), **changed)
    return client.post("/status", data=form, environ_base={"REMOTE_ADDR": ip})


def _wrong(student):
    """The last four digits, mistyped."""
    return f"{(int(student['last4']) + 1) % 10000:04d}"


def test_limits_as_delivered(campus):
    app, _students = campus
    assert app.config["RATE_CAND_FAILS_IP_PER_15MIN"] == 600 and app.config["RATE_STATUS_FAILS_PER_15MIN"] == 300
    assert app.config["RATE_CAND_FAILS_APP_PER_15MIN"] == 6


def test_a_campus_signs_in_through_one_address(campus):
    app, students = campus
    from kts.utils import limiter
    for student in students:
        r = _student(app, student, "203.0.113.50", last4=_wrong(student))
        assert _says(r, _text("status.not_found")), student["app_no"]
        r = _student(app, student, "203.0.113.50")
        assert _opens(r, "/candidate/"), student["app_no"]
    assert len(limiter._hits[("cand_login", "203.0.113.50")][1]) == 90


def test_six_wrong_attempts_close_a_number_for_their_address(campus):
    app, students = campus
    victim, classmate = students[0], students[1]
    for n in range(6):
        r = _student(app, victim, "203.0.113.60", last4=f"9{n:03d}")
        assert _says(r, _text("status.not_found")), n
    # the seventh from this address, wrong or right
    for last4 in ("9006", victim["last4"]):
        r = _student(app, victim, "203.0.113.60", last4=last4)
        assert _says(r, _text("reg.err_rate")), last4
    # the candidate himself, at another address
    r = _student(app, victim, "203.0.113.61")
    assert _opens(r, "/candidate/")
    # a classmate at the address of the six attempts
    r = _student(app, classmate, "203.0.113.60")
    assert _opens(r, "/candidate/")
    assert _rows(app, "SELECT COUNT(*) FROM audit_log WHERE action = 'candidate_login_failed' AND detail = ? "
                      "AND ip = '203.0.113.60'", (victim["app_no"],)) == [(6,)]


def test_a_campus_looks_up_its_status_through_one_address(campus):
    app, students = campus
    from kts.utils import limiter
    for n, student in enumerate(students, start=1):
        r = _status(app, student, "203.0.113.70", last4=_wrong(student))
        assert _says(r, _text("status.not_found")), student["app_no"]
        r = _status(app, student, "203.0.113.70")
        assert _says(r, f"Campus Student {n}<"), student["app_no"]
    assert len(limiter._hits[("status", "203.0.113.70")][1]) == 90


def test_six_wrong_look_ups_close_a_number_for_their_address(campus):
    app, students = campus
    victim, classmate = students[0], students[1]
    for n in range(6):
        r = _status(app, victim, "203.0.113.80", last4=f"9{n:03d}")
        assert _says(r, _text("status.not_found")), n
    for last4 in ("9006", victim["last4"]):
        r = _status(app, victim, "203.0.113.80", last4=last4)
        assert _says(r, _text("reg.err_rate")) and b"Campus Student" not in r.data, last4
    r = _status(app, victim, "203.0.113.81")
    assert _says(r, "Campus Student 1<")
    r = _status(app, classmate, "203.0.113.80")
    assert _says(r, "Campus Student 2<")


def test_mistakes_on_the_status_page_do_not_close_the_sign_in(campus):
    app, students = campus
    from kts.utils import limiter
    student = students[2]
    for n in range(6):
        r = _status(app, student, "203.0.113.90", last4=f"9{n:03d}")
        assert _says(r, _text("status.not_found")), n
    r = _status(app, student, "203.0.113.90")
    assert _says(r, _text("reg.err_rate"))
    # the page has a counter of its own
    assert sorted(limiter._hits) == [("status", "203.0.113.90"), ("status_app", student["app_no"] + "|203.0.113.90")]
    r = _student(app, student, "203.0.113.90")
    assert _opens(r, "/candidate/")
    # and the other way round
    for n in range(6):
        _student(app, student, "203.0.113.91", last4=f"9{n:03d}")
    r = _student(app, student, "203.0.113.91")
    assert _says(r, _text("reg.err_rate"))
    r = _status(app, student, "203.0.113.91")
    assert _says(r, "Campus Student 3<")


def test_status_limit_per_address_still_holds():
    own = make_app(RATE_STATUS_FAILS_PER_15MIN=8)
    student = add_candidates(own, 1)[0]
    for n in range(8):
        # another number each time, so that the limit per number is not the one that refuses
        r = _status(own, student, "203.0.113.95", app_no=f"KTS5-2026-9{n:05d}")
        assert _says(r, _text("status.not_found")), n
    r = _status(own, student, "203.0.113.95")
    assert _says(r, _text("reg.err_rate"))
    r = _status(own, student, "203.0.113.96")
    assert _says(r, "Campus Student 1<")


# ---- A7 · the first administrator -----------------------------------------------

def _first_admin_file(app):
    return Path(app.config["INSTANCE_DIR"]) / "first-admin.txt"


def _restart(app, **settings):
    """The portal started again on the same database and the same folders."""
    values = {name: app.config[name] for name in ("INSTANCE_DIR", "DATABASE", "UPLOAD_DIR", "ADMIN_EMAIL", "BASE_URL")}
    values.update(settings)
    return make_app(**values)


def _give_retired_password(app, email, must_change=1, active=1):
    from werkzeug.security import generate_password_hash
    from kts.db import RETIRED_FIRST_PASSWORD, execute
    with app.app_context():
        execute("UPDATE users SET password_hash = ?, must_change_password = ?, active = ? WHERE email = ?",
                (generate_password_hash(RETIRED_FIRST_PASSWORD), must_change, active, email))


def _retired_password_opens(app, email=FIRST):
    from kts.db import RETIRED_FIRST_PASSWORD
    return _opens(_staff(app, email, RETIRED_FIRST_PASSWORD))


def _password_opens(app, email, password, target=None):
    return _opens(_staff(app, email, password), target)


def test_first_administrator_gets_a_password_of_his_own(caplog):
    from kts import db
    with caplog.at_level(logging.WARNING):
        app = make_app(ADMIN_PASSWORD=None, ADMIN_EMAIL="First@Tests.Example", BASE_URL="https://portal.example/")
    path = _first_admin_file(app)
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    assert raw.endswith(b"\r\n") and b"\n" not in raw.replace(b"\r\n", b"")
    assert "Sign-in page: https://portal.example/console/login\r\n" in text
    assert "asks for a new password at once" in text and "removes this file" in text
    accounts = db.read_first_admin(app)
    assert [email for email, _password in accounts] == [FIRST]
    password = accounts[0][1]
    assert len(password) == 16 and set(password) <= set(db.PASSWORD_LETTERS)
    assert not set(db.PASSWORD_LETTERS) & set("0O1lI")
    known = password in (db.RETIRED_FIRST_PASSWORD, os.environ["KTS_ADMIN_PASSWORD"])
    assert not known
    # the log names the file, never the password
    logged = password in caplog.text
    assert str(path) in caplog.text and not logged
    # the account: first administrator, must set a new password
    assert _rows(app, "SELECT email, role, active, must_change_password FROM users") == [(FIRST, "superadmin", 1, 1)]
    assert not _retired_password_opens(app)
    opened = _password_opens(app, FIRST, password, "/console/password")
    assert opened
    # the next start changes nothing
    again = _restart(app, ADMIN_PASSWORD=None)
    unchanged = _first_admin_file(again).read_bytes() == raw
    opened = _password_opens(again, FIRST, password)
    assert unchanged and opened


def test_generated_passwords_differ():
    from kts import db
    words = {db.new_password() for _ in range(200)}
    assert len(words) == 200
    for word in words:
        assert len(word) == 16 and set(word) <= set(db.PASSWORD_LETTERS)
        assert any(c.isupper() for c in word) and any(c.islower() for c in word) and any(c.isdigit() for c in word)


def test_no_file_when_the_password_is_configured(app, caplog):
    configured = "Configured-" + TMP.name[-8:] + "-9Z"
    with caplog.at_level(logging.WARNING):
        own = make_app(ADMIN_PASSWORD=configured, ADMIN_EMAIL=FIRST)
    assert not _first_admin_file(own).exists()
    logged = configured in caplog.text
    assert "KTS_ADMIN_PASSWORD" in caplog.text and not logged
    opened = _password_opens(own, FIRST, configured, "/console/password")
    assert opened
    # the application of the other tests has its password from the environment
    assert not _first_admin_file(app).exists()


def test_the_retired_password_cannot_be_configured():
    from kts.db import RETIRED_FIRST_PASSWORD
    own = make_app(ADMIN_PASSWORD=RETIRED_FIRST_PASSWORD, ADMIN_EMAIL=FIRST)
    assert _first_admin_file(own).exists()
    assert not _retired_password_opens(own)


def test_rotation_of_the_retired_password(caplog):
    from kts import db
    app = make_app(ADMIN_EMAIL=FIRST)
    _give_retired_password(app, FIRST)
    assert _retired_password_opens(app)
    # with a configured password nothing is rotated
    again = _restart(app)
    assert again.config["ADMIN_PASSWORD"] == os.environ["KTS_ADMIN_PASSWORD"]
    assert not _first_admin_file(again).exists() and _retired_password_opens(again)
    assert _rows(again, "SELECT COUNT(*) FROM audit_log WHERE action = 'first_password_rotated'") == [(0,)]
    # without one the account receives a new password
    with caplog.at_level(logging.WARNING):
        again = _restart(app, ADMIN_PASSWORD=None)
    assert not _retired_password_opens(again)
    accounts = db.read_first_admin(again)
    assert [email for email, _password in accounts] == [FIRST]
    password = accounts[0][1]
    logged = password in caplog.text
    assert str(_first_admin_file(again)) in caplog.text and not logged
    user_id = _rows(again, "SELECT id FROM users WHERE email = ?", (FIRST,))[0][0]
    assert _rows(again, "SELECT actor, entity, entity_id, detail FROM audit_log WHERE action = 'first_password_rotated'") \
        == [("portal", "user", user_id, FIRST)]
    assert _rows(again, "SELECT must_change_password FROM users WHERE email = ?", (FIRST,)) == [(1,)]
    opened = _password_opens(again, FIRST, password, "/console/password")
    assert opened
    # once only
    before = _first_admin_file(again).read_bytes()
    third = _restart(app, ADMIN_PASSWORD=None)
    unchanged = _first_admin_file(third).read_bytes() == before
    assert unchanged
    assert _rows(third, "SELECT COUNT(*) FROM audit_log WHERE action = 'first_password_rotated'") == [(1,)]


@pytest.mark.parametrize("must_change, active", [(1, 0), (0, 0)])
def test_no_rotation_of_other_accounts(must_change, active):
    # an account that is not active cannot sign in
    app = make_app(ADMIN_EMAIL=FIRST)
    _give_retired_password(app, FIRST, must_change=must_change, active=active)
    from werkzeug.security import check_password_hash
    from kts.db import RETIRED_FIRST_PASSWORD
    again = _restart(app, ADMIN_PASSWORD=None)
    assert not _first_admin_file(again).exists()
    assert _rows(again, "SELECT COUNT(*) FROM audit_log WHERE action = 'first_password_rotated'") == [(0,)]
    unchanged = check_password_hash(_rows(again, "SELECT password_hash FROM users WHERE email = ?", (FIRST,))[0][0],
                                    RETIRED_FIRST_PASSWORD)
    assert unchanged
    assert _rows(again, "SELECT must_change_password FROM users WHERE email = ?", (FIRST,)) == [(must_change,)]


CHECKED = "SELECT value FROM settings WHERE key = 'security.first_passwords_checked'"


def test_rotation_of_a_password_kept_in_the_change_form(caplog):
    # The change form of earlier versions accepted the password of before: the account has the
    # published password and need not change it.
    from kts import db
    app = make_app(ADMIN_EMAIL=FIRST)
    _give_retired_password(app, FIRST, must_change=0)
    opened = _retired_password_opens(app)
    assert opened and _rows(app, CHECKED) == []
    with caplog.at_level(logging.WARNING):
        again = _restart(app, ADMIN_PASSWORD=None)
    assert not _retired_password_opens(again)
    accounts = db.read_first_admin(again)
    assert [email for email, _password in accounts] == [FIRST]
    password = accounts[0][1]
    logged = password in caplog.text
    assert str(_first_admin_file(again)) in caplog.text and not logged
    user_id = _rows(again, "SELECT id FROM users WHERE email = ?", (FIRST,))[0][0]
    assert _rows(again, "SELECT actor, entity, entity_id, detail FROM audit_log WHERE action = 'first_password_rotated'") \
        == [("portal", "user", user_id, FIRST)]
    # the account must set a password of its own, as the file says
    assert _rows(again, "SELECT must_change_password FROM users WHERE email = ?", (FIRST,)) == [(1,)]
    opened = _password_opens(again, FIRST, password, "/console/password")
    assert opened
    assert _rows(again, CHECKED) == [("1",)]
    # once only, and the file stays until the password has been changed
    before = _first_admin_file(again).read_bytes()
    third = _restart(app, ADMIN_PASSWORD=None)
    unchanged = _first_admin_file(third).read_bytes() == before
    opened = _password_opens(third, FIRST, password, "/console/password")
    assert unchanged and opened
    assert _rows(third, "SELECT COUNT(*) FROM audit_log WHERE action = 'first_password_rotated'") == [(1,)]
    assert _rows(third, CHECKED) == [("1",)]


def test_every_account_is_compared_once_for_each_database(monkeypatch):
    from werkzeug.security import generate_password_hash
    from kts import db
    app = make_app(ADMIN_EMAIL=FIRST)
    # 60 members of staff who have set a password of their own; a hash that is quickly compared
    with app.app_context():
        db.executemany("INSERT INTO users(email, name, password_hash, role, active, must_change_password, created_at) "
                       "VALUES(?,?,?,?,1,0,?)",
                       [(f"staff{n}@tests.example", f"Staff {n}", generate_password_hash(f"Chosen-{n}-By-Its-Owner",
                                                                                          method="pbkdf2:sha256:1000"),
                         "viewer", db.utcnow()) for n in range(60)])
    # and the administrator, who kept the published password in the change form
    _give_retired_password(app, FIRST, must_change=0)
    settled = {row[0] for row in _rows(app, "SELECT password_hash FROM users WHERE email != ?", (FIRST,))}
    assert len(settled) == 60

    compared = []

    def counted(pwhash, password):
        compared.append(pwhash)
        return compare(pwhash, password)

    compare = db.check_password_hash
    monkeypatch.setattr(db, "check_password_hash", counted)
    # a start with a configured password compares nothing and leaves the question open
    _restart(app)
    assert compared == [] and _rows(app, CHECKED) == []
    # the first start that looks: every active account
    first = _restart(app, ADMIN_PASSWORD=None)
    everybody = settled < set(compared)
    assert len(compared) == 61 and everybody
    assert [email for email, _password in db.read_first_admin(first)] == [FIRST]
    assert _rows(first, CHECKED) == [("1",)]
    # the second start: no account that need not change its password
    compared.clear()
    second = _restart(app, ADMIN_PASSWORD=None)
    waiting = {row[0] for row in _rows(second, "SELECT password_hash FROM users WHERE must_change_password = 1")}
    only_the_waiting = set(compared) == waiting and not set(compared) & settled
    assert len(waiting) == 1 and len(compared) > 0 and only_the_waiting
    assert _rows(second, "SELECT COUNT(*) FROM users WHERE active = 1 AND must_change_password = 0") == [(60,)]
    assert _rows(second, "SELECT COUNT(*) FROM audit_log WHERE action = 'first_password_rotated'") == [(1,)]


@pytest.mark.parametrize("stored", ["x", "", "plain$salt$hash", "sha256$salt$hash", "$$", "scrypt:3:8:1$salt$hash",
                                    "pbkdf2:sha256:many$salt$hash", "pbkdf2:nothing:1000$salt$hash"])
def test_a_hash_that_cannot_be_compared_does_not_stop_the_start(stored):
    # an account written into the database by other means; every active account is compared
    from kts import db
    app = make_app(ADMIN_EMAIL=FIRST)
    with app.app_context():
        db.execute("INSERT INTO users(email, name, password_hash, role, active, must_change_password, created_at) "
                   "VALUES(?,?,?,?,1,0,?)", (STAFF, "Staff", stored, "viewer", db.utcnow()))
    _give_retired_password(app, FIRST, must_change=0)
    again = _restart(app, ADMIN_PASSWORD=None)
    assert again.test_client().get("/healthz").get_json()["ok"] is True
    # that account is as it was, the other one has received its new password
    assert _rows(again, "SELECT password_hash, must_change_password FROM users WHERE email = ?", (STAFF,)) == [(stored, 0)]
    assert [email for email, _password in db.read_first_admin(again)] == [FIRST]
    assert not _retired_password_opens(again)
    assert _rows(again, CHECKED) == [("1",)]
    # the same for an account that awaits its first sign-in, at the starts that follow
    with again.app_context():
        db.execute("UPDATE users SET must_change_password = 1 WHERE email = ?", (STAFF,))
    db.write_first_admin(again, db.read_first_admin(again) + [(STAFF, "not-a-real-password")])
    third = _restart(app, ADMIN_PASSWORD=None)
    assert [email for email, _password in db.read_first_admin(third)] == [FIRST]


def test_rotation_reaches_every_account_that_has_the_retired_password():
    from kts import db
    app = make_app(ADMIN_EMAIL=FIRST)
    with app.app_context():
        db.execute("INSERT INTO users(email, name, password_hash, role, active, must_change_password, created_at) "
                   "VALUES(?,?,?,?,1,1,?)", (STAFF, "Staff", "x", "admin", db.utcnow()))
    _give_retired_password(app, FIRST)
    _give_retired_password(app, STAFF)
    again = _restart(app, ADMIN_PASSWORD=None)
    accounts = dict(db.read_first_admin(again))
    different = accounts[FIRST] != accounts[STAFF]
    assert set(accounts) == {FIRST, STAFF} and different
    for email in accounts:
        assert not _retired_password_opens(again, email), email
        opened = _password_opens(again, email, accounts[email])
        assert opened, email
    # the first of them sets a new password: the other one stays in the file
    client = again.test_client()
    _staff(again, STAFF, accounts[STAFF], client=client)
    r = client.post("/console/password", data={"_csrf": _token(client), "current": accounts[STAFF], "new": NEW_PASSWORD,
                                               "confirm": NEW_PASSWORD}, follow_redirects=True)
    assert b"Password updated" in r.data
    left = db.read_first_admin(again) == [(FIRST, accounts[FIRST])]
    assert left


def test_file_is_removed_after_the_change_of_password():
    from kts import db
    app = make_app(ADMIN_PASSWORD=None, ADMIN_EMAIL=FIRST)
    path = _first_admin_file(app)
    password = db.read_first_admin(app)[0][1]
    client = app.test_client()
    r = _staff(app, FIRST, password, client=client)
    assert _opens(r, "/console/password")
    token = _token(client)
    # a first password that stays is no change, and the retired one is not accepted either
    for new in (password, db.RETIRED_FIRST_PASSWORD):
        r = client.post("/console/password", data={"_csrf": token, "current": password, "new": new, "confirm": new})
        assert r.status_code == 200 and b"Password updated" not in r.data
        assert b"Choose a password" in r.data
        assert path.exists()
    r = client.post("/console/password", data={"_csrf": token, "current": "wrong", "new": NEW_PASSWORD, "confirm": NEW_PASSWORD})
    assert b"The current password is incorrect." in r.data and path.exists()
    r = client.post("/console/password", data={"_csrf": token, "current": password, "new": NEW_PASSWORD,
                                               "confirm": NEW_PASSWORD}, follow_redirects=True)
    assert b"Password updated" in r.data
    assert not path.exists()
    assert _rows(app, "SELECT must_change_password FROM users WHERE email = ?", (FIRST,)) == [(0,)]
    r = _staff(app, FIRST, NEW_PASSWORD)
    assert _opens(r, "/console/")
    # and it does not come back
    again = _restart(app, ADMIN_PASSWORD=None)
    assert not _first_admin_file(again).exists()


@contextmanager
def _read_only(path):
    """The file with the read-only attribute: Windows then refuses to write and to remove it."""
    os.chmod(path, stat.S_IREAD)
    try:
        yield
    finally:
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)


@on_windows
def test_file_that_cannot_be_removed_does_not_stop_the_start(caplog):
    from kts import db
    app = make_app(ADMIN_PASSWORD=None, ADMIN_EMAIL=FIRST)
    path = _first_admin_file(app)
    password = db.read_first_admin(app)[0][1]
    client = app.test_client()
    r = _staff(app, FIRST, password, client=client)
    assert _opens(r, "/console/password")
    with _read_only(path):
        r = client.post("/console/password", data={"_csrf": _token(client), "current": password, "new": NEW_PASSWORD,
                                                   "confirm": NEW_PASSWORD}, follow_redirects=True)
        assert b"Password updated" in r.data and path.exists()
        before = path.read_bytes()
        # what the file says is no longer true and the file cannot be removed: the portal starts
        with caplog.at_level(logging.WARNING):
            again = _restart(app, ADMIN_PASSWORD=None)
        assert f"{path} could not be brought up to date" in caplog.text
        logged = password in caplog.text
        assert not logged and path.read_bytes() == before
        assert again.test_client().get("/healthz").get_json()["ok"] is True
        opened = _password_opens(again, FIRST, NEW_PASSWORD, "/console/")
        assert opened
        # and so does every start that follows
        _restart(app, ADMIN_PASSWORD=None)
    # the file can be removed again: the next start does it
    again = _restart(app, ADMIN_PASSWORD=None)
    assert not _first_admin_file(again).exists()


@on_windows
@pytest.mark.parametrize("must_change", [1, 0])
def test_file_that_cannot_be_written_undoes_the_rotation(caplog, must_change):
    from kts import db
    app = make_app(ADMIN_EMAIL=FIRST)
    _give_retired_password(app, FIRST, must_change=must_change)
    path = _first_admin_file(app)
    db.write_first_admin(app, [("gone@tests.example", "not-a-real-password")])
    before = path.read_bytes()
    settings = _rows(app, "SELECT COUNT(*) FROM settings")
    with app.app_context():
        db.execute("DELETE FROM settings WHERE key = 'exam.date'")
    with _read_only(path):
        with caplog.at_level(logging.WARNING):
            again = _restart(app, ADMIN_PASSWORD=None)
        assert f"{path} could not be written" in caplog.text and "keeps it" in caplog.text
        assert "the first password is in the file" not in caplog.text
        # the account is as it was, and nothing says that it received a password
        assert _retired_password_opens(again)
        assert _rows(again, "SELECT must_change_password FROM users WHERE email = ?", (FIRST,)) == [(must_change,)]
        assert _rows(again, "SELECT COUNT(*) FROM audit_log WHERE action = 'first_password_rotated'") == [(0,)]
        assert path.read_bytes() == before
        # only the rotation was undone: the rest of the start has happened
        assert _rows(again, "SELECT COUNT(*) FROM settings") == settings
        # the accounts count as not yet compared
        assert _rows(again, CHECKED) == []
    # the next start tries again
    again = _restart(app, ADMIN_PASSWORD=None)
    assert _rows(again, CHECKED) == [("1",)]
    assert not _retired_password_opens(again)
    accounts = db.read_first_admin(again)
    assert [email for email, _password in accounts] == [FIRST]
    opened = _password_opens(again, FIRST, accounts[0][1], "/console/password")
    assert opened
    assert _rows(again, "SELECT COUNT(*) FROM audit_log WHERE action = 'first_password_rotated'") == [(1,)]


def _folders():
    folder = Path(tempfile.mkdtemp(prefix="app-", dir=TMP))
    (folder / "instance").mkdir()
    return {"INSTANCE_DIR": folder / "instance", "DATABASE": folder / "instance" / "test.sqlite3",
            "UPLOAD_DIR": folder / "uploads"}


@on_windows
def test_first_account_needs_its_file():
    # a password made for the very first account has no other place than the file
    folders = _folders()
    path = folders["INSTANCE_DIR"] / "first-admin.txt"
    path.write_text("left behind\r\n", encoding="utf-8")
    with _read_only(path):
        with pytest.raises(OSError):
            make_app(ADMIN_PASSWORD=None, ADMIN_EMAIL=FIRST, **folders)
        # no account without a password that somebody can read
        conn = sqlite3.connect(str(folders["DATABASE"]))
        try:
            assert conn.execute("SELECT COUNT(*) FROM users").fetchall() == [(0,)]
        finally:
            conn.close()
    app = make_app(ADMIN_PASSWORD=None, ADMIN_EMAIL=FIRST, **folders)
    from kts import db
    assert [email for email, _password in db.read_first_admin(app)] == [FIRST]


@on_windows
def test_first_account_with_a_configured_password_needs_no_file(caplog):
    folders = _folders()
    path = folders["INSTANCE_DIR"] / "first-admin.txt"
    path.write_text("E-mail:   gone@tests.example\r\nPassword: not-a-real-password\r\n", encoding="utf-8")
    with _read_only(path):
        with caplog.at_level(logging.WARNING):
            app = make_app(ADMIN_EMAIL=FIRST, **folders)
        assert f"{path} could not be brought up to date" in caplog.text
        opened = _password_opens(app, FIRST, os.environ["KTS_ADMIN_PASSWORD"], "/console/password")
        assert opened


def test_file_of_another_account_stays(site):
    from kts import db
    other = "Somebody.Else@tests.example"
    db.write_first_admin(site, [(other, "not-a-real-password")])
    path = _first_admin_file(site)
    try:
        client = site.test_client()
        _staff(site, STAFF, STAFF_PASSWORD, client=client)
        changed = STAFF_PASSWORD + "b"
        for current, new in ((STAFF_PASSWORD, changed), (changed, STAFF_PASSWORD)):
            r = client.post("/console/password", data={"_csrf": _token(client), "current": current, "new": new,
                                                       "confirm": new}, follow_redirects=True)
            assert b"Password updated" in r.data
        assert db.read_first_admin(site) == [(other, "not-a-real-password")]
        # the e-mail address is compared without regard to capitals
        db.forget_first_admin(site, other.upper())
        assert not path.exists()
    finally:
        if path.exists():
            path.unlink()


def test_file_forgets_what_is_no_longer_true():
    from kts import db
    app = make_app(ADMIN_PASSWORD=None, ADMIN_EMAIL=FIRST)
    password = db.read_first_admin(app)[0][1]
    db.write_first_admin(app, [("gone@tests.example", "not-a-real-password"), (FIRST, password)])
    again = _restart(app, ADMIN_PASSWORD=None)
    left = db.read_first_admin(again) == [(FIRST, password)]
    assert left
    # the password was set anew by other means (console, manage.py)
    with app.app_context():
        db.execute("UPDATE users SET must_change_password = 0 WHERE email = ?", (FIRST,))
    again = _restart(app, ADMIN_PASSWORD=None)
    assert not _first_admin_file(again).exists()


GENERAL_LINE = "Sign-in page: the address of the portal, followed by /console/login"
REAL_ADDRESS = "https://kts.cict.in"
REAL_LINE = "Sign-in page: https://kts.cict.in/console/login"


def _sign_in_lines(path):
    """What the file says about the sign-in page. The rest of it holds a password and is never printed."""
    return [line for line in path.read_bytes().decode("utf-8").split("\r\n") if "Sign-in" in line or "console/login" in line]


def _without_sign_in_lines(path):
    return [line for line in path.read_bytes().decode("utf-8").split("\r\n") if line not in _sign_in_lines(path)]


class _Kept:
    """The file as it is now, with a time of writing that no start of today can give it."""

    def __init__(self, path):
        os.utime(path, ns=(10 ** 18, 10 ** 18))
        self.path, self.content, self.written_at = path, path.read_bytes(), path.stat().st_mtime_ns

    def untouched(self):
        return self.path.read_bytes() == self.content and self.path.stat().st_mtime_ns == self.written_at


def test_file_names_no_page_that_does_not_exist():
    from kts import db
    # a start without KTS_BASE_URL, as the start test of the installer of earlier versions makes it
    app = make_app(ADMIN_PASSWORD=None, ADMIN_EMAIL=FIRST)
    assert app.config["BASE_URL"] == "http://localhost:8905"
    path = _first_admin_file(app)
    assert _sign_in_lines(path) == [GENERAL_LINE]
    nowhere = b"localhost" not in path.read_bytes() and b"8905" not in path.read_bytes()
    assert nowhere
    assert [email for email, _password in db.read_first_admin(app)] == [FIRST]
    # the same start once more leaves the file alone
    kept = _Kept(path)
    _restart(app, ADMIN_PASSWORD=None)
    assert kept.untouched()
    # the built-in address written out, with or without the stroke at its end, is no address either
    for base in ("http://localhost:8905", "http://localhost:8905/"):
        _restart(app, ADMIN_PASSWORD=None, BASE_URL=base)
        assert kept.untouched(), base


def test_file_is_written_anew_when_the_address_is_known():
    from kts import db
    app = make_app(ADMIN_PASSWORD=None, ADMIN_EMAIL=FIRST)
    path = _first_admin_file(app)
    assert _sign_in_lines(path) == [GENERAL_LINE]
    rest = _without_sign_in_lines(path)
    accounts = db.read_first_admin(app)
    users = _rows(app, "SELECT email, password_hash, must_change_password FROM users")
    # the next start is the one of the web server, which knows the address of the portal
    again = _restart(app, ADMIN_PASSWORD=None, BASE_URL=REAL_ADDRESS)
    assert _sign_in_lines(path) == [REAL_LINE]
    # the same accounts and passwords: nothing was rotated, nothing else has changed
    same = db.read_first_admin(again) == accounts and _without_sign_in_lines(path) == rest
    assert same and path.read_bytes().endswith(b"\r\n")
    same = _rows(again, "SELECT email, password_hash, must_change_password FROM users") == users
    assert same
    assert _rows(again, "SELECT COUNT(*) FROM audit_log WHERE action = 'first_password_rotated'") == [(0,)]
    opened = _password_opens(again, FIRST, db.read_first_admin(again)[0][1], "/console/password")
    assert opened
    # a start with the same address leaves the file untouched
    kept = _Kept(path)
    third = _restart(again, ADMIN_PASSWORD=None)
    assert third.config["BASE_URL"] == REAL_ADDRESS and kept.untouched()
    # and so does a start without the address (manage.py run by hand): the line stays right
    by_hand = _restart(app, ADMIN_PASSWORD=None)
    assert by_hand.config["BASE_URL"] == "http://localhost:8905" and kept.untouched()
    # the portal under another address: the file follows
    moved = _restart(app, ADMIN_PASSWORD=None, BASE_URL="https://portal.example/")
    assert _sign_in_lines(path) == ["Sign-in page: https://portal.example/console/login"]
    same = db.read_first_admin(moved) == accounts and _without_sign_in_lines(path) == rest
    assert same


def test_file_written_anew_keeps_every_account():
    from kts import db
    app = make_app(ADMIN_EMAIL=FIRST)
    with app.app_context():
        db.execute("INSERT INTO users(email, name, password_hash, role, active, must_change_password, created_at) "
                   "VALUES(?,?,?,?,1,1,?)", (STAFF, "Staff", "x", "admin", db.utcnow()))
    _give_retired_password(app, FIRST)
    _give_retired_password(app, STAFF)
    # the rotation at a start without the address, then the start that knows it
    first = _restart(app, ADMIN_PASSWORD=None)
    path = _first_admin_file(first)
    accounts = db.read_first_admin(first)
    assert _sign_in_lines(path) == [GENERAL_LINE] and sorted(email for email, _password in accounts) == [FIRST, STAFF]
    again = _restart(app, ADMIN_PASSWORD=None, BASE_URL=REAL_ADDRESS)
    same = db.read_first_admin(again) == accounts
    assert same and _sign_in_lines(path) == [REAL_LINE]
    assert _rows(again, "SELECT COUNT(*) FROM audit_log WHERE action = 'first_password_rotated'") == [(2,)]
    for email, password in accounts:
        opened = _password_opens(again, email, password, "/console/password")
        assert opened, email
    # with a configured password nothing is rotated, and the file is brought up to date all the same
    moved = _restart(app, BASE_URL="https://portal.example")
    same = db.read_first_admin(moved) == accounts
    assert same and _sign_in_lines(path) == ["Sign-in page: https://portal.example/console/login"]


@on_windows
def test_file_that_cannot_be_written_anew_does_not_stop_the_start(caplog):
    from kts import db
    app = make_app(ADMIN_PASSWORD=None, ADMIN_EMAIL=FIRST)
    path = _first_admin_file(app)
    password = db.read_first_admin(app)[0][1]
    kept = _Kept(path)
    with _read_only(path):
        with caplog.at_level(logging.WARNING):
            again = _restart(app, ADMIN_PASSWORD=None, BASE_URL=REAL_ADDRESS)
        assert f"{path} could not be brought up to date" in caplog.text
        logged = password in caplog.text
        assert not logged and kept.untouched()
        assert again.test_client().get("/healthz").get_json()["ok"] is True
        opened = _password_opens(again, FIRST, password, "/console/password")
        assert opened
    # the file can be written again: the next start does it
    again = _restart(app, ADMIN_PASSWORD=None, BASE_URL=REAL_ADDRESS)
    assert _sign_in_lines(path) == [REAL_LINE]
    opened = _password_opens(again, FIRST, password, "/console/password")
    assert opened


# ---- A8 · the settings file instance/portal.env -----------------------------------

def test_settings_file(monkeypatch):
    monkeypatch.delenv("KTS_SMTP_HOST", raising=False)
    config, folder = _config(monkeypatch, lines=[
        "# outgoing mail",
        "KTS_SMTP_HOST = smtp.example.org",
        '  KTS_SMTP_FROM="KTS office <office@example.org>"  ',
        "KTS_SMTP_USER='user name'",
        "KTS_SMTP_PORT=2525",
        "#KTS_SMTP_PASSWORD=left out",
        "   # KTS_SMTP_TLS=0",
        "",
        "a line without the sign",
        "=no name",
        "KTS_BASE_URL=https://portal.example/?a=b",
        "KTS_RATE_REGISTER_PER_HOUR=250",
        "KTS_RATE_CONTACT_PER_HOUR=a dozen",
        "KTS_HTTPS=1",
        "KTS_HSTS=\"1\"",
        "KTS_TRUSTED_PROXY=10.0.0.5",
        "KTS_URL_PREFIX=",
        # where the data is cannot be said by the file
        "KTS_DATABASE=C:\\elsewhere\\other.sqlite3",
        "KTS_UPLOAD_DIR=C:\\elsewhere\\uploads",
        "KTS_INSTANCE_DIR=C:\\elsewhere",
    ])
    assert config.SMTP_HOST == "smtp.example.org"
    assert config.SMTP_FROM == "KTS office <office@example.org>"
    assert config.SMTP_USER == "user name"
    assert config.SMTP_PORT == 2525
    assert config.SMTP_PASSWORD is None and config.SMTP_TLS is True
    assert config.BASE_URL == "https://portal.example/?a=b"
    assert config.RATE_REGISTER_PER_HOUR == 250 and config.RATE_CONTACT_PER_HOUR == 10
    assert config.SESSION_COOKIE_SECURE is True and config.HSTS is True
    assert config.TRUSTED_PROXY == "10.0.0.5" and config.URL_PREFIX == ""
    assert config.INSTANCE_DIR == folder and config.DATABASE == folder / "test.sqlite3"
    assert config.UPLOAD_DIR == folder / "uploads"
    # the password of the tests comes from the environment
    assert config.ADMIN_PASSWORD == os.environ["KTS_ADMIN_PASSWORD"]
    # the two lines that hold no setting, by their numbers
    assert config.SETTINGS_UNUSED_LINES == (9, 10)
    # and the setting whose value is no number, by its name
    assert config.SETTINGS_UNUSABLE == ("KTS_RATE_CONTACT_PER_HOUR",)


def test_names_in_small_letters(monkeypatch):
    monkeypatch.delenv("KTS_SMTP_HOST", raising=False)
    config, _folder = _config(monkeypatch, lines=["kts_smtp_host=smtp.example.org", "Kts_Smtp_User = Office",
                                                  "kts_hsts=1", "kts_rate_login_fails=40"])
    assert config.SMTP_HOST == "smtp.example.org" and config.SMTP_USER == "Office"
    assert config.HSTS is True and config.RATE_LOGIN_FAILS_PER_15MIN == 40
    assert config.SETTINGS_UNUSED_LINES == () and config.SETTINGS_UNUSABLE == ()


def test_where_the_data_is_cannot_be_said_in_small_letters_either(monkeypatch):
    folder = Path(tempfile.mkdtemp(prefix="env-", dir=TMP))
    (folder / "portal.env").write_text("kts_database=C:\\elsewhere\\other.sqlite3\nKts_Upload_Dir=C:\\elsewhere\\uploads\n"
                                       "kts_instance_dir=C:\\elsewhere\nKTS_DATABASE=C:\\elsewhere\\other.sqlite3\n",
                                       encoding="utf-8")
    monkeypatch.setenv("KTS_INSTANCE_DIR", str(folder))
    # the environment is silent about the database: now the file would be asked
    monkeypatch.delenv("KTS_DATABASE")
    spec = importlib.util.spec_from_file_location("config_read_anew", ROOT / "config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # config.py is read, no application is made of it
    assert module._FILE == {}
    assert module.Config.DATABASE == folder / "kts5.sqlite3" and module.Config.INSTANCE_DIR == folder
    assert module.Config.UPLOAD_DIR == Path(os.environ["KTS_UPLOAD_DIR"])


def test_lines_without_a_setting_are_named_in_the_log(monkeypatch, caplog):
    from kts import create_app
    secret = "Kept-To-Itself-42"
    config, folder = _config(monkeypatch, lines=[
        "# mail",
        f"KTS_SMTP_PASSWORD: {secret}",
        "KTS_SMTP_HOST=smtp.example.org",
        f"= {secret}",
        "",
        "KTS_HSTS 1",
        f"{secret}",
    ])
    assert config.SETTINGS_UNUSED_LINES == (2, 4, 6, 7) and config.SMTP_PASSWORD is None
    with caplog.at_level(logging.WARNING):
        create_app(config)
    lines = [record.getMessage() for record in caplog.records if "portal.env" in record.getMessage()]
    assert lines == [f"{folder / 'portal.env'}: no setting could be read from lines 2, 4, 6, 7. "
                     "A setting is written NAME=value."]
    # the numbers, never the text of a line
    assert secret not in caplog.text and "KTS_HSTS" not in caplog.text
    caplog.clear()
    config, folder = _config(monkeypatch, lines=["KTS_SMTP_HOST=smtp.example.org", "no setting"])
    with caplog.at_level(logging.WARNING):
        create_app(config)
    assert f"{folder / 'portal.env'}: no setting could be read from line 2. " in caplog.text


def test_a_settings_file_in_order_is_not_mentioned(monkeypatch, caplog):
    from kts import create_app
    for lines in (["# nothing is set"], ["KTS_SMTP_HOST=smtp.example.org", "", "   ", "#"], None):
        config, _folder = _config(monkeypatch, lines=lines)
        assert config.SETTINGS_UNUSED_LINES == () and config.SETTINGS_UNUSABLE == ()
        with caplog.at_level(logging.WARNING):
            create_app(config)
        assert "portal.env" not in caplog.text and "cannot be used" not in caplog.text


UNUSABLE = ("These settings have a value that cannot be used (a limit is a whole number above zero, a switch is 1 or 0): "
            "{}. In portal.env nothing may follow the value on its line.")


def _logged(caplog, folder):
    """What the portal says in the log about its settings, without the name of the folder."""
    lines = [record.getMessage() for record in caplog.records if record.name == "kts"]
    return [line.replace(str(folder), "<folder>") for line in lines if "portal.env" in line]


def test_values_that_cannot_be_used_are_named_in_the_log(monkeypatch, caplog):
    from kts import create_app
    secret = "Kept-To-Itself-42"
    config, folder = _config(monkeypatch, lines=[
        "KTS_RATE_REGISTER_PER_HOUR=250   # the computer room",
        "KTS_HSTS=1 ; on",
        "set KTS_RATE_LOGIN_FAILS=3",
        # a password on the line of the port
        f"KTS_SMTP_PORT={secret}",
        "KTS_RATE_CONTACT_PER_HOUR=25",
    ])
    # what cannot be used changes nothing
    assert config.RATE_REGISTER_PER_HOUR == 100 and config.HSTS is False and config.RATE_LOGIN_FAILS_PER_15MIN == 12
    assert config.SMTP_PORT == 587 and config.RATE_CONTACT_PER_HOUR == 25
    assert sorted(config.SETTINGS_UNUSABLE) == ["KTS_HSTS", "KTS_RATE_REGISTER_PER_HOUR", "KTS_SMTP_PORT"]
    assert config.SETTINGS_UNUSED_LINES == (3,)
    with caplog.at_level(logging.WARNING):
        app = create_app(config)
    assert app.config["SETTINGS_UNUSABLE"] == config.SETTINGS_UNUSABLE
    assert _logged(caplog, folder) == [
        f"<folder>{os.sep}portal.env: no setting could be read from line 3. A setting is written NAME=value.",
        UNUSABLE.format(", ".join(config.SETTINGS_UNUSABLE))]
    # the names, never a value, and nothing of a line that holds no setting
    said = " ".join(_logged(caplog, folder))
    for value in ("250", "computer room", "1 ;", "; on", "=3", "KTS_RATE_LOGIN_FAILS", secret, "KTS_RATE_CONTACT_PER_HOUR"):
        assert value not in said, value
    assert secret not in caplog.text and "computer room" not in caplog.text
    assert "Strict-Transport-Security" not in app.test_client().get("/healthz").headers
    # the same file without what follows the values
    caplog.clear()
    config, folder = _config(monkeypatch, lines=["KTS_RATE_REGISTER_PER_HOUR=250", "KTS_HSTS=1", "KTS_RATE_LOGIN_FAILS=3",
                                                 "KTS_SMTP_PORT=2525", "KTS_HTTPS=1"])
    assert config.RATE_REGISTER_PER_HOUR == 250 and config.HSTS is True and config.RATE_LOGIN_FAILS_PER_15MIN == 3
    assert config.SETTINGS_UNUSABLE == () and config.SETTINGS_UNUSED_LINES == ()
    with caplog.at_level(logging.WARNING):
        create_app(config)
    assert _logged(caplog, folder) == []


@pytest.mark.parametrize("line", ["set KTS_SMTP_HOST=smtp.example.org", "SET  KTS_SMTP_HOST=smtp.example.org",
                                  "export KTS_SMTP_HOST=smtp.example.org", "$env:KTS_SMTP_HOST=smtp.example.org",
                                  "KTS-SMTP-HOST=smtp.example.org", "KTS SMTP HOST=smtp.example.org",
                                  "KTS_SMTP_HOST:=smtp.example.org", "'KTS_SMTP_HOST'=smtp.example.org", "___=x", "=x"])
def test_a_name_is_made_of_letters_digits_and_the_low_line(monkeypatch, line):
    monkeypatch.delenv("KTS_SMTP_HOST", raising=False)
    config, folder = _config(monkeypatch, lines=["# mail", line, "KTS_SMTP_USER=office", "kts_smtp_from2=x"])
    assert config.SMTP_HOST is None and config.SMTP_USER == "office"
    assert config.SETTINGS_UNUSED_LINES == (2,) and config.SETTINGS_UNUSABLE == ()
    # and nothing is kept under a name that nobody asks for
    spec = importlib.util.spec_from_file_location("config_read_anew", ROOT / "config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.Config.INSTANCE_DIR == folder
    assert module._FILE == {"KTS_SMTP_USER": "office", "KTS_SMTP_FROM2": "x"}


@pytest.mark.parametrize("name, attribute, value", [
    ("KTS_HTTPS", "SESSION_COOKIE_SECURE", "yes"), ("KTS_BEHIND_PROXY", "BEHIND_PROXY", "true"),
    ("KTS_HSTS", "HSTS", "1 # on"), ("KTS_HSTS", "HSTS", " 1"), ("KTS_SMTP_TLS", "SMTP_TLS", "off"),
    ("KTS_SMTP_TLS", "SMTP_TLS", "0 # no tls"), ("KTS_SMTP_TLS", "SMTP_TLS", "on")])
def test_a_switch_is_one_or_nought(monkeypatch, caplog, name, attribute, value):
    from kts import create_app
    # from the environment, where no file is to blame; the value counts as it did before: not as 1
    config, folder = _config(monkeypatch, **{name: value})
    assert getattr(config, attribute) is False and config.SETTINGS_UNUSABLE == (name,)
    with caplog.at_level(logging.WARNING):
        create_app(config)
    assert _logged(caplog, folder) == [UNUSABLE.format(name)]
    for right, read in (("1", True), ("0", False)):
        config, _folder = _config(monkeypatch, **{name: right})
        assert getattr(config, attribute) is read and config.SETTINGS_UNUSABLE == ()


def test_environment_wins_over_the_file(monkeypatch):
    lines = ["KTS_SMTP_HOST=file.example.org", "KTS_SMTP_FROM=file@example.org", "KTS_RATE_LOGIN_FAILS=40"]
    config, _folder = _config(monkeypatch, lines=lines, KTS_SMTP_HOST="environment.example.org", KTS_RATE_LOGIN_FAILS="20",
                              KTS_SMTP_FROM="")
    assert config.SMTP_HOST == "environment.example.org" and config.RATE_LOGIN_FAILS_PER_15MIN == 20
    # an empty variable of the environment is no value
    assert config.SMTP_FROM == "file@example.org"


def test_first_password_from_the_file_or_none(monkeypatch):
    monkeypatch.delenv("KTS_ADMIN_PASSWORD")
    config, _folder = _config(monkeypatch, lines=["KTS_ADMIN_EMAIL=chief@example.org"])
    assert config.ADMIN_PASSWORD is None and config.ADMIN_EMAIL == "chief@example.org"
    config, _folder = _config(monkeypatch)
    assert config.ADMIN_PASSWORD is None and config.ADMIN_EMAIL == "admin@kts5.local"


@pytest.mark.parametrize("raw", [
    "KTS_SMTP_HOST=smtp.example.org\r\nKTS_SMTP_USER=அலுவலகம்\r\n".encode("utf-8"),
    b"\xef\xbb\xbf" + "KTS_SMTP_HOST=smtp.example.org\r\nKTS_SMTP_USER=அலுவலகம்\r\n".encode("utf-8"),
    "\ufeffKTS_SMTP_HOST=smtp.example.org\r\nKTS_SMTP_USER=அலுவலகம்\r\n".encode("utf-16-le"),
    "\ufeffKTS_SMTP_HOST=smtp.example.org\r\nKTS_SMTP_USER=அலுவலகம்\r\n".encode("utf-16-be"),
], ids=["utf-8", "utf-8 with mark", "utf-16 le", "utf-16 be"])
def test_settings_file_as_windows_saves_it(monkeypatch, raw):
    monkeypatch.delenv("KTS_SMTP_HOST", raising=False)
    config, _folder = _config(monkeypatch, raw=raw)
    assert config.SMTP_HOST == "smtp.example.org" and config.SMTP_USER == "அலுவலகம்"


def test_settings_file_missing_or_unreadable(monkeypatch):
    monkeypatch.delenv("KTS_SMTP_HOST", raising=False)
    config, folder = _config(monkeypatch)
    assert not (folder / "portal.env").exists()
    assert config.SMTP_HOST is None and config.SMTP_PORT == 587 and config.RATE_REGISTER_PER_HOUR == 100
    # a folder of that name cannot be read as a file
    config, folder = _config(monkeypatch)
    (folder / "portal.env").mkdir()
    config, _folder = _config(monkeypatch, KTS_INSTANCE_DIR=str(folder))
    assert config.SMTP_HOST is None
    # bytes that are no text
    config, _folder = _config(monkeypatch, raw=b"\x00\x81\xfe=\xff\nKTS_SMTP_HOST=smtp.example.org\n")
    assert config.SMTP_HOST == "smtp.example.org"


# ---- A9 · dates on the About page --------------------------------------------------

def _about(app, code):
    return app.test_client().get(f"/about?lang={code}").data.decode("utf-8")


@pytest.mark.parametrize("order", [("en", "hi"), ("hi", "en"), ("ur", "en", "ta"), ("en", "ur")])
def test_about_dates_follow_the_language(order):
    fresh = make_app()  # nothing compiled yet: the first language is the one that used to stay
    pages = {code: _about(fresh, code) for code in order}
    # and once more, now from the compiled template
    pages.update({code + " again": _about(fresh, code) for code in order})
    for code, page in pages.items():
        assert f'<html lang="{code.split()[0]}"' in page
        if code.startswith("en"):
            assert "KTS 1.0 · 16 Nov 2022 – 15 Dec 2022" in page and "16-11-2022" not in page, order
            assert "\u2066" not in page
        elif code.startswith("ur"):
            assert "KTS 1.0 · \u206616-11-2022\u2069 – \u206615-12-2022\u2069" in page and "Nov 2022" not in page, order
        else:
            assert "KTS 1.0 · 16-11-2022 – 15-12-2022" in page and "Nov 2022" not in page, order
            assert "KTS 3.0 · 15-02-2025 – 24-02-2025" in page


def test_date_filters_take_the_context(app):
    for name in ("date", "datetime", "time"):
        assert getattr(app.jinja_env.filters[name], "jinja_pass_arg", None) is not None, name
    with app.test_request_context("/?lang=en"):
        template = app.jinja_env.from_string("{{ '2026-11-29T11:00:00'|datetime }} | {{ '2026-11-29T11:00:00'|time }} | {{ day|date }}")
    with app.test_request_context("/?lang=ta"):
        assert template.render(day="2026-11-29") == "29-11-2026, 11:00 | 11:00 | 29-11-2026"
    with app.test_request_context("/?lang=en"):
        assert template.render(day="2026-11-29") == "29 Nov 2026, 11:00 AM | 11:00 AM | 29 Nov 2026"


# ---- A10 · headers ---------------------------------------------------------------

@pytest.mark.parametrize("path", ["/register", "/register/", "/register/done/KTS5-2026-000001", "/status", "/status?app=x",
                                  "/contact", "/console/login", "/candidate/login", "/hub/", "/console/logout"])
def test_no_store(app, path):
    assert app.test_client().get(path).headers.get("Cache-Control") == "no-store"


@pytest.mark.parametrize("path", ["/", "/about", "/schedule", "/thirukkural/1", "/static/css/portal.css"])
def test_public_pages_may_be_kept(app, path):
    r = app.test_client().get(path)
    assert r.status_code == 200 and "no-store" not in r.headers.get("Cache-Control", "")


def test_four_headers_stay(app):
    headers = app.test_client().get("/").headers
    assert headers["X-Content-Type-Options"] == "nosniff" and headers["X-Frame-Options"] == "SAMEORIGIN"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    assert "Strict-Transport-Security" not in headers


@pytest.mark.parametrize("hsts, secure, sent", [(True, True, True), (True, False, False), (False, True, False)])
def test_strict_transport_security(hsts, secure, sent):
    own = make_app(HSTS=hsts, SESSION_COOKIE_SECURE=secure)
    for path in ("/", "/console/login", "/no-such-page", "/static/css/portal.css"):
        headers = own.test_client().get(path, base_url="https://localhost").headers
        assert headers.get("Strict-Transport-Security") == ("max-age=31536000" if sent else None), path


# ---- A11 · trailing slash, 405 ---------------------------------------------------

@pytest.mark.parametrize("path", ["/about", "/register", "/status", "/contact", "/schedule", "/thirukkural",
                                  "/thirukkural/1", "/daily-kural", "/merit-list", "/candidate/login", "/console/login"])
def test_with_and_without_slash(app, path):
    client = app.test_client()
    plain = client.get(path)
    slash = client.get(path + "/")
    assert plain.status_code == 200 and slash.status_code == 200
    assert "Location" not in slash.headers
    title = re.search(r"<title>(.*?)</title>", plain.data.decode("utf-8"), re.S).group(1)
    assert f"<title>{title}</title>" in slash.data.decode("utf-8")


def test_static_files_and_unknown_pages(app):
    client = app.test_client()
    assert client.get("/static/css/portal.css").status_code == 200
    assert client.get("/no-such-page").status_code == 404 and client.get("/no-such-page/").status_code == 404
    assert client.get("/healthz/").get_json()["ok"] is True


@pytest.mark.parametrize("path, target", [("/console", "/console/login"), ("/console/", "/console/login"),
                                          ("/candidate", "/candidate/login"), ("/candidate/", "/candidate/login"),
                                          ("/hub", "/console/login"), ("/hub/", "/console/login")])
def test_entrances_without_sign_in(app, path, target):
    client = app.test_client()
    r = client.get(path)
    assert r.status_code == 302 and r.headers["Location"] == target
    r = client.get(path, follow_redirects=True)
    assert r.status_code == 200 and len(r.history) == 1 and r.request.path == target


def test_entrances_after_sign_in(site):
    client = site.test_client()
    r = _staff(site, STAFF, STAFF_PASSWORD, client=client)
    assert _opens(r)
    for path in ("/console", "/console/", "/hub", "/hub/", "/console/applications", "/console/applications/"):
        r = client.get(path)
        assert r.status_code == 200 and "Location" not in r.headers, path
    # who is signed in is sent on from the sign-in page, once
    r = client.get("/console/login/", follow_redirects=True)
    assert r.status_code == 200 and len(r.history) == 1 and r.request.path == "/console/"
    client = site.test_client()
    form = dict(CANDIDATE, _csrf=_token(client, "/candidate/login"))
    assert client.post("/candidate/login/", data=form).status_code == 302
    for path in ("/candidate", "/candidate/", "/candidate/acknowledgement", "/candidate/acknowledgement/"):
        assert client.get(path).status_code == 200, path


@pytest.mark.parametrize("path", ["/console/logout", "/candidate/logout", "/console/logout/"])
def test_method_not_allowed_shows_the_portal_page(app, path):
    client = app.test_client()
    r = client.get(path)
    page = r.data.decode("utf-8")
    assert r.status_code == 405
    assert "POST" in r.headers["Allow"] and "GET" not in r.headers["Allow"]
    assert '<html lang="en" dir="ltr"' in page and '<span class="eyebrow">405</span>' in page
    assert f"<h1>{_text('err.404.t')}</h1>" in page and _text("err.404.d") in page
    assert 'href="/static/css/portal.css' in page and "Method Not Allowed" not in page
    assert r.headers["Cache-Control"] == "no-store" and r.headers["X-Content-Type-Options"] == "nosniff"
    # in the language of the visitor
    client.get("/lang/hi")
    page = client.get(path).data.decode("utf-8")
    assert '<html lang="hi"' in page and f"<h1>{_text('err.404.t', 'hi')}</h1>" in page
    assert not re.search(r">\s*err\.[a-z0-9_.]+\s*<", page)


def test_post_where_only_get_is_allowed(app):
    client = app.test_client()
    r = client.post("/about", data={"_csrf": _token(client)})
    assert r.status_code == 405 and '<span class="eyebrow">405</span>' in r.data.decode("utf-8")
    assert "GET" in r.headers["Allow"]
    # sign-out itself works as before
    r = client.post("/console/logout", data={"_csrf": _token(client)})
    assert r.status_code == 302 and r.headers["Location"] == "/"


# ---- A12 · version ---------------------------------------------------------------

def test_version():
    from kts import version
    assert version.VERSION == "1.2.4"
    assert "/healthz" in version.__doc__ and "installer" in version.__doc__


# ---- a session belongs to the password it was opened with -------------------------------

def _held(app, client):
    """The browser of before, with its cookie, in front of the portal as it runs now."""
    held = app.test_client()
    held.set_cookie("session", client.get_cookie("session").value)
    return held


def _change(client, current, new):
    return client.post("/console/password", data={"_csrf": _token(client, "/console/password"), "current": current,
                                                   "new": new, "confirm": new})


@pytest.mark.parametrize("must_change", [1, 0])
def test_a_session_ends_when_the_password_is_replaced(must_change):
    # Somebody signed in with the published password while an earlier version ran and kept his
    # browser open. The start of the portal replaces the password, the administrator sets his own.
    from kts import db
    app = make_app(ADMIN_EMAIL=FIRST)
    _give_retired_password(app, FIRST, must_change=must_change)
    stranger = app.test_client()
    assert _opens(_staff(app, FIRST, db.RETIRED_FIRST_PASSWORD, client=stranger))
    again = _restart(app, ADMIN_PASSWORD=None)
    held = _held(again, stranger)
    r = held.get("/console/users")
    assert r.status_code == 302 and r.headers["Location"].endswith("/console/login")
    password = db.read_first_admin(again)[0][1]
    owner = again.test_client()
    assert _opens(_staff(again, FIRST, password, client=owner), "/console/password")
    assert _change(owner, password, NEW_PASSWORD).status_code == 302
    # whoever changed the password stays signed in, the browser of before does not come back
    assert owner.get("/console/users").status_code == 200
    r = held.get("/console/users")
    assert r.status_code == 302 and r.headers["Location"].endswith("/console/login")
    r = held.get("/console/applications/export.csv")
    assert r.status_code == 302 and b"@" not in r.data


def test_a_session_ends_when_the_password_is_changed_elsewhere(site):
    # two browsers of one member of staff: the change in one of them ends the other
    from werkzeug.security import generate_password_hash
    from kts.db import execute
    here, there = site.test_client(), site.test_client()
    assert _opens(_staff(site, STAFF, STAFF_PASSWORD, client=here))
    assert _opens(_staff(site, STAFF, STAFF_PASSWORD, client=there))
    try:
        assert _change(here, STAFF_PASSWORD, NEW_PASSWORD).status_code == 302
        assert here.get("/console/").status_code == 200
        r = there.get("/console/")
        assert r.status_code == 302 and r.headers["Location"].endswith("/console/login")
    finally:
        with site.app_context():
            execute("UPDATE users SET password_hash = ? WHERE email = ?", (generate_password_hash(STAFF_PASSWORD), STAFF))

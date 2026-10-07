"""
Configuration for the Kashi Tamil Sangamam 5.0 portal.

Everything that differs between a laptop, a staging box and the production
server is read from environment variables so the same code runs everywhere.
A setting that the environment does not have is taken from the settings file
instance/portal.env, which an update of the portal leaves alone.
"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# These say where the data is, and with it the settings file: environment only.
_ENV_ONLY = ("KTS_INSTANCE_DIR", "KTS_DATABASE", "KTS_UPLOAD_DIR")


def _settings_file():
    """
    The settings of instance/portal.env: lines NAME=value, a line that starts with '#' is a
    comment. Spaces around name and value and one pair of quotes around the value are removed;
    a name may be written in small letters. A missing or unreadable file is no error.

    Gives the settings and the numbers of the lines that hold no setting: no '=', or in front
    of it something that is no name (a name is made of letters, digits and '_').
    """
    folder = os.environ.get("KTS_INSTANCE_DIR") or BASE_DIR / "instance"
    try:
        raw = (Path(folder) / "portal.env").read_bytes()
    except OSError:
        return {}, []
    # Notepad and PowerShell may have saved the file as UTF-16 or with a byte order mark
    text = raw.decode("utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig", "replace")
    values, unused = {}, []
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, sign, value = line.partition("=")
        # capitals before the name is compared: kts_database must not get past _ENV_ONLY
        name, value = name.strip().upper(), value.strip()
        if not sign or not name.replace("_", "").isalnum():
            # no name, or 'set NAME'. The number only: the text of such a line may be a password
            unused.append(number)
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if name not in _ENV_ONLY:
            values[name] = value
    return values, unused


_FILE, _UNUSED_LINES = _settings_file()
# names of settings that have a value which cannot be used; create_app names them in the log
_UNUSABLE = []

# the address of the portal when no setting names one
DEFAULT_BASE_URL = "http://localhost:8905"


def _env(name, default=None):
    """The environment, else the settings file, else the default."""
    value = os.environ.get(name)
    if value in (None, ""):
        value = _FILE.get(name)
    return value if value not in (None, "") else default


def _int_env(name, default):
    """
    A whole number above zero with at most 9 digits; anything else gives the default, and the
    name of the setting is kept for the log.
    """
    value = str(_env(name, "")).strip()
    if len(value) <= 9 and value.isascii() and value.isdigit() and int(value) > 0:
        return int(value)
    if value and name not in _UNUSABLE:
        _UNUSABLE.append(name)
    return default


def _flag_env(name, default):
    """
    A switch: True for the value 1 and for nothing else, as before. A value that is neither 1
    nor 0 is no answer to the question: the name of the setting is kept for the log.
    """
    value = _env(name, default)
    if value not in ("0", "1") and name not in _UNUSABLE:
        _UNUSABLE.append(name)
    return value == "1"


def _secret_key(instance_dir):
    """
    KTS_SECRET_KEY if set; otherwise a key persisted in instance/secret.key
    (generated on first start, so sessions survive restarts without anyone
    having to put a secret into web.config).
    """
    explicit = _env("KTS_SECRET_KEY")
    if explicit:
        return explicit
    path = Path(instance_dir) / "secret.key"
    try:
        if path.exists():
            key = path.read_text(encoding="utf-8").strip()
            if len(key) >= 32:
                return key
        path.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_urlsafe(48)
        path.write_text(key, encoding="utf-8")
        return key
    except OSError:
        return "kts5-dev-secret-change-me"


class Config:
    # ---- storage --------------------------------------------------------
    INSTANCE_DIR = Path(_env("KTS_INSTANCE_DIR", BASE_DIR / "instance"))
    DATABASE = Path(_env("KTS_DATABASE", INSTANCE_DIR / "kts5.sqlite3"))
    UPLOAD_DIR = Path(_env("KTS_UPLOAD_DIR", BASE_DIR / "uploads"))
    DATA_DIR = BASE_DIR / "data"
    # lines of instance/portal.env that hold no setting; create_app names them in the log
    SETTINGS_UNUSED_LINES = tuple(_UNUSED_LINES)
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB request ceiling
    PHOTO_MAX_BYTES = 600 * 1024
    IDPROOF_MAX_BYTES = 2 * 1024 * 1024
    # the nomination form signed by the head of the institution, scanned (version 1.2.22)
    NOMINATION_MAX_BYTES = 4 * 1024 * 1024
    RESOURCE_MAX_BYTES = 20 * 1024 * 1024

    # ---- security -------------------------------------------------------
    SECRET_KEY = _secret_key(INSTANCE_DIR)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _flag_env("KTS_HTTPS", "0")
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 hours
    TEMPLATES_AUTO_RELOAD = True
    SEND_FILE_MAX_AGE_DEFAULT = 300
    ASSET_VERSION = "2"

    # ---- hosting --------------------------------------------------------
    # Behind IIS (ASP.NET Core Module, HttpPlatformHandler or ARR), nginx or any reverse proxy
    # on this machine: serve.py tells Waitress to take the visitor's address from the last entry
    # of X-Forwarded-For, the one the proxy wrote, when the connection comes from TRUSTED_PROXY.
    # No other forwarding header is believed: the scheme comes from KTS_HTTPS, the host name from
    # the Host header and a path prefix from KTS_URL_PREFIX.
    BEHIND_PROXY = _flag_env("KTS_BEHIND_PROXY", "0")
    TRUSTED_PROXY = _env("KTS_TRUSTED_PROXY", "127.0.0.1")
    # Strict-Transport-Security on every answer. Switch it on (KTS_HSTS=1) only when the site has
    # its real certificate, and not in the web server as well. Needs KTS_HTTPS=1.
    HSTS = _flag_env("KTS_HSTS", "0")
    # Serve under a path such as /kts5 when the portal is an IIS application
    # inside an existing site rather than its own host name.
    URL_PREFIX = (_env("KTS_URL_PREFIX", "") or "").strip().rstrip("/")

    # ---- site -----------------------------------------------------------
    SITE_NAME = "Kashi Tamil Sangamam 5.0"
    SITE_SHORT = "KTS 5.0"
    SITE_THEME_EN = "Thirukkural Payilvom – Thirukkural Abhyas Karen"
    SITE_THEME_TA = "திருக்குறள் பயில்வோம்"
    SITE_THEME_HI = "तिरुक्कुरल अभ्यास करें"
    SITE_THEME_MEANING = "Let's Learn Thirukkural"
    ORGANISER = "Central Institute of Classical Tamil (CICT), Chennai"
    MINISTRY = "Ministry of Education, Government of India"
    BASE_URL = _env("KTS_BASE_URL", DEFAULT_BASE_URL)
    DEFAULT_LANG = "en"  # the 23 interface languages are listed in kts/i18n.py

    # ---- mail (optional) ------------------------------------------------
    # If SMTP is not configured, every message is kept in the outbox table
    # and can be read by administrators from the console.
    SMTP_HOST = _env("KTS_SMTP_HOST")
    SMTP_PORT = _int_env("KTS_SMTP_PORT", 587)
    SMTP_USER = _env("KTS_SMTP_USER")
    SMTP_PASSWORD = _env("KTS_SMTP_PASSWORD")
    SMTP_FROM = _env("KTS_SMTP_FROM", "office@cict.in")
    SMTP_TLS = _flag_env("KTS_SMTP_TLS", "1")

    # ---- first administrator -------------------------------------------
    # Created on first start if no user exists. Without KTS_ADMIN_PASSWORD the portal makes a
    # password of its own and writes it to instance/first-admin.txt (see kts/db.py).
    ADMIN_EMAIL = _env("KTS_ADMIN_EMAIL", "admin@kts5.local")
    ADMIN_PASSWORD = _env("KTS_ADMIN_PASSWORD")

    # ---- rate limiting (in-process, per address) ------------------------
    # The students of one college reach the portal through one public address, so a limit per
    # address has to leave room for a whole campus: on the day of the test all of them sign in
    # within the same minutes, and a limit that is reached closes the address for right details
    # too. Sign-in and status look-up count failed attempts only.
    RATE_REGISTER_PER_HOUR = _int_env("KTS_RATE_REGISTER_PER_HOUR", 100)
    RATE_CONTACT_PER_HOUR = _int_env("KTS_RATE_CONTACT_PER_HOUR", 10)
    RATE_STATUS_FAILS_PER_15MIN = _int_env("KTS_RATE_STATUS_FAILS", 300)
    RATE_LOGIN_FAILS_PER_15MIN = _int_env("KTS_RATE_LOGIN_FAILS", 12)
    RATE_CAND_FAILS_IP_PER_15MIN = _int_env("KTS_RATE_CANDIDATE_FAILS_IP", 600)
    # Per application number and address together, for the sign-in and for the status look-up
    # each. Application numbers are consecutive: counted per number alone, six wrong attempts
    # from anywhere would close the sign-in of any candidate during the hour of the test.
    # The price: guesses against one number are bounded per address, not in total.
    RATE_CAND_FAILS_APP_PER_15MIN = _int_env("KTS_RATE_CANDIDATE_FAILS_APP", 6)

    # last in the class: by now every setting has been read
    SETTINGS_UNUSABLE = tuple(_UNUSABLE)

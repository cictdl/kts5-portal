"""
Configuration for the Kashi Tamil Sangamam 5.0 portal.

Everything that differs between a laptop, a staging box and the production
server is read from environment variables so the same code runs everywhere.
"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _env(name, default=None):
    value = os.environ.get(name)
    return value if value not in (None, "") else default


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
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB request ceiling
    PHOTO_MAX_BYTES = 600 * 1024
    IDPROOF_MAX_BYTES = 2 * 1024 * 1024
    RESOURCE_MAX_BYTES = 20 * 1024 * 1024

    # ---- security -------------------------------------------------------
    SECRET_KEY = _secret_key(INSTANCE_DIR)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env("KTS_HTTPS", "0") == "1"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 hours
    TEMPLATES_AUTO_RELOAD = True
    SEND_FILE_MAX_AGE_DEFAULT = 300
    ASSET_VERSION = "2"

    # ---- hosting --------------------------------------------------------
    # Behind IIS (HttpPlatformHandler or ARR), nginx or any reverse proxy:
    # trust X-Forwarded-For / -Proto / -Host from the proxy in front.
    BEHIND_PROXY = _env("KTS_BEHIND_PROXY", "0") == "1"
    # Serve under a path such as /kts5 when the portal is an IIS application
    # inside an existing site rather than its own host name.
    URL_PREFIX = (_env("KTS_URL_PREFIX", "") or "").strip().rstrip("/")

    # ---- site -----------------------------------------------------------
    SITE_NAME = "Kashi Tamil Sangamam 5.0"
    SITE_SHORT = "KTS 5.0"
    SITE_THEME_EN = "Thirukkural Payilvom – Thirukkural Abhyas Karen"
    SITE_THEME_TA = "திருக்குறள் பயில்வோம்"
    SITE_THEME_HI = "तिरुक्कुरल अभ्यास करें"
    ORGANISER = "Central Institute of Classical Tamil (CICT), Chennai"
    MINISTRY = "Ministry of Education, Government of India"
    BASE_URL = _env("KTS_BASE_URL", "http://localhost:8905")
    DEFAULT_LANG = "en"
    LANGS = ("en", "ta", "hi")

    # ---- mail (optional) ------------------------------------------------
    # If SMTP is not configured, every message is kept in the outbox table
    # and can be read by administrators from the console.
    SMTP_HOST = _env("KTS_SMTP_HOST")
    SMTP_PORT = int(_env("KTS_SMTP_PORT", "587"))
    SMTP_USER = _env("KTS_SMTP_USER")
    SMTP_PASSWORD = _env("KTS_SMTP_PASSWORD")
    SMTP_FROM = _env("KTS_SMTP_FROM", "kts5@cict.in")
    SMTP_TLS = _env("KTS_SMTP_TLS", "1") == "1"

    # ---- first administrator -------------------------------------------
    # Created on first start if no user exists. Change the password at once.
    ADMIN_EMAIL = _env("KTS_ADMIN_EMAIL", "admin@kts5.local")
    ADMIN_PASSWORD = _env("KTS_ADMIN_PASSWORD", "Admin@KTS5")

    # ---- rate limiting (in-process, per IP) -----------------------------
    RATE_REGISTER_PER_HOUR = 5
    RATE_LOGIN_PER_15MIN = 12

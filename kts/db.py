"""
SQLite persistence for the KTS 5.0 portal.

One connection per request (stored on flask.g), WAL journal so that the
admin console and the public site never block each other, and a schema that
is created on first start. Migrations are additive: add a column below and
`_ensure_columns` applies it to existing databases.
"""
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g
from werkzeug.security import check_password_hash, generate_password_hash

from config import DEFAULT_BASE_URL

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '',
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS agencies (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT UNIQUE NOT NULL,
    name         TEXT NOT NULL,
    short_name   TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'institute',
    role_desc    TEXT NOT NULL DEFAULT '',
    contact_name TEXT DEFAULT '',
    email        TEXT DEFAULT '',
    phone        TEXT DEFAULT '',
    website      TEXT DEFAULT '',
    sort_order   INTEGER NOT NULL DEFAULT 100,
    active       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'viewer',
    agency_id     INTEGER REFERENCES agencies(id),
    phone         TEXT DEFAULT '',
    active        INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS applications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    app_no          TEXT UNIQUE,
    status          TEXT NOT NULL DEFAULT 'submitted',
    -- personal
    full_name       TEXT NOT NULL,
    gender          TEXT NOT NULL,
    dob             TEXT NOT NULL,
    category        TEXT DEFAULT '',
    pwd             INTEGER NOT NULL DEFAULT 0,
    -- contact
    mobile          TEXT NOT NULL,
    whatsapp        TEXT DEFAULT '',
    email           TEXT NOT NULL,
    address         TEXT DEFAULT '',
    state           TEXT NOT NULL,
    district        TEXT DEFAULT '',
    pincode         TEXT DEFAULT '',
    -- institution
    college_name    TEXT NOT NULL,
    college_key     TEXT NOT NULL,
    aishe_code      TEXT DEFAULT '',
    college_type    TEXT DEFAULT '',
    college_state   TEXT DEFAULT '',
    college_district TEXT DEFAULT '',
    university      TEXT DEFAULT '',
    course_level    TEXT DEFAULT '',
    discipline      TEXT DEFAULT '',
    year_of_study   TEXT DEFAULT '',
    roll_no         TEXT DEFAULT '',
    -- language
    mother_tongue   TEXT DEFAULT '',
    pref_lang       TEXT NOT NULL,
    tamil_level     TEXT DEFAULT '',
    kural_level     TEXT DEFAULT '',
    -- mentor
    mentor_name     TEXT DEFAULT '',
    mentor_designation TEXT DEFAULT '',
    mentor_email    TEXT DEFAULT '',
    mentor_phone    TEXT DEFAULT '',
    -- files
    photo_path      TEXT DEFAULT '',
    idproof_path    TEXT DEFAULT '',
    -- workflow
    remarks         TEXT DEFAULT '',
    verified_by     INTEGER REFERENCES users(id),
    verified_at     TEXT,
    exam_score      REAL,
    exam_rank       INTEGER,
    ip              TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_app_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_app_state ON applications(state);
CREATE INDEX IF NOT EXISTS idx_app_college ON applications(college_key);
CREATE INDEX IF NOT EXISTS idx_app_email ON applications(email);
CREATE INDEX IF NOT EXISTS idx_app_mobile ON applications(mobile);

CREATE TABLE IF NOT EXISTS questions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lang        TEXT NOT NULL,
    qtype       TEXT NOT NULL DEFAULT 'gk',
    text        TEXT NOT NULL,
    opt_a       TEXT NOT NULL,
    opt_b       TEXT NOT NULL,
    opt_c       TEXT NOT NULL,
    opt_d       TEXT NOT NULL,
    correct     TEXT NOT NULL,
    kural_no    INTEGER,
    difficulty  INTEGER NOT NULL DEFAULT 1,
    source      TEXT NOT NULL DEFAULT 'manual',
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_q_lang ON questions(lang, active);

CREATE TABLE IF NOT EXISTS exam_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id  INTEGER NOT NULL UNIQUE REFERENCES applications(id),
    lang            TEXT NOT NULL,
    paper_json      TEXT NOT NULL,
    answers_json    TEXT NOT NULL DEFAULT '{}',
    started_at      TEXT NOT NULL,
    deadline_at     TEXT NOT NULL,
    submitted_at    TEXT,
    status          TEXT NOT NULL DEFAULT 'in_progress',
    score           REAL,
    correct_count   INTEGER,
    time_taken_sec  INTEGER,
    ip              TEXT DEFAULT '',
    user_agent      TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS merit_list (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rank            INTEGER NOT NULL,
    application_id  INTEGER NOT NULL REFERENCES applications(id),
    score           REAL NOT NULL,
    college_key     TEXT NOT NULL,
    outcome         TEXT NOT NULL,
    run_id          TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT 'general',
    lang        TEXT NOT NULL DEFAULT 'en',
    pinned      INTEGER NOT NULL DEFAULT 0,
    published   INTEGER NOT NULL DEFAULT 1,
    publish_at  TEXT,
    attachment  TEXT DEFAULT '',
    link        TEXT DEFAULT '',
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT 'link',
    lang        TEXT NOT NULL DEFAULT '',
    url         TEXT DEFAULT '',
    file_path   TEXT DEFAULT '',
    file_name   TEXT DEFAULT '',
    file_size   INTEGER DEFAULT 0,
    thumbnail   TEXT DEFAULT '',
    published   INTEGER NOT NULL DEFAULT 1,
    featured    INTEGER NOT NULL DEFAULT 0,
    sort_order  INTEGER NOT NULL DEFAULT 100,
    downloads   INTEGER NOT NULL DEFAULT 0,
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL DEFAULT 'general',
    lang        TEXT NOT NULL DEFAULT '',
    starts_at   TEXT NOT NULL,
    ends_at     TEXT,
    venue       TEXT DEFAULT '',
    link        TEXT DEFAULT '',
    agency_id   INTEGER REFERENCES agencies(id),
    published   INTEGER NOT NULL DEFAULT 1,
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    workstream  TEXT NOT NULL DEFAULT 'general',
    agency_id   INTEGER REFERENCES agencies(id),
    assignee_id INTEGER REFERENCES users(id),
    status      TEXT NOT NULL DEFAULT 'open',
    priority    TEXT NOT NULL DEFAULT 'normal',
    due_date    TEXT,
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_agency ON tasks(agency_id, status);

CREATE TABLE IF NOT EXISTS task_updates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id),
    user_id     INTEGER REFERENCES users(id),
    note        TEXT NOT NULL DEFAULT '',
    old_status  TEXT DEFAULT '',
    new_status  TEXT DEFAULT '',
    attachment  TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    agency_id   INTEGER REFERENCES agencies(id),
    visibility  TEXT NOT NULL DEFAULT 'all',
    file_path   TEXT NOT NULL,
    file_name   TEXT NOT NULL,
    file_size   INTEGER NOT NULL DEFAULT 0,
    uploaded_by INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    phone       TEXT DEFAULT '',
    subject     TEXT NOT NULL,
    body        TEXT NOT NULL,
    topic       TEXT NOT NULL DEFAULT 'general',
    handled     INTEGER NOT NULL DEFAULT 0,
    reply_note  TEXT DEFAULT '',
    ip          TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    to_addr     TEXT NOT NULL,
    subject     TEXT NOT NULL,
    body        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'queued',
    error       TEXT DEFAULT '',
    created_at  TEXT NOT NULL,
    sent_at     TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    actor       TEXT NOT NULL DEFAULT '',
    action      TEXT NOT NULL,
    entity      TEXT NOT NULL DEFAULT '',
    entity_id   INTEGER,
    detail      TEXT NOT NULL DEFAULT '',
    ip          TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(created_at);
"""

# Columns added after the first release: (table, column, DDL type/default)
LATER_COLUMNS = [
    ("applications", "withdrawn_at", "TEXT"),
    ("applications", "admit_card_no", "TEXT"),
]

# CICT on social media: (setting, name of the service, address). The links stand in the footer of
# every page and on the contact page; an administrator can change an address or empty it (the
# link then disappears) under Settings.
SOCIAL_LINKS = [
    ("social.x", "X", "https://x.com/cictofficial"),
    ("social.instagram", "Instagram", "https://instagram.com/cict_chennai/"),
    ("social.youtube", "YouTube", "https://youtube.com/@cicttamil"),
    ("social.facebook", "Facebook", "https://facebook.com/chennaicict"),
    ("social.threads", "Threads", "https://threads.com/@cict_chennai"),
    ("social.whatsapp", "WhatsApp", "https://whatsapp.com/channel/0029Vb0wjUvGOj9r7LmmgU0e"),
    ("social.linkedin", "LinkedIn", "https://linkedin.com/in/central-institute-of-classical-tamil-chennai-1b735a367/"),
    ("social.telegram", "Telegram", "https://t.me/Classicaltamil"),
    ("social.arattai", "Arattai", "https://aratt.ai/@cict_chennai"),
]

# The nodal officers of KTS 5.0 at CICT, shown on the contact page under the institute. Each has
# four settings (name, designation, e-mail, phone) that an administrator can change; an officer
# whose name is empty is not shown.
NODAL_OFFICERS = [
    ("nodal.1", {"name": "Dr. R. Bhuvaneshwari", "designation": "Registrar", "email": "registrar@cict.in", "phone": "9790325518"}),
    ("nodal.2", {"name": "Dr. R. Akilan", "designation": "Programmer", "email": "akilan.r@cict.in", "phone": "9965734497"}),
]
NODAL_FIELDS = [("name", "Name"), ("designation", "Designation"), ("email", "E-mail"), ("phone", "Phone")]

DEFAULT_SETTINGS = {
    "site.banner": "Applications for KTS 5.0 — Thirukkural Payilvom are open. One student from every college in India.",
    "site.banner_on": "1",
    "reg.open": "1",
    "reg.start": "2026-09-25",
    "reg.end": "2026-11-15",
    "exam.date": "2026-11-29",
    "exam.start_time": "11:00",
    "exam.end_time": "12:00",
    "exam.duration_min": "30",
    "exam.questions": "50",
    "exam.marks_per_q": "2",
    "exam.negative": "0",
    "exam.show_score": "1",
    "exam.open": "auto",
    "exam.instructions_url": "",
    "merit.published": "0",
    "merit.select_count": "1000",
    "merit.wait_count": "300",
    "merit.note": "",
    "orientation.note": "Language-wise online orientation sessions (10 lectures + 20-minute live Q&A) will be scheduled after the merit list is published.",
    "contact.email": "office@cict.in",
    "contact.phone": "044-22540125",
    "contact.address": "Central Institute of Classical Tamil (CICT) – Main Office, Chemmozhi Salai, Perumbakkam, Chennai – 600100, India",
    **{key: address for key, _name, address in SOCIAL_LINKS},
    **{f"{prefix}.{field}": value for prefix, officer in NODAL_OFFICERS for field, value in officer.items()},
    "stats.public": "1",
    "site.draft_note_on": "1",
    "home.pm_on": "1",
    "home.pm_quote": "Kashi Tamil Sangamam furthers the spirit of \u2018Ek Bharat, Shreshtha Bharat\u2019.",
    "home.pm_quote_by": "Hon\u2019ble Prime Minister Shri Narendra Modi",
    "home.pm_caption": "Hon\u2019ble Prime Minister Shri Narendra Modi presenting the Russian translation of the Thirukkural to the President of Russia, Mr Vladimir Putin, at the BRICS Summit 2026, Bharat Mandapam, New Delhi.",
}


# Defaults of earlier versions. A database that still holds one of them, unchanged by the
# administrator, receives the present default when the portal starts.
RETIRED_DEFAULTS = {
    "contact.email": ["kts5@cict.in"],
    "contact.phone": ["+91-44-2254 2781"],
    "contact.address": ["Central Institute of Classical Tamil, 40 Institutional Area, Taramani, Chennai 600 113"],
    # the pattern of the test up to version 1.1.0: 25 questions of 4 marks, now 50 of 2 (100 marks either way)
    "exam.questions": ["25"],
    "exam.marks_per_q": ["4"],
}


# Roles of agencies as earlier versions seeded them (data/agencies.json of that time).
RETIRED_AGENCY_ROLES = {
    "CICT": ["Implementing institute for KTS 5.0: runs this portal, the student registration and selection, the 21-language orientation, the digital repository and all Thirukkural content."],
}


# The first password of the versions before 1.1.0. It was published in the README of the portal,
# so anybody may know it. It is kept here for one purpose only: to find accounts that still use
# it. They receive a new password when the portal starts (see _first_passwords).
RETIRED_FIRST_PASSWORD = "Admin@KTS5"

# Account and first password of the first administrator, in the instance folder.
FIRST_ADMIN_FILE = "first-admin.txt"

# Key in the table settings: every active account of this database has been compared with the
# retired password. It belongs to no group of the settings page.
FIRST_PASSWORDS_CHECKED = "security.first_passwords_checked"

# for passwords made by the portal: without 0 O 1 l I, which are easily confused
PASSWORD_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_db():
    if "db" not in g:
        path = current_app.config["DATABASE"]
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), detect_types=0, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        g.db = conn
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    conn = get_db()
    cur = conn.execute(sql, args)
    conn.commit()
    return cur.lastrowid


def executemany(sql, rows):
    conn = get_db()
    conn.executemany(sql, rows)
    conn.commit()


# ---- settings ---------------------------------------------------------------

def get_setting(key, default=""):
    row = query("SELECT value FROM settings WHERE key = ?", (key,), one=True)
    if row is None:
        return DEFAULT_SETTINGS.get(key, default)
    return row["value"]


def all_settings():
    data = dict(DEFAULT_SETTINGS)
    for row in query("SELECT key, value FROM settings"):
        data[row["key"]] = row["value"]
    return data


def nodal_officers():
    """The nodal officers with a name, as dicts name/designation/email/phone, in their order."""
    settings = all_settings()
    officers = []
    for prefix, _officer in NODAL_OFFICERS:
        officer = {field: (settings.get(f"{prefix}.{field}") or "").strip() for field, _label in NODAL_FIELDS}
        if officer["name"]:
            officers.append(officer)
    return officers


def social_links():
    """[(name, address), ...] of CICT on social media: the settings that hold a web address, in their order."""
    settings = all_settings()
    links = []
    for key, name, _address in SOCIAL_LINKS:
        address = (settings.get(key) or "").strip()
        # only a web address becomes a link, whatever was typed into the setting
        if address.lower().startswith(("https://", "http://")):
            links.append((name, address))
    return links


def set_setting(key, value):
    execute(
        "INSERT INTO settings(key, value, updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value, utcnow()),
    )


# ---- audit ------------------------------------------------------------------

def audit(action, entity="", entity_id=None, detail="", user=None, ip=""):
    if isinstance(detail, (dict, list)):
        detail = json.dumps(detail, ensure_ascii=False)
    execute(
        "INSERT INTO audit_log(user_id, actor, action, entity, entity_id, detail, ip, created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (
            user["id"] if user else None,
            user["email"] if user else "public",
            action, entity, entity_id, detail or "", ip or "", utcnow(),
        ),
    )


# ---- schema / seed ----------------------------------------------------------

def _ensure_columns(conn):
    for table, column, ddl in LATER_COLUMNS:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def new_password(length=16):
    """A random password with a capital letter, a small letter and a digit."""
    while True:
        word = "".join(secrets.choice(PASSWORD_LETTERS) for _ in range(length))
        if any(c.isupper() for c in word) and any(c.islower() for c in word) and any(c.isdigit() for c in word):
            return word


def first_admin_file(app):
    return Path(app.config["INSTANCE_DIR"]) / FIRST_ADMIN_FILE


def _first_admin_lines(app):
    try:
        return first_admin_file(app).read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return []


def read_first_admin(app):
    """[(e-mail, password), ...] as written in instance/first-admin.txt; empty without the file."""
    accounts, email = [], None
    for line in _first_admin_lines(app):
        label, _, value = line.partition(":")
        if label.strip() == "E-mail":
            email = value.strip()
        elif label.strip() == "Password" and email:
            accounts.append((email, value.strip()))
            email = None
    return accounts


def _address_is_set(app):
    """False at a start without KTS_BASE_URL: the portal then knows the built-in address only."""
    return app.config["BASE_URL"].rstrip("/") != DEFAULT_BASE_URL


def _sign_in_page(app):
    """
    The sign-in page as instance/first-admin.txt names it. The built-in address is not written:
    for whoever reads the file on the server it names a page that does not exist.
    """
    if not _address_is_set(app):
        return "the address of the portal, followed by /console/login"
    return f"{app.config['BASE_URL'].rstrip('/')}/console/login"


def _sign_in_page_of_the_file(app):
    """What instance/first-admin.txt says after 'Sign-in page:'; None without the file or the line."""
    for line in _first_admin_lines(app):
        label, _, value = line.partition(":")
        if label.strip() == "Sign-in page":
            return value.strip()
    return None


def write_first_admin(app, accounts):
    """
    Write instance/first-admin.txt for the accounts [(e-mail, password), ...]. Without an account
    the file is removed.
    """
    path = first_admin_file(app)
    if not accounts:
        if path.exists():
            path.unlink()
        return path
    lines = ["Kashi Tamil Sangamam 5.0 portal: first sign-in of the administrator", "",
             f"Sign-in page: {_sign_in_page(app)}"]
    for email, password in accounts:
        lines += ["", f"E-mail:   {email}", f"Password: {password}"]
    lines += ["", "The portal asks for a new password at once after the first sign-in.",
              "It removes this file when the new password has been set."]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("\r\n".join(lines) + "\r\n")
    return path


def forget_first_admin(app, email):
    """After a change of password: the account leaves the file; the file goes with its last account."""
    accounts = read_first_admin(app)
    if any(e.lower() == email.lower() for e, _p in accounts):
        write_first_admin(app, [(e, p) for e, p in accounts if e.lower() != email.lower()])


def _has_password(pwhash, password):
    """
    check_password_hash for the start of the portal, where the accounts of the database are
    compared one after the other: a hash that cannot be compared (written by other means, with
    a method that the library does not know) is the hash of no password and stops nothing.
    """
    try:
        return check_password_hash(pwhash, password)
    except (ValueError, TypeError):
        return False


def _awaits_first_sign_in(conn, email, password):
    row = conn.execute("SELECT password_hash FROM users WHERE email = ? AND active = 1 "
                       "AND must_change_password = 1", (email.lower(),)).fetchone()
    return row is not None and _has_password(row["password_hash"], password)


def _first_passwords(app, conn, now):
    """
    Create the first administrator when there is no user, and take the published password of
    earlier versions away from accounts that still have it. A password made here is written to
    instance/first-admin.txt, never to the log. The file is written anew as well when it names
    another sign-in page than the portal has at this start.

    A file that cannot be written or removed does not stop the start, with one exception: a
    password made for the very first account has no other place.
    """
    configured = app.config.get("ADMIN_PASSWORD")
    if configured == RETIRED_FIRST_PASSWORD:
        app.logger.warning("KTS_ADMIN_PASSWORD holds the password that was published with earlier "
                           "versions of the portal. It is not used.")
        configured = None

    issued, first = [], False
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        first = True
        email = app.config["ADMIN_EMAIL"].lower()
        password = configured or new_password()
        conn.execute(
            "INSERT INTO users(email, name, password_hash, role, active, must_change_password, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (email, "Portal Administrator", generate_password_hash(password), "superadmin", 1, 1, now),
        )
        if configured:
            app.logger.warning("Created first administrator %s with the password of KTS_ADMIN_PASSWORD. "
                               "Sign in and change it immediately.", email)
        else:
            issued.append((email, password))
    elif not configured:
        # inside the transaction of init_db: what follows can be undone by itself
        conn.execute("SAVEPOINT first_passwords")
        # The change form of earlier versions accepted the password of before, so an account may
        # have kept the published password with must_change_password = 0. Comparing costs time:
        # every active account is compared once for each database, afterwards only the accounts
        # that await their first sign-in.
        checked = conn.execute("SELECT 1 FROM settings WHERE key = ?", (FIRST_PASSWORDS_CHECKED,)).fetchone()
        rows = conn.execute("SELECT id, email, password_hash FROM users WHERE active = 1"
                            + (" AND must_change_password = 1" if checked else "")).fetchall()
        for row in rows:
            if _has_password(row["password_hash"], RETIRED_FIRST_PASSWORD):
                password = new_password()
                # never one without the other: the file keeps an account that must change its password
                conn.execute("UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
                             (generate_password_hash(password), row["id"]))
                conn.execute(
                    "INSERT INTO audit_log(user_id, actor, action, entity, entity_id, detail, ip, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (None, "portal", "first_password_rotated", "user", row["id"], row["email"], "", now),
                )
                issued.append((row["email"], password))
        if not checked:
            # after the savepoint: a file that cannot be written takes the mark back as well
            conn.execute("INSERT INTO settings(key, value, updated_at) VALUES(?,?,?)",
                         (FIRST_PASSWORDS_CHECKED, "1", now))

    # What the file says about other accounts stays as long as it is true.
    written = read_first_admin(app)
    named = {email.lower() for email, _p in issued}
    kept = [(e, p) for e, p in written if e.lower() not in named and _awaits_first_sign_in(conn, e, p)]
    # A file of a start without KTS_BASE_URL, or of the portal under another address: a start
    # that knows the address writes it anew, with the same accounts and passwords. Never the
    # other way round: manage.py run by hand must not take the address out of the file.
    renew = bool(kept) and _address_is_set(app) and _sign_in_page_of_the_file(app) != _sign_in_page(app)
    if issued or kept != written or renew:
        try:
            path = write_first_admin(app, kept + issued)
        except OSError as exc:
            if first and issued:
                raise
            if issued:
                # a password that is written nowhere is of no use: the accounts stay as they were
                # and the next start tries again
                conn.execute("ROLLBACK TO first_passwords")
                issued = []
                app.logger.warning("%s could not be written (%s): no account received a new first password "
                                   "at this start; an account that still has the published password keeps it.",
                                   first_admin_file(app), exc)
            else:
                app.logger.warning("%s could not be brought up to date (%s).", first_admin_file(app), exc)
    for email, _p in issued:
        app.logger.warning("Account %s: the first password is in the file %s. The portal asks for a new "
                           "password at the first sign-in and then removes the file.", email, path)


def init_db(app):
    """Create tables, apply additive migrations and seed reference data."""
    path = app.config["DATABASE"]
    path.parent.mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    _ensure_columns(conn)
    now = utcnow()

    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)",
            (key, value, now),
        )
    for key, old_values in RETIRED_DEFAULTS.items():
        for old in old_values:
            conn.execute("UPDATE settings SET value = ?, updated_at = ? WHERE key = ? AND value = ?",
                         (DEFAULT_SETTINGS[key], now, key, old))

    if conn.execute("SELECT COUNT(*) FROM agencies").fetchone()[0] == 0:
        seed_path = app.config["DATA_DIR"] / "agencies.json"
        if seed_path.exists():
            agencies = json.loads(seed_path.read_text(encoding="utf-8"))
            for i, a in enumerate(agencies):
                conn.execute(
                    "INSERT INTO agencies(code, name, short_name, kind, role_desc, website, sort_order) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (a["code"], a["name"], a["short"], a["kind"], a["role"], a.get("website", ""), (i + 1) * 10),
                )

    # Entries of the repository that every installation carries (data/resources.json). Each is put
    # in once for each database, so an entry that an administrator has deleted does not come back,
    # and not at all when an entry with the same address is there already.
    seed_path = app.config["DATA_DIR"] / "resources.json"
    if seed_path.exists():
        for r in json.loads(seed_path.read_text(encoding="utf-8")):
            mark = f"seed.resource.{r['key']}"
            if conn.execute("SELECT 1 FROM settings WHERE key = ?", (mark,)).fetchone():
                continue
            if not conn.execute("SELECT 1 FROM resources WHERE url = ?", (r["url"],)).fetchone():
                conn.execute(
                    "INSERT INTO resources(title, description, category, lang, url, published, featured, sort_order, "
                    "created_at, updated_at) VALUES(?,?,?,?,?,1,?,?,?,?)",
                    (r["title"], r["description"], r["category"], r.get("lang", ""), r["url"],
                     r.get("featured", 0), r.get("sort_order", 100), now, now),
                )
            conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", (mark, "1", now))

    # The role of an agency as seeded by an earlier version becomes the present wording, so that
    # the partner page keeps finding its translation; wording changed in the console is left alone.
    seed_path = app.config["DATA_DIR"] / "agencies.json"
    if seed_path.exists():
        roles = {a["code"]: a["role"] for a in json.loads(seed_path.read_text(encoding="utf-8"))}
        for code, old_roles in RETIRED_AGENCY_ROLES.items():
            for old in old_roles:
                if roles.get(code):
                    conn.execute("UPDATE agencies SET role_desc = ? WHERE code = ? AND role_desc = ?", (roles[code], code, old))

    try:
        _first_passwords(app, conn, now)
        conn.commit()
    finally:
        conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)
    init_db(app)

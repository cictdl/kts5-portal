"""
SQLite persistence for the KTS 5.0 portal.

One connection per request (stored on flask.g), WAL journal so that the
admin console and the public site never block each other, and a schema that
is created on first start. Migrations are additive: add a column below and
`_ensure_columns` applies it to existing databases.
"""
import json
import sqlite3
from datetime import datetime, timezone

from flask import current_app, g
from werkzeug.security import generate_password_hash

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
    "exam.questions": "25",
    "exam.marks_per_q": "4",
    "exam.negative": "0",
    "exam.show_score": "1",
    "exam.open": "auto",
    "exam.instructions_url": "",
    "merit.published": "0",
    "merit.select_count": "1000",
    "merit.wait_count": "300",
    "merit.note": "",
    "orientation.note": "Language-wise online orientation sessions (10 lectures + 20-minute live Q&A) will be scheduled after the merit list is published.",
    "contact.email": "kts5@cict.in",
    "contact.phone": "+91-44-2254 2781",
    "contact.address": "Central Institute of Classical Tamil, 40 Institutional Area, Taramani, Chennai 600 113",
    "stats.public": "1",
}


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

    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO users(email, name, password_hash, role, active, must_change_password, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                app.config["ADMIN_EMAIL"].lower(),
                "Portal Administrator",
                generate_password_hash(app.config["ADMIN_PASSWORD"]),
                "superadmin", 1, 1, now,
            ),
        )
        app.logger.warning(
            "Created first administrator %s with the configured default password. "
            "Sign in and change it immediately.", app.config["ADMIN_EMAIL"],
        )

    conn.commit()
    conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)
    init_db(app)

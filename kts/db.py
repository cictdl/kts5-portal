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

-- the participating Higher Educational Institutions of the States/UTs (1.2.41, kts/heis.py)
CREATE TABLE IF NOT EXISTS institutions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ref              TEXT UNIQUE,
    name             TEXT NOT NULL,
    itype            TEXT NOT NULL DEFAULT '',
    state            TEXT NOT NULL,
    district         TEXT NOT NULL DEFAULT '',
    aishe_code       TEXT NOT NULL DEFAULT '',
    inst_key         TEXT NOT NULL,
    head_name        TEXT NOT NULL DEFAULT '',
    head_designation TEXT NOT NULL DEFAULT '',
    head_email       TEXT NOT NULL DEFAULT '',
    head_phone       TEXT NOT NULL DEFAULT '',
    coord_name       TEXT NOT NULL DEFAULT '',
    coord_email      TEXT NOT NULL DEFAULT '',
    coord_mobile     TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'pending',
    decision_note    TEXT NOT NULL DEFAULT '',
    decided_by       INTEGER,
    decided_at       TEXT,
    ip               TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_institutions_state ON institutions(state, status);
CREATE INDEX IF NOT EXISTS idx_institutions_key ON institutions(inst_key);

-- the online assessment of the participating institutions (1.2.43, kts/campus.py)
CREATE TABLE IF NOT EXISTS campus_students (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id  INTEGER NOT NULL REFERENCES institutions(id),
    name            TEXT NOT NULL,
    email           TEXT NOT NULL DEFAULT '',
    mobile          TEXT NOT NULL DEFAULT '',
    roll_no         TEXT NOT NULL DEFAULT '',
    course          TEXT NOT NULL DEFAULT '',
    lang            TEXT NOT NULL DEFAULT 'en',
    source          TEXT NOT NULL DEFAULT 'online',
    created_at      TEXT NOT NULL,
    ip              TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_campus_students_inst ON campus_students(institution_id);
CREATE TABLE IF NOT EXISTS campus_attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      INTEGER NOT NULL UNIQUE REFERENCES campus_students(id),
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

-- the video recording of the one-hour presentation of each institution's selected student, submitted by the institution as a link
-- (1.2.158; Annexure-III C-4 of the D.O. letter of 31 October 2026): submitted, then accepted or returned by CICT
CREATE TABLE IF NOT EXISTS presentations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id  INTEGER NOT NULL UNIQUE REFERENCES institutions(id),
    application_id  INTEGER REFERENCES applications(id),
    title           TEXT NOT NULL,
    held_on         TEXT NOT NULL,
    minutes         INTEGER NOT NULL,
    audience        INTEGER,
    video_url       TEXT NOT NULL,
    material_url    TEXT NOT NULL DEFAULT '',
    note            TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'submitted',
    review_note     TEXT NOT NULL DEFAULT '',
    reviewed_by     INTEGER,
    reviewed_at     TEXT,
    submitted_at    TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    ip              TEXT NOT NULL DEFAULT ''
);

-- the reminders mailed to the participating institutions, each once (1.2.52, kts/progress.py)
CREATE TABLE IF NOT EXISTS institution_reminders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id  INTEGER NOT NULL REFERENCES institutions(id),
    kind            TEXT NOT NULL,
    sent_at         TEXT NOT NULL,
    sent_by         INTEGER,
    UNIQUE(institution_id, kind)
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

-- Stipend: the bank details of a selected student, one row for each application. The account
-- number and the Aadhaar number are sealed (kts/secure.py); in plain text stand their last four
-- digits only. account_hash is the keyed look-up value that finds one account given twice.
CREATE TABLE IF NOT EXISTS bank_details (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id  INTEGER NOT NULL UNIQUE REFERENCES applications(id),
    holder_name     TEXT NOT NULL,
    account_enc     TEXT NOT NULL,
    account_last4   TEXT NOT NULL,
    account_hash    TEXT NOT NULL,
    ifsc            TEXT NOT NULL,
    bank_name       TEXT NOT NULL,
    branch          TEXT NOT NULL DEFAULT '',
    account_type    TEXT NOT NULL DEFAULT 'savings',
    aadhaar_enc     TEXT NOT NULL DEFAULT '',
    aadhaar_last4   TEXT NOT NULL DEFAULT '',
    proof_path      TEXT NOT NULL DEFAULT '',
    proof_name      TEXT NOT NULL DEFAULT '',
    proof_size      INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'submitted',
    remark          TEXT NOT NULL DEFAULT '',
    submitted_at    TEXT NOT NULL,
    reviewed_by     INTEGER REFERENCES users(id),
    reviewed_at     TEXT,
    paid_ref        TEXT NOT NULL DEFAULT '',
    paid_on         TEXT NOT NULL DEFAULT '',
    paid_by         INTEGER REFERENCES users(id),
    ip              TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bank_status ON bank_details(status);
CREATE INDEX IF NOT EXISTS idx_bank_account ON bank_details(account_hash);

-- Stipend: every payment list (the export of the entries approved and not yet paid) as it went
-- out: the entries in it, each with its updated_at, as JSON [[id, updated_at], ...], and the
-- amount per student of that day (column amount, added in LATER_COLUMNS). 'Paid' for a list
-- marks those entries only, and only those that have not changed since, at that amount; the
-- list is then settled (paid_ref 'discarded' for a list that never went to the bank). No number
-- of an account stands here.
CREATE TABLE IF NOT EXISTS stipend_batches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entries     TEXT NOT NULL,
    rows        INTEGER NOT NULL,
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL,
    paid_ref    TEXT NOT NULL DEFAULT '',
    paid_on     TEXT NOT NULL DEFAULT '',
    settled_at  TEXT
);

-- Classroom quiz (kts/quiz.py): a live quiz that a host shows on a projector and a class answers
-- on phones. The questions are made when the quiz is created and kept here as JSON; the times of
-- the question on the screens are milliseconds of the server clock. players counts those who
-- joined, and stays when their names and answers are deleted after 30 days.
CREATE TABLE IF NOT EXISTS quiz_rooms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL,
    host_kind   TEXT NOT NULL,
    host_id     INTEGER NOT NULL,
    host_name   TEXT NOT NULL DEFAULT '',
    lang        TEXT NOT NULL,
    scope       TEXT NOT NULL DEFAULT 'all',
    seconds     INTEGER NOT NULL DEFAULT 30,
    questions   TEXT NOT NULL,
    phase       TEXT NOT NULL DEFAULT 'lobby',
    q_index     INTEGER NOT NULL DEFAULT -1,
    q_start_ms  INTEGER,
    q_end_ms    INTEGER,
    players     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    created_ms  INTEGER NOT NULL,
    ended_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_quiz_code ON quiz_rooms(code, ended_at);
CREATE INDEX IF NOT EXISTS idx_quiz_host ON quiz_rooms(host_kind, host_id);

CREATE TABLE IF NOT EXISTS quiz_players (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id     INTEGER NOT NULL REFERENCES quiz_rooms(id),
    token       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    score       INTEGER NOT NULL DEFAULT 0,
    right_count INTEGER NOT NULL DEFAULT 0,
    time_ms     INTEGER NOT NULL DEFAULT 0,
    removed     INTEGER NOT NULL DEFAULT 0,
    joined_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quiz_players ON quiz_players(room_id, removed);

CREATE TABLE IF NOT EXISTS quiz_answers (
    room_id     INTEGER NOT NULL,
    player_id   INTEGER NOT NULL REFERENCES quiz_players(id) ON DELETE CASCADE,
    q_index     INTEGER NOT NULL,
    choice      INTEGER NOT NULL,
    correct     INTEGER NOT NULL,
    points      INTEGER NOT NULL,
    ms          INTEGER NOT NULL,
    PRIMARY KEY (player_id, q_index)
);
CREATE INDEX IF NOT EXISTS idx_quiz_answers ON quiz_answers(room_id, q_index);

-- The student delegates who attended the inauguration of KTS 5.0 online (kts/certificate.py):
-- recorded by the student with the code announced during the live stream (via 'code'), or by
-- staff from a list of application numbers (via 'staff'). Each receives a certificate of
-- participation.
CREATE TABLE IF NOT EXISTS inaug_attendance (
    application_id INTEGER PRIMARY KEY REFERENCES applications(id),
    via         TEXT NOT NULL,
    marked_at   TEXT NOT NULL,
    marked_by   INTEGER REFERENCES users(id)
);

-- Research papers of the student delegates (kts/papers.py): one per application, the file sent
-- last, its version and the review; every file sent stays in paper_files.
CREATE TABLE IF NOT EXISTS papers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL UNIQUE REFERENCES applications(id),
    title         TEXT NOT NULL,
    lang          TEXT NOT NULL,
    abstract      TEXT NOT NULL,
    keywords      TEXT NOT NULL DEFAULT '',
    couplets      TEXT NOT NULL DEFAULT '',
    mentor_name   TEXT NOT NULL DEFAULT '',
    mentor_designation TEXT NOT NULL DEFAULT '',
    mentor_email  TEXT NOT NULL DEFAULT '',
    file_path     TEXT NOT NULL,
    file_name     TEXT NOT NULL,
    file_size     INTEGER NOT NULL,
    version       INTEGER NOT NULL DEFAULT 1,
    status        TEXT NOT NULL DEFAULT 'submitted',
    score         INTEGER,
    remarks       TEXT NOT NULL DEFAULT '',
    reviewed_by   INTEGER REFERENCES users(id),
    reviewed_at   TEXT,
    submitted_at  TEXT NOT NULL,
    first_submitted_at TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status);

-- Gallery (kts/gallery.py): photographs in albums (the album is the event named on them), the
-- files in uploads/gallery/, served at /files/gallery/ when published.
-- the visitors of a day, counted without keeping who they were (kts/visits.py, 1.2.31)
CREATE TABLE IF NOT EXISTS visit_days (
    day       TEXT PRIMARY KEY,
    visitors  INTEGER NOT NULL DEFAULT 0,
    views     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS gallery_photos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    album       TEXT NOT NULL,
    caption     TEXT NOT NULL DEFAULT '',
    taken_on    TEXT NOT NULL DEFAULT '',
    file_path   TEXT NOT NULL,
    file_name   TEXT NOT NULL,
    file_size   INTEGER NOT NULL,
    published   INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 100,
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gallery_album ON gallery_photos(album, published);

CREATE TABLE IF NOT EXISTS paper_files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id    INTEGER NOT NULL REFERENCES papers(id),
    version     INTEGER NOT NULL,
    file_path   TEXT NOT NULL,
    file_name   TEXT NOT NULL,
    file_size   INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL
);
"""

# Columns added after the first release: (table, column, DDL type/default)
LATER_COLUMNS = [
    ("applications", "withdrawn_at", "TEXT"),
    ("applications", "admit_card_no", "TEXT"),
    # the nomination form signed by the head of the institution, uploaded at registration (1.2.22)
    ("applications", "nomination_path", "TEXT"),
    # the stipend as it was paid: the setting stipend.amount may change afterwards
    ("bank_details", "paid_amount", "INTEGER"),
    # the stipend per student as a payment list went out: the list is paid at that sum, not at the
    # setting of the day it is marked
    ("stipend_batches", "amount", "INTEGER"),
    # the outbox as a queue (kts/mailq.py, 1.2.35): mails to one person (0) before those of a list (1),
    # the attempts made and the moment of the next one
    ("outbox", "priority", "INTEGER NOT NULL DEFAULT 0"),
    ("outbox", "attempts", "INTEGER NOT NULL DEFAULT 0"),
    ("outbox", "next_try", "TEXT"),
    # the States/UTs of a Nodal Officer ('|' between them; 1.2.38)
    ("users", "states", "TEXT NOT NULL DEFAULT ''"),
    # the participating institution that the student chose (1.2.41); empty: "not listed"
    ("applications", "institution_id", "INTEGER"),
    # the institutions identified by the Nodal Institution, their online assessment and their selected student (1.2.43)
    ("institutions", "invite_token", "TEXT"),
    ("institutions", "invited_by", "INTEGER"),
    ("institutions", "test_on", "INTEGER NOT NULL DEFAULT 0"),
    ("institutions", "test_from", "TEXT"),
    ("institutions", "test_to", "TEXT"),
    ("institutions", "test_slug", "TEXT"),
    ("institutions", "test_code", "TEXT"),
    ("institutions", "winner_id", "INTEGER"),
    ("institutions", "winner_at", "TEXT"),
    ("institutions", "reg_token", "TEXT"),
    ("institutions", "application_id", "INTEGER"),
    # the Institutional Coordinator's designation and the Faculty Supervisor/Guide of the institution (1.2.46, Annexure-IV)
    ("institutions", "coord_designation", "TEXT NOT NULL DEFAULT ''"),
    ("institutions", "guide_name", "TEXT NOT NULL DEFAULT ''"),
    ("institutions", "guide_designation", "TEXT NOT NULL DEFAULT ''"),
    ("institutions", "guide_email", "TEXT NOT NULL DEFAULT ''"),
    ("institutions", "guide_mobile", "TEXT NOT NULL DEFAULT ''"),
    # the designation of a Nodal Officer, as the Ministry's format asks (1.2.43)
    ("users", "designation", "TEXT NOT NULL DEFAULT ''"),
    ("users", "signin_reminded_at", "TEXT"),   # the last sign-in reminder to a Nodal Officer who has never signed in (1.2.136)
    # the syllabus of the institution's online assessment (1.2.64): 'all' (the 1,330 couplets) or '108' (the 108 Thirukkural)
    ("institutions", "test_syllabus", "TEXT NOT NULL DEFAULT 'all'"),
    # the marks of the evaluation committee of the Nodal Institution on the six criteria of Annexure-V of the revised D.O. letter
    # (1.2.111): sop_scores a JSON object of the criteria (kts/heis.py SOP), sop_total their sum out of 100
    ("institutions", "sop_scores", "TEXT NOT NULL DEFAULT ''"),
    ("institutions", "sop_total", "INTEGER"),
    ("institutions", "sop_note", "TEXT NOT NULL DEFAULT ''"),
    ("institutions", "sop_by", "INTEGER"),
    ("institutions", "sop_at", "TEXT"),
    # where an institution's registration came from: 'join' when from its State/UT page (1.2.142)
    ("institutions", "source", "TEXT NOT NULL DEFAULT ''"),
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
# The head of the institute, shown in the same way above the nodal officers; the same four settings.
INSTITUTE_HEAD = [
    ("director", {"name": "Prof. R. Chandrasekaran", "designation": "Director", "email": "director@cict.in", "phone": "044-22540125"}),
]

DEFAULT_SETTINGS = {
    "site.banner": "Applications for KTS 5.0 — Thirukkural Payilvom are open. One student from every participating institution.",
    "site.banner_on": "1",
    "reg.open": "1",
    # the dates of the tentative timeline of KTS 5.0 (28.11.2026 – 12.12.2026)
    "reg.start": "2026-10-22",
    # the D.O. letter of the Ministry of 9 October 2026: the institutions register their selected students by 22 October; the
    # revised D.O. letter (26 October 2026): each selected Participating Institution nominates its student by 20 November;
    # the Ministry's revision of 10 November 2026 (1.2.172): on 24 November
    "reg.end": "2026-11-24",
    # the central online test of CICT (1.2.120, the user's "the online exam should be 10-20 november"): open from 10 November
    # 00:00 to 20 November 23:59 IST, at any time in these days
    "exam.date": "2026-11-10",
    "exam.date_to": "2026-11-20",
    "exam.start_time": "00:00",
    "exam.end_time": "23:59",
    "exam.duration_min": "30",
    "exam.questions": "50",
    "exam.marks_per_q": "2",
    "exam.negative": "0",
    "exam.show_score": "1",
    # the central test, retired by the D.O. letter of 9 October 2026 (1.2.43; the institutions assess, kts/campus.py), open
    # again in its days (1.2.120)
    # CICT's central online test (1.2.120), switched off since 1.2.155: the D.O. letter of 31 October 2026 has none (the user, 4 November)
    "exam.open": "0",
    # the central test also for registered students not yet verified (1.2.119; the user's "let unverified registered
    # students take it too", 29 October 2026)
    "exam.unverified": "1",
    "exam.instructions_url": "",
    "merit.published": "0",
    "merit.select_count": "1000",
    "merit.wait_count": "300",
    "merit.note": "",
    # the form for the bank details of the selected students; closed until an administrator opens it
    "stipend.open": "0",
    "stipend.last_date": "",
    "stipend.amount": "10000",
    "stipend.aadhaar": "1",
    # the academic orientation of the revised D.O. letter is CICT's two lectures with their live Q&A (1.2.71, 1.2.111)
    "orientation.note": "CICT holds language-wise online academic orientation sessions (2 lectures + 20-minute live Q&A), with its multilingual study material and educational videos, before the one-month research and academic engagement begins.",
    # the academic orientation by CICT, with the study material and educational videos: by 10 December 2026 (the revised D.O.
    # letter, Annexure-III D)
    "orientation.by": "2026-12-14",
    "contact.email": "office@cict.in",
    "contact.phone": "044-22540125",
    # the address that receives a copy of every message of the contact form (empty: none)
    "contact.notify": "kts@cict.in",
    "contact.address": "Central Institute of Classical Tamil (CICT) – Main Office, Chemmozhi Salai, Perumbakkam, Chennai – 600100, India",
    **{key: address for key, _name, address in SOCIAL_LINKS},
    **{f"{prefix}.{field}": value for prefix, officer in INSTITUTE_HEAD + NODAL_OFFICERS for field, value in officer.items()},
    "kts.start": "2026-11-28",
    # the hour of the inauguration, for the countdown on the home page (empty: 00:00 IST)
    "kts.start_time": "",
    # the launch of the KTS 5.0 web portal and registration by the Hon'ble Minister of Education (1.2.69): registration opens then, the
    # banner announces it before, the home page says it was launched until launch.until; /launch is the stage screen
    "launch.on": "1",
    "launch.at": "2026-10-22T12:00",
    "launch.until": "2026-10-29",
    "kts.end": "2026-12-12",
    "schedule.tentative": "1",
    # every registered student receives a certificate of recognition (kts/certificate.py)
    "cert.on": "1",
    # and every student selected in the published merit list a certificate of merit
    "cert.merit_on": "1",
    # and every student delegate whose attendance at the inauguration (online) is recorded, a
    # certificate of participation; the address of the live stream, and the attendance code that
    # is announced during it (empty: the students cannot record their attendance themselves)
    "cert.inaug_on": "1",
    "inaug.link": "",
    "inaug.code": "",
    # the confirmation letter of the selected students, and the dates of the internship it names
    "letter.on": "1",
    "letter.date": "2026-12-06",
    "internship.start": "2026-12-15",
    "papers.due": "2027-01-14",
    "present.due": "2027-01-14",
    # the research papers (kts/papers.py): auto = from internship.start to papers.due, 1 open, 0 closed;
    # a note and a link to the guidelines, shown above the form
    "papers.open": "auto",
    "papers.note": "",
    "papers.guide_url": "",
    # the classroom quiz (kts/quiz.py): open, hosted also by the selected students, players in one quiz
    "quiz.on": "1",
    "quiz.candidates": "1",
    # anybody may host a classroom quiz, without an account (1.2.30)
    "quiz.public": "1",
    # the Nodal Officers of the States/UTs (1.2.39): verification closes the day before the test
    "verify.end": "2026-12-05",
    "nodal.digest": "1",
    "nodal.digest_time": "08:00",
    # the copies of the database (1.2.40, kts/backup.py)
    "backup.on": "1",
    "backup.times": "02:00, 14:00",
    "backup.keep": "28",
    # the participating institutions (1.2.41, kts/heis.py)
    "hei.open": "1",
    # 18 November 2026 since 1.2.171 (CICT, 10 November 2026); 15 November in the D.O. letter of 31 October
    "hei.end": "2026-11-18",
    "hei.max_per_state": "0",
    # the revised D.O. letter (26 October 2026): the Nodal Institution selects only the number of Participating Institutions
    # that Annexure-I prescribes for its State/UT (data/nodal_heis.json), between the close of registration and this day
    # off since 1.2.178 (CICT, 12 November 2026: "accepted institutions ceiling should not be there"); switched off once on a
    # database of before (migrate.cap_off_1112)
    "hei.cap_annexure": "0",
    "hei.select_end": "2026-11-19",   # 19 November since the Ministry's revision of 10 November 2026 (1.2.172; 16-17 before)
    "hei.public": "1",
    # the reserve list of each row of Annexure-I on /institutions, in the order of the marks, without them (1.2.174)
    "hei.reserve_public": "1",
    # an institution is selected, or put on the reserve list, only once its marks of Annexure-V are recorded (1.2.174); off since
    # 1.2.175, CICT, 12 November 2026: "marks will be added later stage"
    "hei.marks_first": "0",
    # the State/UT pages for the registration of institutions, /join (1.2.142)
    "join.on": "1",
    # the Nodal Officer of each Nodal HEI, with the contact details given for the account, on the public pages (1.2.70)
    "nodal.officers_public": "1",
    # the D.O. letter of 9 October 2026 (1.2.43): registration by the institutions' links; their online assessment
    "reg.by_institution": "1",
    "camp.on": "1",
    "camp.from": "2026-10-22",
    "camp.to": "2026-11-23",   # the assessment by 23 November since the Ministry's revision of 10 November 2026 (1.2.172)
    "camp.show_score": "1",
    # the reminders to the participating institutions that are behind (1.2.52, kts/progress.py)
    "remind.on": "1",
    # the day before the last day of the assessment, that day, and the day of the nomination (1.2.172: 22, 23, 24 November)
    "remind.test_by": "2026-11-22",
    "remind.select_by": "2026-11-23",
    "remind.register_by": "2026-11-24",
    # the practice test for students (1.2.54, kts/practice.py)
    "practice.on": "1",
    "practice.questions": "10",
    "practice.minutes": "6",
    # the Thirukkural study companion (1.2.119, kts/companion.py)
    "companion.on": "1",
    "hei.orientation": "",
    # the sender of mails (kts/mailq.py, 1.2.35): below the 2,000 mails a day of a Google Workspace account
    "mail.daily_limit": "1800",
    "mail.per_minute": "30",
    "mail.paused": "0",
    # the count of visitors in the footer of every page (1.2.31)
    "site.visitors": "1",
    "quiz.max_players": "200",
    "stats.public": "1",
    # the home page (1.2.146): "Find your next step" (the hub of 1.2.140) and the video of the launch of the portal (1.2.69),
    # hidden; '1' shows them again
    "home.hub": "0",
    "home.launch_video": "0",
    # the students' registration on the public pages (1.2.147): hidden - the students are selected through the institutions;
    # /register and /status work either way (for the links sent to the students selected); '1' shows it all again
    "reg.public": "0",
    # the seminars and workshops of CICT on the public pages (1.2.151): hidden; the page /seminars-workshops works either way;
    # '1' shows them again
    "events.public": "0",
    # "Institution-level assessment" in the menu and the footer's quick links (1.2.156, the user, 4 November 2026: "Hide -
    # Institution-level assessment menu items"): hidden; the page /examination works either way; '1' shows them again
    "menu.assessment": "0",
    # CICT's central online test in the schedule and the upcoming events (1.2.152): left out ("Should remove the content ... Central
    # Online Test", CICT, 4 November 2026); '1' puts it back
    "schedule.central_test": "0",
    # the nomination by the Participating Institutions (1.2.154): the personal registration link of the student a Participating
    # Institution has selected opens the form up to reg.end, even while the students' own registration is off; '0' closes it
    "nominate.open": "1",
    # the days for which the newest circular of the Ministry carries a blinking NEW on the home page (1.2.152); 0: never
    "circular.new_days": "30",
    # the newest circular of the Ministry, with its PDF, first in the circular band of the home page (1.2.162, the user, 5 November
    # 2026: "hide: D.O. letter of the Ministry of Education, 31 October 2026"): hidden; the notice stays under Notices; '1' shows it
    "home.circular": "0",
    # the figures CICT asked to hide on 7 November 2026 ("Hide the above said two graphs"): the card "Institutions registered"
    # (with today and the last 7 days) of At a glance on /institutions, and on the home page too (1.2.165: "at home page hide 258
    # Institutions registered"), and the ring "Participating Institutions under a Nodal Officer" on /nodal-institutions (1.2.164);
    # '1' shows each again. Since 1.2.168 (10 November 2026: "hide institutions registered", "Everywhere public") the number of
    # institutions registered is on no public page while institutions.registered is '0': /progress and its JSON, /institutions,
    # /dashboard, /join, /my-college; the Console keeps every figure
    "institutions.registered": "0",
    "nodal.covered": "0",
    # the public dashboard KTS 5.0 by State/UT (1.2.122, kts/dashboard.py)
    "dashboard.public": "1",
    # its student delegates by name, once verified (1.2.124)
    "dashboard.names": "1",
    # "Marks recorded: N of M" for each State/UT: the institutions selected or on the reserve list whose marks of Annexure-V
    # are recorded (1.2.175; CICT, 12 November 2026)
    "dashboard.marks": "1",
    "site.draft_note_on": "1",
    "home.pm_on": "1",
    "home.pm_quote": "Kashi Tamil Sangamam furthers the spirit of \u2018Ek Bharat, Shreshtha Bharat\u2019.",
    "home.pm_quote_by": "Hon\u2019ble Prime Minister Shri Narendra Modi",
    "home.pm_caption": "Hon\u2019ble Prime Minister Shri Narendra Modi presenting the Russian translation of the Thirukkural to the President of Russia, Mr Vladimir Putin, at the BRICS Summit 2026, Bharat Mandapam, New Delhi.",
}


# Defaults of earlier versions. A database that still holds one of them, unchanged by the
# administrator, receives the present default when the portal starts.
RETIRED_DEFAULTS = {
    # the banner up to 1.2.47: one student from every participating institution since the D.O. letter of 9 October 2026
    "site.banner": ["Applications for KTS 5.0 — Thirukkural Payilvom are open. One student from every college in India."],
    "contact.email": ["kts5@cict.in"],
    "contact.phone": ["+91-44-2254 2781"],
    "contact.address": ["Central Institute of Classical Tamil, 40 Institutional Area, Taramani, Chennai 600 113"],
    # the pattern of the test up to version 1.1.0: 25 questions of 4 marks, now 50 of 2 (100 marks either way)
    "exam.questions": ["25"],
    "exam.marks_per_q": ["4"],
    # the dates up to version 1.1.4, before the timeline of the programme was fixed, and those of the
    # timeline up to 1.2.31 (registration 10-16 October, test 19 October), moved by the timeline of
    # 8 October 2026 (registration 15-21 October, test 22 October)
    "reg.start": ["2026-09-25", "2026-10-10", "2026-10-15", "2026-10-14"],
    "reg.end": ["2026-11-15", "2026-10-16", "2026-10-21", "2026-10-22", "2026-10-29", "2026-11-20"],
    "exam.date": ["2026-11-29", "2026-10-19", "2026-10-22"],
    "letter.date": ["2026-10-22", "2026-10-25", "2026-11-01"],
    "internship.start": ["2026-10-23", "2026-10-26", "2026-11-02", "2026-12-12"],
    # the test begins at 11:30 (8 October 2026); the window still closes at 12:00
    "exam.start_time": ["11:00"],
    # the D.O. letter of 9 October 2026 (1.2.43): the institutions register their students by 22 October, the Nodal
    # Officers verify until the consolidation, no central test, no cap on the institutions of a State/UT
    "verify.end": ["2026-10-21", "2026-10-24", "2026-10-31"],
    "hei.max_per_state": ["50"],
    # the online orientation has two lectures, not ten (14 October 2026)
    "orientation.note": ["Language-wise online orientation sessions (10 lectures + 20-minute live Q&A) will be scheduled after the merit list is published.",
                         "Language-wise online orientation sessions (2 lectures + 20-minute live Q&A) will be scheduled after the merit list is published."],
    # the launch of 14 October 2026 was postponed; the Hon'ble Minister of Education launched the portal and its registration
    # on 22 October 2026 (1.2.95): registration 22-29 October, and every later date a week on
    "launch.at": ["2026-10-14T17:00"],
    "launch.until": ["2026-10-22"],
    "hei.end": ["2026-10-21", "2026-10-29", "2026-11-10", "2026-11-15"],
    "hei.select_end": ["2026-11-15", "2026-11-17"],
    "orientation.by": ["2026-12-10"],
    "camp.from": ["2026-10-15"],
    "camp.to": ["2026-10-21", "2026-10-29", "2026-11-20", "2026-11-19"],
    # the reminders: one key each (the second of a pair written twice up to 1.2.171 had hidden the first); the days of the
    # letter of 31 October 2026 moved by the Ministry's revision of 10 November (1.2.172)
    "remind.test_by": ["2026-10-17", "2026-10-24", "2026-11-16", "2026-11-18"],
    "remind.select_by": ["2026-10-20", "2026-10-27", "2026-11-18", "2026-11-19"],
    "remind.register_by": ["2026-10-21", "2026-10-28", "2026-11-19", "2026-11-20"],
    "papers.due": ["2026-11-05", "2026-11-12", "2027-01-11"],
    "present.due": ["2026-11-15", "2026-11-22", "2027-01-11"],
}

# The dates of the revised D.O. letter of the Ministry of Education (26 October 2026, Annexure-III): put in once over the values
# of each database, also where CICT had set others in the Console; changed in the Console afterwards, they stay so
REVISED_DO_DATES = ("hei.end", "hei.select_end", "camp.to", "reg.end", "verify.end", "letter.date", "internship.start",
                    "papers.due", "present.due", "remind.test_by", "remind.select_by", "remind.register_by")

# The dates of the D.O. letter of 31 October 2026 (Annexure-III D, 1.2.133): put in once over the values of each database, as
# those of 26 October were; changed in the Console afterwards, they stay so
REVISED_DO2_DATES = ("hei.end", "hei.select_end", "camp.to", "internship.start", "papers.due", "present.due",
                     "remind.test_by", "remind.select_by", "remind.register_by", "orientation.by")

# The days of the central online test (1.2.120): put in once over the values of each database, as the dates of the revised
# D.O. letter; changed in the Console afterwards, they stay so
EXAM_DAYS = ("exam.date", "exam.date_to", "exam.start_time", "exam.end_time", "exam.open")

# Titles of the events of data/timeline.json as earlier versions put them in, by the key of the event: an event
# that still holds one receives the present title, so that the schedule keeps finding its translation.
RETIRED_EVENT_TITLES = {
    "selection": ["Selection of the 1,000 students", "Consolidation of the selected students by CICT, with State-wise and language-wise representation"],
    "letters": ["Issue of confirmation letters"],
    "live": ["Live sessions: 20 question-and-answer sessions", "Live online orientation with an interactive question-and-answer session"],
    # the revised D.O. letter (26 October 2026)
    "assess": ["Completion of the institution-level assessments: each institution selects one student on merit"],
    # the D.O. letter of 31 October 2026 has no preliminary list of institutions (1.2.155)
    "hei_list": ["Nodal Institutions furnish the details of their Nodal Officer and the preliminary list of institutions"],
    "internship": ["Commencement of the one-month internship and research period"],
    "papers": ["Submission of research papers"],
}

# Days of the events of data/timeline.json as earlier versions put them in, by the key of the event:
# (starts_at, ends_at). An event that still holds them receives the days of the present file; an event
# moved in the console is left alone. The timeline of 8 October 2026 moved these three.
RETIRED_EVENT_DAYS = {
    "selection": [("2026-10-20T00:00", "2026-10-21T00:00"), ("2026-10-23T00:00", "2026-10-24T00:00")],
    # the Nationwide Students' Engagement Programme: 15 October 2026 onwards, no longer until 15 November (1.2.81)
    "engage": [("2026-10-15T00:00", "2026-11-15T00:00")],
    "letters": [("2026-10-22T00:00", None), ("2026-10-25T00:00", None)],
    "internship": [("2026-10-23T00:00", None), ("2026-10-26T00:00", None)],
    # the launch of 22 October 2026 (1.2.95): the assessment, the selection and every step after it a week on (the second
    # days of selection, letters and internship above, and these)
    "assess": [("2026-10-21T00:00", None)],
    "live": [("2026-10-26T00:00", None)],
    "papers": [("2026-11-05T00:00", None)],
    "forward": [("2026-11-06T00:00", None)],
    "eval_start": [("2026-11-07T00:00", None)],
    "eval_end": [("2026-11-12T00:00", None)],
    "booklet": [("2026-11-13T00:00", "2026-11-16T00:00")],
    "present": [("2026-11-15T00:00", None)],
    "printed": [("2026-11-20T00:00", None)],
}
# The D.O. letter of the Ministry of Education of 31 October 2026, pinned among the notices and circulars with the letter itself
# (data/notices/, 1.2.133): the title and the body of the notice, put in once for each database as the circular is
# The Ministry's extension of the registration deadline and revised timeline (e-mail of the Department of Higher Education of
# 10 November 2026 to the Nodal Universities and CICT, 1.2.172): a pinned notice with its text, put in once for each database
EXT_NOTICE = (
    "Extension of the registration deadline and revised timeline: Ministry of Education, 10 November 2026",
    "\n".join([
        "Following the virtual meeting of 10 November 2026 with the 31 Nodal Universities and CICT, chaired by the Additional "
        "Secretary (TEL), the Ministry of Education, Government of India (Department of Higher Education), has extended the last "
        "date for the registration of institutions on this portal from 15 November 2026 to 18 November 2026, and revised the "
        "timeline at Annexure-III of the D.O. letter No. 16-2/2026-Skt.I (Pt.) of 31 October 2026:",
        "",
        "• Registration of institutions on kts.cict.in and outreach: up to 18 November 2026 (earlier 15 November).",
        "• Scrutiny and selection of the Participating Institutions by the Nodal Institutions (Annexure-I numbers, SOP at "
        "Annexure-V, reserve list): 19 November 2026 (earlier 16–17 November).",
        "• Assessment of the interested students: by 23 November 2026 (earlier 19 November).",
        "• Nomination of one student per institution on the portal: 24 November 2026 (earlier 20 November).",
        "",
        "Unchanged: the inaugural function of KTS 5.0 on 28 November and the valedictory function on 12 December 2026 (virtual "
        "joining); the academic orientation and access to the study material by 14 December 2026; the one-month research and "
        "academic engagement from 15 December 2026 to 14 January 2027, with the submission of the article/research note, the "
        "activity report and the supporting records by 14 January 2027 and the stipend of Rs. 10,000 through DBT after "
        "verification; the academic review, compilation and recognition as notified by CICT.",
        "",
        "The Nodal Universities give wide publicity to the extended deadline among the higher educational institutions of their "
        "State/UT, complete the scrutiny and selection in accordance with the SOP within the revised timeline, and furnish the "
        "final list of selected institutions in the format at Annexure-II and the details of the State/UT Nodal Officer, if not "
        "already shared.",
        "",
        "For any clarification: Dr. R. Bhuvaneshwari, Registrar, Central Institute of Classical Tamil, Chennai "
        "(registrar@cict.in, mobile 9790325518 / 9965734497).",
    ]),
)
DO_NOTICE = (
    "D.O. letter of the Ministry of Education, 31 October 2026: Students' Engagement Programme under KTS 5.0 (revised Annexure-I and timeline)",
    "\n".join([
        "D.O. No. 16-2/2026-Skt.I (Pt.) of 31 October 2026 from the Additional Secretary, Department of Higher Education, Ministry of "
        "Education, to the Vice-Chancellors/Directors of the Nodal Higher Educational Institutions, revising the letter of 9 October "
        "2026 on the nationwide Students' Engagement Programme of Kashi Tamil Sangamam 5.0 (28 November – 12 December 2026). The "
        "letter with its annexures is attached.",
        "",
        "Annexure-I: the State/UT-wise list of the Nodal Higher Educational Institutions and the final number of Participating "
        "Institutions to be selected by each, 1,000 in all. Registration is open to institutions without any State/UT-wise ceiling; "
        "registration does not by itself confer selection.",
        "",
        "Annexure-III, the revised timeline:",
        "• Up to 15 November 2026: registration of interested institutions on this portal; wide outreach by the Nodal Institutions.",
        "• 16–17 November 2026: scrutiny and selection of the Participating Institutions by the Nodal Institutions, as per "
        "Annexure-I, with a reserve list (SOP at Annexure-V).",
        "• By 19 November 2026: each selected Participating Institution completes the assessment of its interested students.",
        "• 20 November 2026: each Participating Institution nominates one student on merit through this portal.",
        "• 28 November 2026: inaugural function of KTS 5.0; 12 December 2026: valedictory function. All Nodal Institutions, "
        "Participating Institutions and nominated students join virtually; the link will be communicated separately.",
        "• By 14 December 2026: academic orientation by CICT and access to the study material and educational videos.",
        "• 15 December 2026 – 14 January 2027: the one-month research and academic engagement: structured study, an original "
        "article/research note of four to five pages under a Faculty Supervisor/Guide, and a one-hour presentation at the "
        "institution, recorded; the institution submits the video recording of the presentation to CICT.",
        "• By 14 January 2027: submission of the article/research note, the activity report and the supporting records.",
        "",
        "Each eligible selected student is entitled to a stipend of Rs. 10,000, disbursed through Direct Benefit Transfer after "
        "verification of the prescribed outputs and validation of the student's bank account details by the Participating "
        "Institution through this portal.",
        "",
        "For any clarification: Dr. R. Bhuvaneshwari, Registrar, Central Institute of Classical Tamil (CICT), Chennai, "
        "registrar@cict.in, mobile 9790325518 / 9965734497.",
    ]),
)
DO_NOTICE_FILE = "notices/KTS5-DO-letter-31-October-2026.pdf"

# the revised D.O. letter of the Ministry (26 October 2026, Annexure-III D): the days of the steps it keeps, as 1.2.95 put them
for _key, _days in (("assess", ("2026-10-29T00:00", None)), ("selection", ("2026-10-30T00:00", "2026-10-31T00:00")),
                    ("live", ("2026-11-02T00:00", None)), ("internship", ("2026-11-02T00:00", None)),
                    ("papers", ("2026-11-12T00:00", None))):
    RETIRED_EVENT_DAYS[_key].append(_days)

# the D.O. letter of 31 October 2026 (Annexure-III D, 1.2.133): the days of the steps as the letter of 26 October had them
for _key, _days in (("hei_reg", ("2026-11-10T00:00", None)), ("hei_select", ("2026-11-11T00:00", "2026-11-15T00:00")),
                    ("assess", ("2026-11-20T00:00", None)), ("live", ("2026-12-10T00:00", None)),
                    ("internship", ("2026-12-12T00:00", None)), ("research", ("2026-12-12T00:00", "2027-01-11T00:00")),
                    ("papers", ("2027-01-11T00:00", None))):
    RETIRED_EVENT_DAYS.setdefault(_key, []).append(_days)

# the registration of institutions up to 18 November 2026, not 15 (CICT, 10 November 2026, 1.2.171); the steps after it stay
RETIRED_EVENT_DAYS["hei_reg"].append(("2026-11-15T00:00", None))

# the Ministry's revision of 10 November 2026 (1.2.172): the selection on 19 November, the assessment by 23, the nomination on 24;
# CICT's consolidation and verification of the nominations from 25 November to 5 December
for _key, _days in (("hei_select", ("2026-11-16T00:00", "2026-11-17T00:00")), ("assess", ("2026-11-19T00:00", None)),
                    ("selection", ("2026-11-21T00:00", "2026-12-05T00:00"))):
    RETIRED_EVENT_DAYS.setdefault(_key, []).append(_days)

# Steps of the timeline that the revised D.O. letter (26 October 2026) no longer has: (title, starts_at, ends_at) as the
# portal put them in. Each is taken off the schedule once (published = 0), where it still holds them; nothing is deleted.
RETIRED_EVENTS = [
    ("Last date for the list of participating institutions", "2026-10-15T00:00", None),
    ("Nationwide Students' Engagement Programme in the participating institutions", "2026-10-15T00:00", None),
    ("Confirmation by email and on the portal, and collection of the details for the stipend", "2026-11-01T00:00", None),
    ("Classification and forwarding of research papers", "2026-11-13T00:00", None),
    ("Commencement of evaluation by CIIL", "2026-11-14T00:00", None),
    ("Completion of evaluation by CIIL", "2026-11-18T00:00", None),
    ("Compilation, design and production of the booklet", "2026-11-19T00:00", "2026-11-22T00:00"),
    ("Last date for student presentations and knowledge dissemination", "2026-11-22T00:00", None),
    ("Printed booklet ready", "2026-11-25T00:00", None),
]


# Roles of agencies as earlier versions seeded them (data/agencies.json of that time).
# Slips of the corpus corrected since questions were generated from it (data/kurals): the generated questions
# (source 'auto') that carry the old words get the corrected ones at each start; questions written by hand are left alone.
CORPUS_SLIPS = [
    ("The sage fulfils the vitue's call.", "The sage fulfils the virtue's call."),   # couplet 30, English (1.2.68)
]

RETIRED_AGENCY_ROLES = {
    "CICT": ["Implementing institute for KTS 5.0: runs this portal, the student registration and selection, the 21-language orientation, the digital repository and all Thirukkural content.",
             # the D.O. letter of 31 October 2026: the institutions register, the Participating Institutions nominate (1.2.155)
             "Implementing institute for KTS 5.0: runs this portal, the student registration and selection, the 22-language orientation, the digital repository and all Thirukkural content."],
    "UGC": ["Circulates the call for applications to universities and colleges across India and nominates faculty mentors."],
    "AICTE": ["Outreach to technical institutions for student registration."],
    "IRCTC": ["Travel, accommodation and local tours for delegates; Thirukkural displays at railway stations with Indian Railways."],
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
        # Under WAL, NORMAL writes the log to the disk at each checkpoint and not at each commit: the
        # load test of 9 October 2026 found the saves of the online test waiting on the disk. A crash of
        # the portal loses nothing; a power cut of the server may lose the last commits, never the database.
        conn.execute("PRAGMA synchronous=NORMAL")
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


def _people(entries):
    """The people of `entries` with a name, as dicts name/designation/email/phone, in their order."""
    settings = all_settings()
    people = []
    for prefix, _person in entries:
        person = {field: (settings.get(f"{prefix}.{field}") or "").strip() for field, _label in NODAL_FIELDS}
        if person["name"]:
            people.append(person)
    return people


def nodal_officers():
    """The nodal officers with a name, in their order."""
    return _people(NODAL_OFFICERS)


def institute_head():
    """The head of the institute when a name is set, else an empty list."""
    return _people(INSTITUTE_HEAD)


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


def audit_rows(action, entity, rows, user=None, ip=""):
    """
    The rows of the audit log for one action on many entries, rows = [(entity_id, detail), ...].
    They are written on the connection of the request and not committed here: the caller
    commits them together with the change that they describe.
    """
    now = utcnow()
    get_db().executemany(
        "INSERT INTO audit_log(user_id, actor, action, entity, entity_id, detail, ip, created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        [(user["id"] if user else None, user["email"] if user else "public", action, entity, entity_id,
          json.dumps(detail, ensure_ascii=False) if isinstance(detail, (dict, list)) else (detail or ""),
          ip or "", now) for entity_id, detail in rows],
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


NODAL_NOTICE_LINK = "/nodal-institutions"
# the days in the circular: those of the Ministry's revision of 10 November 2026 (1.2.172), and of the D.O. letter of 31 October
# 2026 before, which a circular that a database holds unchanged gives up
NODAL_DAYS = ("up to 18 November 2026. The Nodal Institution of each State/UT scrutinises them and selects the prescribed number "
              "on 19 November 2026, with a reserve list; each selected Participating Institution assesses its interested students "
              "by 23 November and nominates one on merit on 24 November 2026 (the timeline as revised by the Ministry of Education "
              "on 10 November 2026).")
NODAL_DAYS_1171 = ("up to 15 November 2026. The Nodal Institution of each State/UT scrutinises them and selects the prescribed "
                   "number on 16 and 17 November 2026, with a reserve list; each selected Participating Institution assesses its "
                   "interested students by 19 November and nominates one on merit by 20 November 2026.")


def nodal_notice(heis):
    """(title, body) of the circular with the State/UT-wise list of the Nodal Higher Educational Institutions."""
    # the row as the letter of 31 October 2026 names it: with the Union Territory paired with a State (1.2.135)
    lines = [f"{i}. {' and '.join([h['state'], *h.get('covers', [])])}: {h['name']} ({h['allocation']})" for i, h in enumerate(heis, 1)]
    pairs = [(c, h["state"]) for h in heis for c in h.get("covers", [])]
    pairs_text = ("Annexure-I pairs " + "; ".join(f"{c} with {s}" for c, s in pairs) + ". The institutions of these Union Territories "
                  "register with their own Union Territory and are selected by the Nodal Institution of the State, within the number "
                  "prescribed for the two together.")
    total = sum(h["allocation"] for h in heis)
    body = "\n".join([
        "As communicated by the Ministry of Education, Government of India (Annexure-I of the D.O. letter of 31 October 2026): the Nodal Higher Educational "
        "Institution of each State/UT for the Students' Engagement Programme of Kashi Tamil Sangamam 5.0 (Thirukkural "
        "Payilvom). The number in brackets is the number of Participating HEIs to be selected in that State/UT.",
        "",
        *lines,
        "",
        f"Total: {total:,} Participating HEIs.",
        "",
        "Registration is open to institutions without any State/UT-wise ceiling. The figures above indicate the final number of "
        "Participating Institutions to be selected by the respective Nodal Institution in accordance with the Standard "
        "Operating Procedure (Annexure-V). Registration does not by itself confer selection.",
        *(["", pairs_text] if pairs else []),
        "",
        "All interested higher educational institutions (Central/State/Private Universities and Colleges) register on this "
        "portal (Register › Register your institution) " + NODAL_DAYS + " "
        "The Participating Institutions selected by the Nodal Institutions are listed on the page of the Nodal Institutions.",
    ])
    return "State/UT-wise list of Nodal Higher Educational Institutions", body


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
    # no ceiling on the institutions selected (1.2.178): off once; CICT may switch it on again in the Console
    if not conn.execute("SELECT 1 FROM settings WHERE key = 'migrate.cap_off_1112'").fetchone():
        conn.execute("UPDATE settings SET value = '0', updated_at = ? WHERE key = 'hei.cap_annexure'", (now,))
        conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", ("migrate.cap_off_1112", "1", now))
    if not conn.execute("SELECT 1 FROM settings WHERE key = 'migrate.revised_do'").fetchone():
        for key in REVISED_DO_DATES:
            conn.execute("UPDATE settings SET value = ?, updated_at = ? WHERE key = ?", (DEFAULT_SETTINGS[key], now, key))
        conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", ("migrate.revised_do", "1", now))
    if not conn.execute("SELECT 1 FROM settings WHERE key = 'migrate.revised_do2'").fetchone():
        for key in REVISED_DO2_DATES:
            conn.execute("UPDATE settings SET value = ?, updated_at = ? WHERE key = ?", (DEFAULT_SETTINGS[key], now, key))
        conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", ("migrate.revised_do2", "1", now))
    if not conn.execute("SELECT 1 FROM settings WHERE key = 'migrate.exam_days'").fetchone():
        for key in EXAM_DAYS:
            conn.execute("UPDATE settings SET value = ?, updated_at = ? WHERE key = ?", (DEFAULT_SETTINGS[key], now, key))
        conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", ("migrate.exam_days", "1", now))

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
        # the story of couplet 3 of PM eVidya CICT - Tamil (1.2.101) takes its place among the stories, which stand in the
        # order of the couplets: the eight after it move one place on (439-446 to 440-447), once, where they still have the
        # place they were given; before the new entries are put in, so that a new database is left as the file has it
        later = [r["url"] for r in json.loads(seed_path.read_text(encoding="utf-8"))
                 if r["category"] == "video_pmevidya" and r.get("sort_order", 100) > 439]
        if later and not conn.execute("SELECT 1 FROM settings WHERE key = 'migrate.pmevidya.couplet3'").fetchone():
            conn.execute("UPDATE resources SET sort_order = sort_order + 1 WHERE sort_order BETWEEN 439 AND 446 AND url IN (%s)"
                         % ", ".join("?" * len(later)), later)
            conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)",
                         ("migrate.pmevidya.couplet3", "1", now))
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
        # "Syllabus" became "Study material" (3 Nov 2026, 1.2.148): the title of the entry of the study book, once, where it is
        # still the one it came with (an entry the Console has renamed keeps its name)
        if not conn.execute("SELECT 1 FROM settings WHERE key = 'migrate.resource.study_material'").fetchone():
            conn.execute("UPDATE resources SET title = ? WHERE url = '/syllabus' AND title = ?",
                         ("Thirukkural Payilvom · Study material for the institution-level assessment", "Thirukkural Payilvom · Syllabus for the institution-level assessment"))
            conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)",
                         ("migrate.resource.study_material", "1", now))
        # Valluvar's Pond plays inside the portal (1.2.186): the entry of 1.2.184, which led to the game on the site of its makers
        # and was not featured, leads to the page of the portal and is featured; once, and only where the entry is still as it came
        # (an entry the Console has changed keeps what it was given)
        if not conn.execute("SELECT 1 FROM settings WHERE key = 'migrate.resource.pond_page'").fetchone():
            pond = next((r for r in json.loads(seed_path.read_text(encoding="utf-8")) if r["key"] == "valluvar-pond"), None)
            if pond:
                conn.execute("UPDATE resources SET url = ?, description = ?, featured = ?, sort_order = ?, updated_at = ? "
                             "WHERE url = 'https://adhavan18.github.io/valluvar-pond/' AND featured = 0 AND sort_order = 16",
                             (pond["url"], pond["description"], pond.get("featured", 0), pond.get("sort_order", 100), now))
            conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)",
                         ("migrate.resource.pond_page", "1", now))
        # the Thirukkural stories of PM eVidya CICT - Tamil, put in among the Thirukkural videos (1.2.93), have a tab of
        # their own (1.2.94): they move to it once; an entry that the Console puts back or elsewhere later stays there
        moved = [r["url"] for r in json.loads(seed_path.read_text(encoding="utf-8")) if r["category"] == "video_pmevidya"]
        if moved and not conn.execute("SELECT 1 FROM settings WHERE key = 'migrate.video_pmevidya'").fetchone():
            conn.execute("UPDATE resources SET category = 'video_pmevidya' WHERE category = 'video_kural' AND url IN (%s)"
                         % ", ".join("?" * len(moved)), moved)
            conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)",
                         ("migrate.video_pmevidya", "1", now))

    # Photographs of the gallery that every installation carries (data/gallery.json, 1.2.95): each is put in once, so that
    # one the Console deletes does not come back. The file stays in data/gallery/ and is served from there (utils.file_folder).
    seed_path = app.config["DATA_DIR"] / "gallery.json"
    if seed_path.exists():
        for p in json.loads(seed_path.read_text(encoding="utf-8")):
            mark = f"seed.gallery.{p['key']}"
            if conn.execute("SELECT 1 FROM settings WHERE key = ?", (mark,)).fetchone():
                continue
            source = app.config["DATA_DIR"] / "gallery" / p["file"]
            if source.exists() and not conn.execute("SELECT 1 FROM gallery_photos WHERE file_path = ?",
                                                    ("gallery/" + p["file"],)).fetchone():
                conn.execute("INSERT INTO gallery_photos(album, caption, taken_on, file_path, file_name, file_size, published, "
                             "sort_order, created_at) VALUES(?,?,?,?,?,?,1,?,?)",
                             (p["album"], p["caption"], p["taken_on"], "gallery/" + p["file"], p["file"], source.stat().st_size,
                              p.get("sort_order", 100), now))
            conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", (mark, "1", now))

    # The timeline of the programme (data/timeline.json), as events of the schedule. Each is put
    # in once for each database, as the entries of the repository are, and not at all when an
    # event with the same title is there already. The dates kept as settings (registration, the
    # test, the Sangamam itself) are not among them: the schedule takes those from the settings.
    seed_path = app.config["DATA_DIR"] / "timeline.json"
    if seed_path.exists():
        for e in json.loads(seed_path.read_text(encoding="utf-8")):
            mark = f"seed.event.{e['key']}"
            if conn.execute("SELECT 1 FROM settings WHERE key = ?", (mark,)).fetchone():
                continue
            if not conn.execute("SELECT 1 FROM events WHERE title = ?", (e["title"],)).fetchone():
                agency = conn.execute("SELECT id FROM agencies WHERE code = ?", (e.get("agency", ""),)).fetchone()
                conn.execute(
                    "INSERT INTO events(title, description, kind, starts_at, ends_at, agency_id, published, created_at, updated_at) "
                    "VALUES(?,?,?,?,?,?,1,?,?)",
                    (e["title"], e.get("description", ""), e["kind"], e["starts"] + "T00:00",
                     e["ends"] + "T00:00" if e.get("ends") else None, agency[0] if agency else None, now, now),
                )
            conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", (mark, "1", now))
        seeds = {e["key"]: e for e in json.loads(seed_path.read_text(encoding="utf-8"))}
        for key, olds in RETIRED_EVENT_TITLES.items():
            e = seeds.get(key)
            if e is None:
                continue
            for old in olds:
                conn.execute("UPDATE events SET title = ?, updated_at = ? WHERE title = ?", (e["title"], now, old))
        # the days of an event that an earlier version put in, still unchanged, become those of the file
        for key, olds in RETIRED_EVENT_DAYS.items():
            e = seeds.get(key)
            if e is None:
                continue
            new = (e["starts"] + "T00:00", e["ends"] + "T00:00" if e.get("ends") else None)
            for starts, ends in olds:
                conn.execute("UPDATE events SET starts_at = ?, ends_at = ?, updated_at = ? "
                             "WHERE title = ? AND starts_at = ? AND ends_at IS ?",
                             (new[0], new[1], now, e["title"], starts, ends))
        # the steps the revised D.O. letter no longer has leave the schedule, once
        if not conn.execute("SELECT 1 FROM settings WHERE key = 'migrate.revised_do.events'").fetchone():
            for title, starts, ends in RETIRED_EVENTS:
                conn.execute("UPDATE events SET published = 0, updated_at = ? WHERE title = ? AND starts_at = ? AND ends_at IS ?",
                             (now, title, starts, ends))
            conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", ("migrate.revised_do.events", "1", now))

    # The State/UT-wise list of the Nodal Higher Educational Institutions (data/nodal_heis.json), as
    # a circular pinned among the notices (1.2.51). Put in once for each database, as the events are:
    # a notice that CICT has changed or deleted in the console stays so, and none is added when a
    # notice with the same title is there already.
    seed_path = app.config["DATA_DIR"] / "nodal_heis.json"
    # the circular as 1.2.51 put it in, with the tentative allocation, takes the numbers and the text of the revised D.O.
    # letter (26 October 2026), once
    if seed_path.exists() and not conn.execute("SELECT 1 FROM settings WHERE key = 'migrate.revised_do.notice'").fetchone():
        title, body = nodal_notice(json.loads(seed_path.read_text(encoding="utf-8")))
        conn.execute("UPDATE notices SET body = ?, updated_at = ? WHERE title = ? AND body LIKE '%allocation is tentative%'",
                     (body, now, title))
        conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", ("migrate.revised_do.notice", "1", now))
    # the circular with the numbers and the days of 26 October takes those of the D.O. letter of 31 October 2026, once (1.2.133)
    if seed_path.exists() and not conn.execute("SELECT 1 FROM settings WHERE key = 'migrate.revised_do2.notice'").fetchone():
        title, body = nodal_notice(json.loads(seed_path.read_text(encoding="utf-8")))
        conn.execute("UPDATE notices SET body = ?, updated_at = ? WHERE title = ? AND body LIKE '%up to 10 November 2026%'",
                     (body, now, title))
        conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", ("migrate.revised_do2.notice", "1", now))
    # the pairs of Annexure-I of 31 October 2026 (1.2.135): the circular names each row as the letter does, once; a circular
    # CICT has rewritten is left alone
    if seed_path.exists() and not conn.execute("SELECT 1 FROM settings WHERE key = 'migrate.annex1_pairs.notice'").fetchone():
        title, body = nodal_notice(json.loads(seed_path.read_text(encoding="utf-8")))
        conn.execute("UPDATE notices SET body = ?, updated_at = ? WHERE title = ? AND body LIKE '%7. Gujarat: Central University of Gujarat (50)%'",
                     (body, now, title))
        conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", ("migrate.annex1_pairs.notice", "1", now))
    mark = "seed.notice.nodal_heis"
    if seed_path.exists() and not conn.execute("SELECT 1 FROM settings WHERE key = ?", (mark,)).fetchone():
        title, body = nodal_notice(json.loads(seed_path.read_text(encoding="utf-8")))
        if not conn.execute("SELECT 1 FROM notices WHERE title = ?", (title,)).fetchone():
            conn.execute("INSERT INTO notices(title, body, category, lang, pinned, published, attachment, link, created_at, updated_at) "
                         "VALUES(?,?,'circular','en',1,1,'',?,?,?)", (title, body, NODAL_NOTICE_LINK, now, now))
        conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", (mark, "1", now))

    # The D.O. letter of 31 October 2026 (1.2.133), pinned among the notices and circulars with the letter itself, which the
    # portal carries (data/notices/): put in once for each database, as the circular is; none is added when a notice with the
    # same title is there already (as when CICT put the letter in itself).
    mark = "seed.notice.do_31oct"
    if (app.config["DATA_DIR"] / DO_NOTICE_FILE).is_file() and not conn.execute("SELECT 1 FROM settings WHERE key = ?", (mark,)).fetchone():
        if not conn.execute("SELECT 1 FROM notices WHERE title = ?", (DO_NOTICE[0],)).fetchone():
            conn.execute("INSERT INTO notices(title, body, category, lang, pinned, published, attachment, link, created_at, updated_at) "
                         "VALUES(?,?,'circular','en',1,1,?,'/schedule',?,?)", (DO_NOTICE[0], DO_NOTICE[1], DO_NOTICE_FILE, now, now))
        conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", (mark, "1", now))
    # its number as the letter prints it (1.2.152): "16-2/2026-Skt.I (Pt.)"; the notice put in before takes it, once, where its text is
    # still the one put in
    mark = "migrate.do_31oct.number"
    if not conn.execute("SELECT 1 FROM settings WHERE key = ?", (mark,)).fetchone():
        conn.execute("UPDATE notices SET body = ?, updated_at = ? WHERE title = ? AND body = ?",
                     (DO_NOTICE[1], now, DO_NOTICE[0], DO_NOTICE[1].replace("16-2/2026-Skt.I (Pt.)", "16-2/2026-Skt.(Pt.)")))
        conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", (mark, "1", now))

    # The D.O. letter of 31 October 2026 (1.2.155): the notice of the letter (the video of the presentation, the Registrar's mobiles),
    # the circular of the Nodal HEIs and the launch notice take their present text where a database holds the earlier one unchanged;
    # the marks of Annexure-V recorded on the six criteria of the letter of 26 October no longer count (their total is cleared, the
    # marks stay recorded); CICT's central online test is switched off (the user, 4 November 2026). Each once.
    mark = "migrate.do_31oct.1155"
    if not conn.execute("SELECT 1 FROM settings WHERE key = ?", (mark,)).fetchone():
        before = DO_NOTICE[1].replace("recorded; the institution submits the video recording of the presentation to CICT.", "recorded.") \
                             .replace("registrar@cict.in, mobile 9790325518 / 9965734497.", "registrar@cict.in.")
        conn.execute("UPDATE notices SET body = ?, updated_at = ? WHERE title = ? AND body = ?", (DO_NOTICE[1], now, DO_NOTICE[0], before))
        if seed_path.exists():
            title, body = nodal_notice(json.loads(seed_path.read_text(encoding="utf-8")))
            before = body.replace("The Participating Institutions selected by the Nodal Institutions are listed",
                                  "The participating institutions accepted so far are listed")
            conn.execute("UPDATE notices SET body = ?, updated_at = ? WHERE title = ? AND body = ?", (body, now, title, before))
        conn.execute("UPDATE notices SET body = ?, updated_at = ? WHERE title = ? AND body = ?",
                     (LAUNCH_NOTICE[1], now, LAUNCH_NOTICE[0], LAUNCH_BODY_1154))
        conn.execute("UPDATE institutions SET sop_total = NULL WHERE sop_total IS NOT NULL AND sop_scores LIKE '%\"record\"%'")
        conn.execute("UPDATE settings SET value = '0', updated_at = ? WHERE key = 'exam.open' AND value != '0'", (now,))
        conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", (mark, "1", now))

    # The Ministry's revision of the timeline of 10 November 2026 (1.2.172): its notice, pinned, put in once (none when a notice
    # with its title is there); the circular of the Nodal Institutions and the launch notice take the revised days where a
    # database holds their text of the letter of 31 October unchanged
    mark = "seed.notice.ext_10nov"
    if not conn.execute("SELECT 1 FROM settings WHERE key = ?", (mark,)).fetchone():
        if not conn.execute("SELECT 1 FROM notices WHERE title = ?", (EXT_NOTICE[0],)).fetchone():
            conn.execute("INSERT INTO notices(title, body, category, lang, pinned, published, attachment, link, created_at, updated_at) "
                         "VALUES(?,?,'circular','en',1,1,'','/schedule',?,?)", (EXT_NOTICE[0], EXT_NOTICE[1], now, now))
        if seed_path.exists():
            title, body = nodal_notice(json.loads(seed_path.read_text(encoding="utf-8")))
            conn.execute("UPDATE notices SET body = ?, updated_at = ? WHERE title = ? AND body = ?",
                         (body, now, title, body.replace(NODAL_DAYS, NODAL_DAYS_1171)))
        conn.execute("UPDATE notices SET body = ?, updated_at = ? WHERE title = ? AND body = ?",
                     (LAUNCH_NOTICE[1], now, LAUNCH_NOTICE[0], LAUNCH_BODY_1171))
        conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", (mark, "1", now))

    # The launch of 14 October 2026, 5:00 PM was postponed (1.2.69): on a database that has announced it already (its notice
    # was put in by an earlier start), the launch, registration and the banner are switched off, once. Nothing else changes,
    # and CICT switches them on again in the Console with the new moment; a new database is left as it is.
    mark = "seed.launch.postponed"
    if not conn.execute("SELECT 1 FROM settings WHERE key = ?", (mark,)).fetchone():
        if conn.execute("SELECT 1 FROM settings WHERE key = 'seed.notice.launch'").fetchone():
            for key in ("launch.on", "reg.open", "site.banner_on"):
                conn.execute("INSERT INTO settings(key, value, updated_at) VALUES(?, '0', ?) "
                             "ON CONFLICT(key) DO UPDATE SET value = '0', updated_at = excluded.updated_at", (key, now))
        conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", (mark, "1", now))

    # The launch took place on 22 October 2026 (1.2.95): on a database where it was switched off when it was postponed, the
    # launch, registration and the banner are switched on again, once; CICT may switch them off in the Console afterwards.
    mark = "seed.launch.done"
    if not conn.execute("SELECT 1 FROM settings WHERE key = ?", (mark,)).fetchone():
        if conn.execute("SELECT 1 FROM settings WHERE key = 'seed.launch.postponed'").fetchone():
            for key in ("launch.on", "reg.open", "site.banner_on"):
                conn.execute("INSERT INTO settings(key, value, updated_at) VALUES(?, '1', ?) "
                             "ON CONFLICT(key) DO UPDATE SET value = '1', updated_at = excluded.updated_at", (key, now))
        conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES(?,?,?)", (mark, "1", now))
    # the notice of before the launch, still unchanged, says that it took place, dated the day it is changed
    for title, body in RETIRED_LAUNCH_NOTICES:
        conn.execute("UPDATE notices SET title = ?, body = ?, created_at = ?, updated_at = ? WHERE title = ? AND body = ?",
                     (LAUNCH_NOTICE[0], LAUNCH_NOTICE[1], now, now, title, body))

    # The launch of the KTS 5.0 web portal and registration (1.2.69), as a notice pinned at the top, put in once as the circular is.
    mark = "seed.notice.launch"
    if not conn.execute("SELECT 1 FROM settings WHERE key = ?", (mark,)).fetchone():
        if not conn.execute("SELECT 1 FROM notices WHERE title = ?", (LAUNCH_NOTICE[0],)).fetchone():
            conn.execute("INSERT INTO notices(title, body, category, lang, pinned, published, attachment, link, created_at, updated_at) "
                         "VALUES(?,?,'general','en',1,1,'','/',?,?)", (LAUNCH_NOTICE[0], LAUNCH_NOTICE[1], now, now))
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

    for old, new in CORPUS_SLIPS:
        like = f"%{old}%"
        conn.execute("UPDATE questions SET text = replace(text, ?, ?), opt_a = replace(opt_a, ?, ?), opt_b = replace(opt_b, ?, ?), "
                     "opt_c = replace(opt_c, ?, ?), opt_d = replace(opt_d, ?, ?) WHERE source = 'auto' AND "
                     "(text LIKE ? OR opt_a LIKE ? OR opt_b LIKE ? OR opt_c LIKE ? OR opt_d LIKE ?)",
                     (old, new) * 5 + (like,) * 5)

    try:
        _first_passwords(app, conn, now)
        conn.commit()
    finally:
        conn.close()


LAUNCH_NOTICE = (
    "Launch of the KTS 5.0 web portal and registration by the Hon'ble Minister of Education, 22 October 2026",
    "The Hon'ble Minister of Education, Shri Pralhad Joshi, launched the web portal of the fifth edition of Kashi Tamil "
    "Sangamam (KTS 5.0), kts.cict.in, and its registration on 22 October 2026. KTS 5.0 is scheduled to be held from "
    "28 November to 12 December 2026 under the theme “Thirukkural Payilvom – Thirukkural Abhyas Karen”. The programme "
    "seeks to celebrate the cultural and civilisational bonds between Kashi and Tamil Nadu and to promote the timeless "
    "ethical and moral values of the Thirukkural.\n\nAll interested higher educational institutions register on kts.cict.in up to "
    "18 November 2026; the Nodal Institutions select the Participating Institutions on 19 November, and each selected "
    "Participating Institution assesses its interested students by 23 November and nominates one student on merit through the "
    "portal on 24 November 2026 (the D.O. letter of the Ministry of Education of 31 October 2026, its timeline as revised by the "
    "Ministry on 10 November 2026).",
)
# its days up to 1.2.171 (the D.O. letter of 31 October 2026): a notice that a database holds unchanged takes the revised ones
LAUNCH_BODY_1171 = LAUNCH_NOTICE[1].replace(
    "18 November 2026; the Nodal Institutions select the Participating Institutions on 19 November, and each selected "
    "Participating Institution assesses its interested students by 23 November and nominates one student on merit through the "
    "portal on 24 November 2026 (the D.O. letter of the Ministry of Education of 31 October 2026, its timeline as revised by the "
    "Ministry on 10 November 2026).",
    "15 November 2026; the Nodal Institutions select the Participating Institutions on 16 and 17 November, and each selected "
    "Participating Institution assesses its interested students by 19 November and nominates one student on merit through the "
    "portal by 20 November 2026 (the D.O. letter of the Ministry of Education of 31 October 2026).")
# its text up to 1.2.154 (the dates of the letter of 26 October): a notice that a database holds unchanged takes the present one (1.2.155)
LAUNCH_BODY_1154 = (
    "The Hon'ble Minister of Education, Shri Pralhad Joshi, launched the web portal of the fifth edition of Kashi Tamil "
    "Sangamam (KTS 5.0), kts.cict.in, and its registration on 22 October 2026. KTS 5.0 is scheduled to be held from "
    "28 November to 12 December 2026 under the theme “Thirukkural Payilvom – Thirukkural Abhyas Karen”. The programme "
    "seeks to celebrate the cultural and civilisational bonds between Kashi and Tamil Nadu and to promote the timeless "
    "ethical and moral values of the Thirukkural.\n\nThe registration of the selected students is open on kts.cict.in. "
    "Each participating institution completes the assessment of its students by 29 October 2026, selects one student on "
    "merit and registers that student on the portal by 29 October 2026."
)

# The notice as put in before the launch took place, for 14 October 2026, 5:00 PM (1.2.69 to 1.2.94): one that a
# database still holds unchanged receives the present title and text (1.2.95).
RETIRED_LAUNCH_NOTICES = [(
    "Launch of the KTS 5.0 web portal and registration by the Hon'ble Minister of Education, 14 October 2026, 5:00 PM",
    "The Hon'ble Minister of Education, Shri Pralhad Joshi, will launch the web portal of the fifth edition of Kashi Tamil "
    "Sangamam (KTS 5.0), kts.cict.in, and its registration on 14 October 2026 (Wednesday) at 5:00 PM. KTS 5.0 is "
    "scheduled to be held from "
    "28 November to 12 December 2026 under the theme “Thirukkural Payilvom – Thirukkural Abhyas Karen”. The programme "
    "seeks to celebrate the cultural and civilisational bonds between Kashi and Tamil Nadu and to promote the timeless "
    "ethical and moral values of the Thirukkural.\n\nThe registration of the selected students opens with the launch, on "
    "kts.cict.in. Each participating institution assesses its students from 15 to 21 October 2026 and selects one student "
    "on merit; the selected student registers by 22 October 2026.",
)]


def init_app(app):
    app.teardown_appcontext(close_db)
    init_db(app)

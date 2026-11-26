"""
Puducherry: nominations only from the institutions of the Nodal Institution's list (1.2.225). CICT, 26 November 2026: "from the
selected institutions of Puducherry only i have to get the students registration / nomination". The institutions that 1.2.220 kept for
a submitted nomination (the references in its mark) are declined and those nominations withdrawn, once; no mail. A rejected nomination
stays rejected; earlier remarks are kept; an institution that CICT accepted again is not touched.

    python -m pytest tests/test_py_strict_1126.py -q
"""
import json

from conftest import make_app
from test_reserve_1111 import _insert

BEFORE = "2026-11-20T06:00:00+00:00"
NAMES = ["Perunthalaivar Kamarajar college of Education", "Pondicherry University", "Perunthalaivar Kamarajar Arts College",
         "IDHAYA COLLEGE OF ARTS AND SCIENCE FOR WOMEN", "Rashtriya Raksha University"]


def _application(app, iid, n, status="submitted", remarks=""):
    from kts.db import execute, utcnow
    with app.app_context():
        aid = execute("INSERT INTO applications(full_name, gender, dob, mobile, email, state, college_name, college_key, pref_lang, "
                      "created_at, updated_at, institution_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (f"Student {n}", "F", "2004-05-06", f"98760{n:05d}", f"s{n}@tests.example", "Puducherry", "College", f"name:c{n}|puducherry",
                       "hi", utcnow(), utcnow(), iid))
        execute("UPDATE applications SET app_no = ?, status = ?, remarks = ? WHERE id = ?", (f"KTS5-TEST-{n:04d}", status, remarks, aid))
        execute("UPDATE institutions SET application_id = ? WHERE id = ?", (aid, iid))
    return aid


def _fresh():
    from kts.db import execute
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key IN ('migrate.py_list_1126', 'migrate.py_strict_1126')")
    return app


def _status(app, table, iid):
    from kts.db import query
    with app.app_context():
        return dict(query(f"SELECT * FROM {table} WHERE id = ?", (iid,), one=True))


def test_only_the_listed_institutions_nominate():
    from kts.db import init_db, query
    app = _fresh()
    listed = {n: _insert(app, n, "Puducherry", "Puducherry", "accepted", created=BEFORE, ref=f"KTS5-HEI-07{i:03d}") for i, n in enumerate(NAMES)}
    nit = _insert(app, "National Institute of Technology Puducherry", "Puducherry", "Karikal", "accepted", created=BEFORE, ref="KTS5-HEI-07100")
    physio = _insert(app, "School of Physiotherapy", "Puducherry", "Pondicherry", "accepted", created=BEFORE, ref="KTS5-HEI-07101")
    plain = _insert(app, "Tagore Government Arts and science College", "Puducherry", "Pondicherry", "accepted", created=BEFORE, ref="KTS5-HEI-07102")
    nit_app = _application(app, nit, 1, remarks="Checked by the Nodal Officer")
    physio_app = _application(app, physio, 2)
    pu_app = _application(app, listed["Pondicherry University"], 3)
    kerala = _insert(app, "Kerala College", "Kerala", "Thrissur", "accepted", created=BEFORE, ref="KTS5-HEI-07103")
    kerala_app = _application(app, kerala, 4)
    with app.app_context():
        mails = query("SELECT COUNT(*) AS n FROM outbox", one=True)["n"]
    init_db(app)
    assert all(_status(app, "institutions", i)["status"] == "accepted" for i in listed.values())
    assert _status(app, "institutions", nit)["status"] == _status(app, "institutions", physio)["status"] == "declined"
    assert _status(app, "institutions", plain)["status"] == "declined" and _status(app, "institutions", kerala)["status"] == "accepted"
    nit_row = _status(app, "applications", nit_app)
    assert nit_row["status"] == "withdrawn" and nit_row["remarks"] == (
        "Withdrawn: the institution is not on the list of the Nodal Institution of Puducherry\nEarlier: Checked by the Nodal Officer")
    assert _status(app, "applications", physio_app)["status"] == "withdrawn"
    assert _status(app, "applications", pu_app)["status"] == "submitted" and _status(app, "applications", kerala_app)["status"] == "submitted"
    with app.app_context():
        strict = json.loads(query("SELECT value FROM settings WHERE key = 'migrate.py_strict_1126'", one=True)["value"])
        lines = query("SELECT action, detail FROM audit_log WHERE actor = 'release 1.2.225'")
        assert query("SELECT COUNT(*) AS n FROM outbox", one=True)["n"] == mails
    assert sorted(strict["kept_before"]) == sorted(strict["declined"]) == ["KTS5-HEI-07100", "KTS5-HEI-07101"]
    assert sorted(strict["applications_withdrawn"]) == ["KTS5-TEST-0001", "KTS5-TEST-0002"]
    assert sorted(r["action"] for r in lines) == ["application_withdrawn"] * 2 + ["institution_declined"] * 2
    assert any(json.loads(r["detail"]).get("remarks_was") == "Checked by the Nodal Officer" for r in lines)
    # once
    from kts.db import execute
    with app.app_context():
        execute("UPDATE institutions SET status = 'accepted' WHERE id = ?", (nit,))
    init_db(app)
    assert _status(app, "institutions", nit)["status"] == "accepted"


def test_only_the_kept_references_and_a_rejected_nomination_stays():
    """The strict step declines the references the list step kept, nothing else: one that CICT accepted again stays."""
    from kts.db import execute, init_db, query
    app = _fresh()
    kept = _insert(app, "School of Physiotherapy", "Puducherry", "Pondicherry", "accepted", created=BEFORE, ref="KTS5-HEI-07201")
    again = _insert(app, "Tagore Government Arts and science College", "Puducherry", "Pondicherry", "accepted", created=BEFORE, ref="KTS5-HEI-07202")
    rejected = _application(app, kept, 11, status="rejected", remarks="Photo not clear")
    submitted = _insert(app, "Another College", "Puducherry", "Pondicherry", "accepted", created=BEFORE, ref="KTS5-HEI-07203")
    with app.app_context():
        # the list step ran before (1.2.220): it kept KTS5-HEI-07201 for a nomination; KTS5-HEI-07202 it declined, and CICT accepted it again
        execute("INSERT OR REPLACE INTO settings(key, value, updated_at) VALUES('migrate.py_list_1126', ?, '2026-11-26T09:00:00+00:00')",
                (json.dumps({"listed": [], "changed": [], "declined": ["KTS5-HEI-07202"], "kept_nominated": ["KTS5-HEI-07201"]}),))
    init_db(app)
    assert _status(app, "institutions", kept)["status"] == "declined"
    assert _status(app, "institutions", again)["status"] == "accepted" and _status(app, "institutions", submitted)["status"] == "accepted"
    rejected_row = _status(app, "applications", rejected)
    assert rejected_row["status"] == "rejected" and rejected_row["remarks"] == "Photo not clear"
    with app.app_context():
        strict = json.loads(query("SELECT value FROM settings WHERE key = 'migrate.py_strict_1126'", one=True)["value"])
    assert strict["declined"] == ["KTS5-HEI-07201"] and strict["applications_withdrawn"] == []


def test_nothing_where_the_list_has_not_been_applied():
    from kts import db
    app = _fresh()
    with app.app_context():
        conn = db.get_db()
        db._strict_kept(conn, db.utcnow(), "migrate.zz_list_1126", "migrate.zz_strict_1126", ("Nowhere",), "Nowhere", "note", "release 1.2.225")
        conn.commit()
        mark = json.loads(db.query("SELECT value FROM settings WHERE key = 'migrate.zz_strict_1126'", one=True)["value"])
    assert mark == {"skipped": "the list has not been applied on this database"}


def test_the_console_decisions_since_the_list_step():
    """A kept one that the Console declined since: its nomination is withdrawn, the institution left declined. One that the Console
    declined and accepted again after the list step: left as it is. One moved to another State/UT: left as it is. A mail of a
    listed institution that only carries a kept one's name is not withdrawn."""
    from kts.db import execute, init_db, query
    app = _fresh()
    declined = _insert(app, "Kept Declined College", "Puducherry", "Pondicherry", "declined", created=BEFORE, ref="KTS5-HEI-07301")
    declined_app = _application(app, declined, 21)
    again = _insert(app, "Kept Again College", "Puducherry", "Pondicherry", "accepted", created=BEFORE, ref="KTS5-HEI-07302",
                    decided_by=1, decided_at="2026-11-26T12:10:00+00:00")
    again_app = _application(app, again, 22)
    moved = _insert(app, "Kept Moved College", "Tamil Nadu", "Chennai", "accepted", created=BEFORE, ref="KTS5-HEI-07303")
    moved_app = _application(app, moved, 23)
    person = _insert(app, "Koushik Kumar Mahato", "Puducherry", "Pondicherry", "accepted", created=BEFORE, ref="KTS5-HEI-07304",
                     coord_email="kk@kept.example")
    with app.app_context():
        execute("INSERT OR REPLACE INTO settings(key, value, updated_at) VALUES('migrate.py_list_1126', ?, '2026-11-26T09:00:00+00:00')",
                (json.dumps({"kept_nominated": ["KTS5-HEI-07301", "KTS5-HEI-07302", "KTS5-HEI-07303", "KTS5-HEI-07304"]}),))
        theirs = execute("INSERT INTO outbox(to_addr, subject, body, status, created_at, priority) VALUES(?,?,?,?,?,0)",
                         ("coord@listed.example", "KTS 5.0: the nomination of Koushik Kumar Mahato is submitted", "Body", "queued", "2026-11-26T09:00:00+00:00"))
        own = execute("INSERT INTO outbox(to_addr, subject, body, status, created_at, priority) VALUES(?,?,?,?,?,0)",
                      ("kk@kept.example", "Reminder – KTS 5.0: select your student – Koushik Kumar Mahato", "Body", "queued", "2026-11-26T09:00:00+00:00"))
    init_db(app)
    assert _status(app, "institutions", declined)["status"] == "declined" and _status(app, "applications", declined_app)["status"] == "withdrawn"
    assert _status(app, "institutions", again)["status"] == "accepted" and _status(app, "applications", again_app)["status"] == "submitted"
    assert _status(app, "institutions", moved)["status"] == "accepted" and _status(app, "applications", moved_app)["status"] == "submitted"
    assert _status(app, "institutions", person)["status"] == "declined"
    assert _status(app, "outbox", theirs)["status"] == "queued" and _status(app, "outbox", own)["status"] == "failed"
    with app.app_context():
        strict = json.loads(query("SELECT value FROM settings WHERE key = 'migrate.py_strict_1126'", one=True)["value"])
    assert strict["declined"] == ["KTS5-HEI-07304"] and strict["declined_before"] == ["KTS5-HEI-07301"]
    assert strict["accepted_again"] == ["KTS5-HEI-07302"] and strict["moved_state"] == ["KTS5-HEI-07303"]
    assert strict["applications_withdrawn"] == ["KTS5-TEST-0021"]


def test_a_mark_of_another_shape_does_not_stop_the_start():
    from kts.db import execute, init_db, query
    app = _fresh()
    with app.app_context():
        execute("INSERT OR REPLACE INTO settings(key, value, updated_at) VALUES('migrate.py_list_1126', ?, '2026-11-26T09:00:00+00:00')",
                (json.dumps({"kept_nominated": 5}),))
    init_db(app)
    with app.app_context():
        assert json.loads(query("SELECT value FROM settings WHERE key = 'migrate.py_strict_1126'", one=True)["value"])["declined"] == []

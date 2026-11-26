"""
Nominations only from the institutions of the Nodal Institutions' lists in Jammu and Kashmir and Ladakh, Chhattisgarh, Jharkhand,
Madhya Pradesh and Maharashtra (1.2.226). CICT, 26 November 2026, of the institutions kept there for a submitted nomination: declined,
their nominations withdrawn, as for Puducherry (1.2.225): "Yes". The kept references of each list, once; no mail; the other lists
(Tripura, Telangana, Sikkim, Rajasthan, ...) are left as they are.

    python -m pytest tests/test_strict_all_1126.py -q
"""
import json

from conftest import make_app
from test_reserve_1111 import _insert

BEFORE = "2026-11-20T06:00:00+00:00"


def _application(app, iid, n, state):
    from kts.db import execute, utcnow
    with app.app_context():
        aid = execute("INSERT INTO applications(full_name, gender, dob, mobile, email, state, college_name, college_key, pref_lang, "
                      "created_at, updated_at, institution_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (f"Student {n}", "F", "2004-05-06", f"98761{n:05d}", f"t{n}@tests.example", state, "College", f"name:c{n}|x",
                       "hi", utcnow(), utcnow(), iid))
        execute("UPDATE applications SET app_no = ?, status = 'submitted' WHERE id = ?", (f"KTS5-STRICT-{n:04d}", aid))
        execute("UPDATE institutions SET application_id = ? WHERE id = ?", (aid, iid))
    return aid


def _entry(key):
    from kts.db import NODAL_LISTS_1126
    return next(nodal_list for nodal_list in NODAL_LISTS_1126 if nodal_list["key"] == key)


def _fresh():
    from kts.db import execute
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key LIKE 'migrate.%_strict_1126' OR key LIKE 'migrate.%_list_1126'")
    return app


def _state(app, table, iid):
    from kts.db import query
    with app.app_context():
        return query(f"SELECT status FROM {table} WHERE id = ?", (iid,), one=True)["status"]


def test_jammu_and_kashmir_maharashtra_and_not_tripura():
    from kts.db import init_db, query
    app = _fresh()
    on = _insert(app, "Altaf Memorial Government Degree College Kilam Kulgam", "Jammu and Kashmir", "Kulgam", "accepted", created=BEFORE, ref="KTS5-HEI-08691")
    on_app = _application(app, on, 1, "Jammu and Kashmir")
    off = _insert(app, "Sri Pratap College", "Jammu and Kashmir", "Srinagar", "accepted", created=BEFORE, ref="KTS5-HEI-07999")
    off_app = _application(app, off, 2, "Jammu and Kashmir")
    khaltse = _insert(app, "GOVERNMENT DEGREE COLLEGE, KHALTSE", "Ladakh", "Khaltse", "accepted", created=BEFORE, ref="KTS5-HEI-07998")
    khaltse_app = _application(app, khaltse, 3, "Ladakh")
    names = [r[0] for r in _entry("mh")["listed"]]
    mh = {n: _insert(app, n, "Maharashtra", "District", "accepted", created=BEFORE, ref=f"KTS5-HEI-01{i:03d}") for i, n in enumerate(names)}
    copy = _insert(app, "NKES COLLEGE OF ARTS COMMERCE AND SCIENCE", "Maharashtra", "Mumbai", "accepted", created=BEFORE, ref="KTS5-HEI-01900")
    copy_app = _application(app, copy, 4, "Maharashtra")
    listed_app = _application(app, mh["NKES COLLEGE OF ARTS COMMERCE AND SCIENCE"], 5, "Maharashtra")
    # Tripura: one off the list with a nomination - kept by its list, and left as it is (not among the regions CICT answered for)
    tr_names = [r[0] for r in _entry("tr")["listed"]]
    for i, n in enumerate(tr_names):
        _insert(app, n, "Tripura", "West Tripura", "accepted", created=BEFORE, ref=f"KTS5-HEI-00{i:03d}")
    tu = _insert(app, "Tripura University", "Tripura", "West Tripura District", "accepted", created=BEFORE, ref="KTS5-HEI-00900")
    tu_app = _application(app, tu, 6, "Tripura")
    init_db(app)
    assert _state(app, "institutions", on) == "accepted" and _state(app, "applications", on_app) == "submitted"
    assert _state(app, "institutions", off) == "declined" and _state(app, "applications", off_app) == "withdrawn"
    assert _state(app, "institutions", khaltse) == "declined" and _state(app, "applications", khaltse_app) == "withdrawn"
    assert _state(app, "institutions", copy) == "declined" and _state(app, "applications", copy_app) == "withdrawn"
    assert _state(app, "institutions", mh["NKES COLLEGE OF ARTS COMMERCE AND SCIENCE"]) == "accepted" and _state(app, "applications", listed_app) == "submitted"
    assert _state(app, "institutions", tu) == "accepted" and _state(app, "applications", tu_app) == "submitted"
    with app.app_context():
        jk = json.loads(query("SELECT value FROM settings WHERE key = 'migrate.jk_strict_1126'", one=True)["value"])
        mhm = json.loads(query("SELECT value FROM settings WHERE key = 'migrate.mh_strict_1126'", one=True)["value"])
        assert query("SELECT 1 FROM settings WHERE key = 'migrate.tr_strict_1126'", one=True) is None
        lines = query("SELECT action FROM audit_log WHERE actor = 'release 1.2.226'")
    assert sorted(jk["applications_withdrawn"]) == ["KTS5-STRICT-0002", "KTS5-STRICT-0003"] and mhm["applications_withdrawn"] == ["KTS5-STRICT-0004"]
    assert sorted(r["action"] for r in lines) == ["application_withdrawn"] * 3 + ["institution_declined"] * 3


def test_once_and_a_list_that_kept_nothing():
    from kts.db import execute, init_db, query
    app = _fresh()
    stray = _insert(app, "Some College", "Madhya Pradesh", "Bhopal", "accepted", created=BEFORE, ref="KTS5-HEI-02990")
    stray_app = _application(app, stray, 7, "Madhya Pradesh")
    init_db(app)       # the list of Madhya Pradesh does not match here (skipped): it kept nothing, so nothing is declined
    assert _state(app, "institutions", stray) == "accepted" and _state(app, "applications", stray_app) == "submitted"
    with app.app_context():
        assert json.loads(query("SELECT value FROM settings WHERE key = 'migrate.mp_strict_1126'", one=True)["value"])["declined"] == []
        execute("UPDATE institutions SET status = 'accepted' WHERE status = 'declined'")
    init_db(app)          # once: CICT may accept one again
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM institutions WHERE status = 'declined'", one=True)["n"] == 0


def test_no_mail():
    from kts.db import init_db, query
    app = _fresh()
    off = _insert(app, "Sri Pratap College", "Jammu and Kashmir", "Srinagar", "accepted", created=BEFORE, ref="KTS5-HEI-07999")
    _application(app, off, 8, "Jammu and Kashmir")
    with app.app_context():
        mails = query("SELECT COUNT(*) AS n FROM outbox", one=True)["n"]
    init_db(app)
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM outbox", one=True)["n"] == mails

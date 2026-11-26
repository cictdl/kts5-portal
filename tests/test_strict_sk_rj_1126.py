"""
Nominations only from the institutions of the lists of Sikkim and Rajasthan (1.2.227). CICT, 26 November 2026: "yes, decline Sikkim and
Rajasthan too". The institutions their list steps kept for a submitted nomination are declined and those nominations withdrawn, once,
as in 1.2.225/1.2.226; no mail; Telangana and Tripura are left as they are.

    python -m pytest tests/test_strict_sk_rj_1126.py -q
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
                      (f"Student {n}", "F", "2004-05-06", f"98762{n:05d}", f"u{n}@tests.example", state, "College", f"name:c{n}|y",
                       "hi", utcnow(), utcnow(), iid))
        execute("UPDATE applications SET app_no = ?, status = 'submitted' WHERE id = ?", (f"KTS5-SKRJ-{n:04d}", aid))
        execute("UPDATE institutions SET application_id = ? WHERE id = ?", (aid, iid))
    return aid


def _entry(key):
    from kts.db import NODAL_LISTS_1126
    return next(nodal_list for nodal_list in NODAL_LISTS_1126 if nodal_list["key"] == key)


def _state(app, table, iid):
    from kts.db import query
    with app.app_context():
        return query(f"SELECT status FROM {table} WHERE id = ?", (iid,), one=True)["status"]


def test_sikkim_and_rajasthan():
    from kts.db import execute, init_db, query
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key LIKE 'migrate.%_strict_1126' OR key LIKE 'migrate.%_list_1126'")
    sk = _entry("sk")
    for name, *_rest in sk["listed"]:
        _insert(app, name, "Sikkim", "District", "accepted", created=BEFORE, ref=sk["match"][name]["ref"])
    dentam = _insert(app, "Sikkim Government Vocational College Dentam", "Sikkim", "Gyalshing", "accepted", created=BEFORE, ref="KTS5-HEI-09030")
    dentam_app = _application(app, dentam, 1, "Sikkim")
    rj_names = [r[0] for r in _entry("rj")["listed"]]
    rj = {n: _insert(app, n, "Rajasthan", "District", "accepted", created=BEFORE, ref=f"KTS5-HEI-05{i:03d}") for i, n in enumerate(rj_names)}
    kallaji = _insert(app, "Shri Kallaji vedic vishavavidhyalaya Jawda, Nimbaheda , chittorgarh (Rajasthan)", "Rajasthan", "Chittorgarh",
                      "accepted", created=BEFORE, ref="KTS5-HEI-09031")
    kallaji_app = _application(app, kallaji, 2, "Rajasthan")
    listed_app = _application(app, rj["Agriculture University, Kota"], 3, "Rajasthan")
    tu = _insert(app, "Tripura University", "Tripura", "West Tripura District", "accepted", created=BEFORE, ref="KTS5-HEI-00900")
    for i, (name, *_rest) in enumerate(_entry("tr")["listed"]):
        _insert(app, name, "Tripura", "West Tripura", "accepted", created=BEFORE, ref=f"KTS5-HEI-00{i:03d}")
    tu_app = _application(app, tu, 4, "Tripura")
    with app.app_context():
        mails = query("SELECT COUNT(*) AS n FROM outbox", one=True)["n"]
    init_db(app)
    assert _state(app, "institutions", dentam) == "declined" and _state(app, "applications", dentam_app) == "withdrawn"
    assert _state(app, "institutions", kallaji) == "declined" and _state(app, "applications", kallaji_app) == "withdrawn"
    assert _state(app, "applications", listed_app) == "submitted" and _state(app, "institutions", rj["Agriculture University, Kota"]) == "accepted"
    assert _state(app, "institutions", tu) == "accepted" and _state(app, "applications", tu_app) == "submitted"      # Tripura: not asked
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM outbox", one=True)["n"] == mails
        skm = json.loads(query("SELECT value FROM settings WHERE key = 'migrate.sk_strict_1126'", one=True)["value"])
        rjm = json.loads(query("SELECT value FROM settings WHERE key = 'migrate.rj_strict_1126'", one=True)["value"])
        lines = query("SELECT action FROM audit_log WHERE actor = 'release 1.2.227'")
    assert skm["declined"] == ["KTS5-HEI-09030"] and rjm["declined"] == ["KTS5-HEI-09031"]
    assert sorted(r["action"] for r in lines) == ["application_withdrawn"] * 2 + ["institution_declined"] * 2

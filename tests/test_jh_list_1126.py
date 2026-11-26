"""
The list of the Nodal Institution of Jharkhand (1.2.222). CICT, 26 November 2026, with the file "Result_KTS5.0" of the Central
University of Jharkhand (20 selected and 4 reserved of the 41 registered): "Jharkhand"; the 4 reserved: "Keep the 4". The 24 stay;
the others of Jharkhand registered up to 3:00 PM IST are declined, as the lists of 1.2.220. "Jharkhand state Open university" is
registered twice: the one of Ranchi is on the list (its district tells it apart), the one of Garhwa is declined.

    python -m pytest tests/test_jh_list_1126.py -q
"""
import json

from conftest import make_app
from test_reserve_1111 import _insert

MARK = "migrate.jh_list_1126"
BEFORE = "2026-11-20T06:00:00+00:00"
OFF = ["B.S. College Lohardga", "BABU DINESH SINGH UNIVERSITY", "Cambridge Institute of Technology", "DEGREE COLLEGE GOMIA",
       "Government engineering College bokaro", "Government Polytechnic Kharsawan", "Jagannath Nagar College, Dhurwa",
       "Jamshedpur women university", "K.B. WOMEN'S COLLEGE HAZARIBAG", "Koushik Kumar Mahato", "Model college, pakur",
       "NILAI EDUCATIONAL TRUST'S GROUP OF INSTITUTIONS", "PARASNATH MAHAVIDYALAY, ISRI BAZAR", "Ramgovind Institute of Technology",
       "S.S.L.N.T. Mahila Mahavidyalaya", "Tata College, Chaibasa"]


def _listed():
    from kts.db import NODAL_LISTS_1126
    return next(nodal_list for nodal_list in NODAL_LISTS_1126 if nodal_list["key"] == "jh")


def test_the_list():
    from kts.db import NODAL_LISTS_1126
    jh = _listed()
    names = [r[0] for r in jh["listed"]]
    assert jh["state"] == "Jharkhand" and len(names) == 24 and all(r[1:] == ("", "", "") for r in jh["listed"])
    assert names[0] == "Central University of Jharkhand" and names[-4:] == [
        "Bindeshwari Dubey Awasiya Mahavidyalaya, Pichhri, Bermo, Bokaro", "Government Engineering College Godda",
        "KRISHNA BALLAV COLLEGE, BERMO", "Netaji Subhas University Jamshedpur"]          # the 4 reserved, kept
    assert jh["match"] == {"Jharkhand state Open university": {"district": "RANCHI"}} and jh["release"] == "release 1.2.222"
    assert jh["until"] == "2026-11-26T09:30:00+00:00"
    assert jh["note"] == ("Not among the 24 institutions of the list of the Nodal Institution of Jharkhand (Central University of "
                          "Jharkhand), 26 November 2026")
    assert [nodal_list["key"] for nodal_list in NODAL_LISTS_1126][:5] == ["py", "ap", "cg", "hp", "jh"]
    assert not set(OFF) & set(names)


def test_the_17_not_on_the_list_are_declined_and_the_ranchi_open_university_stays():
    from kts.db import execute, init_db, query
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key = ?", (MARK,))
    names = [r[0] for r in _listed()["listed"]]
    ids = {}
    for n, name in enumerate(names + OFF):
        district = "RANCHI" if name == "Jharkhand state Open university" else "District"
        ids[name] = _insert(app, name, "Jharkhand", district, "accepted", created=BEFORE, ref=f"KTS5-HEI-03{n:03d}")
    garhwa = _insert(app, "JHARKHAND STATE OPEN UNIVERSITY", "Jharkhand", "Garhwa", "accepted", created=BEFORE, ref="KTS5-HEI-03100")
    init_db(app)
    with app.app_context():
        status = {r["id"]: r["status"] for r in query("SELECT id, status FROM institutions WHERE state = 'Jharkhand'")}
        mark = json.loads(query("SELECT value FROM settings WHERE key = ?", (MARK,), one=True)["value"])
    assert all(status[ids[n]] == "accepted" for n in names)
    assert all(status[ids[n]] == "declined" for n in OFF) and status[garhwa] == "declined"
    assert len(mark["listed"]) == 24 and len(mark["declined"]) == 17 and ids["Jharkhand state Open university"] and "skipped" not in mark


def test_without_the_district_the_list_would_do_nothing():
    """The one-to-one safety of 1.2.220 stands: a name that two rows carry and no district tells apart stops the whole list."""
    from kts import db
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        db.execute("DELETE FROM settings WHERE key = 'migrate.zz_list_1126'")
    a = _insert(app, "Same College", "Jharkhand", "Ranchi", "accepted", created=BEFORE, ref="KTS5-HEI-03201")
    b = _insert(app, "SAME COLLEGE", "Jharkhand", "Garhwa", "accepted", created=BEFORE, ref="KTS5-HEI-03202")
    c = _insert(app, "Other College", "Jharkhand", "Ranchi", "accepted", created=BEFORE, ref="KTS5-HEI-03203")
    entry = {"key": "zz", "state": "Jharkhand", "until": "2026-11-26T09:30:00+00:00", "note": "test", "listed": (("Same College", "", "", ""),)}
    with app.app_context():
        conn = db.get_db()
        db._apply_nodal_list(conn, db.utcnow(), entry)
        conn.commit()
        mark = json.loads(db.query("SELECT value FROM settings WHERE key = 'migrate.zz_list_1126'", one=True)["value"])
        status = {r["id"]: r["status"] for r in db.query("SELECT id, status FROM institutions")}
    assert mark["skipped"].startswith("the list does not match") and status[a] == status[b] == status[c] == "accepted"
    with app.app_context():
        db.execute("DELETE FROM settings WHERE key = 'migrate.zz_list_1126'")
        conn = db.get_db()
        db._apply_nodal_list(conn, db.utcnow(), dict(entry, match={"Same College": {"district": "RANCHI"}}))
        conn.commit()
        status = {r["id"]: r["status"] for r in db.query("SELECT id, status FROM institutions")}
    assert (status[a], status[b], status[c]) == ("accepted", "declined", "declined")

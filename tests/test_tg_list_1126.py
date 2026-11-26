"""
The list of the Nodal Institution of Telangana (1.2.224). CICT, 26 November 2026, with the file "AnnexureII_FormatforListofInstitutions
SelectedbytheHEI_Telangana" of the University of Hyderabad (28 selected): "Telangana". 27 are found by their portal reference, whatever
their names on the portal; Avinash College of Commerce by its name and district. The others are declined, as the lists of 1.2.220.

    python -m pytest tests/test_tg_list_1126.py -q
"""
import json

from conftest import make_app
from test_reserve_1111 import _insert

MARK = "migrate.tg_list_1126"
BEFORE = "2026-11-20T06:00:00+00:00"


def _listed():
    from kts.db import NODAL_LISTS_1126
    return next(nodal_list for nodal_list in NODAL_LISTS_1126 if nodal_list["key"] == "tg")


def test_the_list():
    from kts.db import NODAL_LISTS_1126
    tg = _listed()
    assert tg["state"] == "Telangana" and len(tg["listed"]) == 28 and tg["release"] == "release 1.2.224"
    refs = [spec["ref"] for spec in tg["match"].values() if "ref" in spec]
    assert len(refs) == len(set(refs)) == 27 and all(r.startswith("KTS5-HEI-") and len(r) == 14 for r in refs)
    assert tg["match"]["Avinash college of commerce"] == {"district": "Rangareddy"}
    assert tg["match"]["Gurram bala narasaya institute of pharmacy"] == {"ref": "KTS5-HEI-01142"}
    assert [nodal_list["key"] for nodal_list in NODAL_LISTS_1126][:9] == ["py", "ap", "cg", "hp", "jh", "mp", "mh", "tr", "tg"]


def test_found_by_reference_whatever_the_name():
    from kts.db import execute, init_db, query
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key = ?", (MARK,))
    tg = _listed()
    ids = {}
    for i, (name, *_rest) in enumerate(tg["listed"]):
        spec = tg["match"][name]
        if "ref" in spec:      # the portal's name differs from the list's: the reference finds it
            ids[name] = _insert(app, f"Portal name {i}", "Telangana", "District", "accepted", created=BEFORE, ref=spec["ref"])
    avinash = _insert(app, "Avinash college of commerce", "Telangana", "Rangareddy", "accepted", created=BEFORE, ref="KTS5-HEI-09001")
    avinash_2 = _insert(app, "Avinash College of Commerce", "Telangana", "Hyderabad", "accepted", created=BEFORE, ref="KTS5-HEI-09002")
    omega = _insert(app, "OMEGA INSTITUTE OF SCIENCE AND TECHNOLOGY(A)", "Telangana", "Medchal", "accepted", created=BEFORE, ref="KTS5-HEI-09003")
    # a registration that carries a listed name but another reference is not taken for it
    other = _insert(app, "Malla Reddy Engineering College", "Telangana", "medchal", "accepted", created=BEFORE, ref="KTS5-HEI-09004")
    init_db(app)
    with app.app_context():
        status = {r["id"]: r["status"] for r in query("SELECT id, status FROM institutions WHERE state = 'Telangana'")}
        mark = json.loads(query("SELECT value FROM settings WHERE key = ?", (MARK,), one=True)["value"])
    assert len(ids) == 27 and all(status[i] == "accepted" for i in ids.values()) and status[avinash] == "accepted"
    assert status[avinash_2] == status[omega] == status[other] == "declined"
    assert len(mark["listed"]) == 28 and sorted(mark["declined"]) == ["KTS5-HEI-09002", "KTS5-HEI-09003", "KTS5-HEI-09004"]


def test_a_reference_that_is_not_there_stops_the_list():
    from kts.db import execute, init_db, query
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key = ?", (MARK,))
    some = _insert(app, "Some College", "Telangana", "District", "accepted", created=BEFORE, ref="KTS5-HEI-09010")
    init_db(app)
    with app.app_context():
        mark = json.loads(query("SELECT value FROM settings WHERE key = ?", (MARK,), one=True)["value"])
        assert query("SELECT status FROM institutions WHERE id = ?", (some,), one=True)["status"] == "accepted"
    assert mark["skipped"].startswith("the list does not match")


def test_sikkim_by_its_references():
    from kts.db import NODAL_LISTS_1126, execute, init_db, query
    sk = next(nodal_list for nodal_list in NODAL_LISTS_1126 if nodal_list["key"] == "sk")
    assert sk["state"] == "Sikkim" and len(sk["listed"]) == 10 and all("ref" in spec for spec in sk["match"].values())
    assert [nodal_list["key"] for nodal_list in NODAL_LISTS_1126][:10] == ["py", "ap", "cg", "hp", "jh", "mp", "mh", "tr", "tg", "sk"]
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key = 'migrate.sk_list_1126'")
    ids = [_insert(app, name, "Sikkim", "District", "accepted", created=BEFORE, ref=sk["match"][name]["ref"]) for name, *_rest in sk["listed"]]
    off = _insert(app, "Sikkim Sardar Patel University", "Sikkim", "Namchi District", "accepted", created=BEFORE, ref="KTS5-HEI-09020")
    init_db(app)
    with app.app_context():
        status = {r["id"]: r["status"] for r in query("SELECT id, status FROM institutions WHERE state = 'Sikkim'")}
    assert all(status[i] == "accepted" for i in ids) and status[off] == "declined"


def test_rajasthan():
    from kts.db import NODAL_LISTS_1126, execute, init_db, query
    rj = next(nodal_list for nodal_list in NODAL_LISTS_1126 if nodal_list["key"] == "rj")
    names = [r[0] for r in rj["listed"]]
    assert rj["state"] == "Rajasthan" and len(names) == 53 and names[0] == "Agriculture University, Kota"
    assert "COLLEGE OF HORTICULTURE AND FORESTRY. JHALAWAR" in names
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key = 'migrate.rj_list_1126'")
    ids = [_insert(app, n, "Rajasthan", "District", "accepted", created=BEFORE, ref=f"KTS5-HEI-05{i:03d}") for i, n in enumerate(names)]
    copy = _insert(app, "College of Horticulture and forestry, Jhalawar", "Rajasthan", "JHalawar", "accepted", created=BEFORE, ref="KTS5-HEI-05900")
    init_db(app)
    with app.app_context():
        status = {r["id"]: r["status"] for r in query("SELECT id, status FROM institutions WHERE state = 'Rajasthan'")}
    assert all(status[i] == "accepted" for i in ids) and status[copy] == "declined"

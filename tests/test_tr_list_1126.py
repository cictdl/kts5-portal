"""
The list of the Nodal Institution of Tripura (1.2.223). CICT, 26 November 2026, with the file "KTS5-Annexure-II-selected-institutions"
of Tripura University (7 selected of the 8 registered): "Tripura". The 7 stay; the other registered up to 3:20 PM IST is declined, as
the lists of 1.2.220 - on the live list "Tripura University" itself, whose "Department of Sanskrit" is on the list.

    python -m pytest tests/test_tr_list_1126.py -q
"""
import json

from conftest import make_app
from test_reserve_1111 import _insert

MARK = "migrate.tr_list_1126"
BEFORE = "2026-11-20T06:00:00+00:00"


def _listed():
    from kts.db import NODAL_LISTS_1126
    return next(nodal_list for nodal_list in NODAL_LISTS_1126 if nodal_list["key"] == "tr")


def test_the_list():
    from kts.db import NODAL_LISTS_1126
    tr = _listed()
    names = [r[0] for r in tr["listed"]]
    assert tr["state"] == "Tripura" and len(names) == 7 and "Department of Sanskrit" in names and "Tripura University" not in names
    assert tr["release"] == "release 1.2.223" and tr["until"] == "2026-11-26T09:50:00+00:00"
    assert tr["note"] == "Not among the 7 institutions of the list of the Nodal Institution of Tripura (Tripura University), 26 November 2026"
    assert [nodal_list["key"] for nodal_list in NODAL_LISTS_1126][:8] == ["py", "ap", "cg", "hp", "jh", "mp", "mh", "tr"]


def test_the_one_not_on_the_list_is_declined():
    from kts.db import execute, init_db, query
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key = ?", (MARK,))
    names = [r[0] for r in _listed()["listed"]]
    ids = {n: _insert(app, n, "Tripura", "West Tripura", "accepted", created=BEFORE, ref=f"KTS5-HEI-00{i:03d}") for i, n in enumerate(names)}
    tu = _insert(app, "Tripura University", "Tripura", "West Tripura District", "accepted", created=BEFORE, ref="KTS5-HEI-00900")
    init_db(app)
    with app.app_context():
        status = {r["id"]: r["status"] for r in query("SELECT id, status FROM institutions WHERE state = 'Tripura'")}
        mark = json.loads(query("SELECT value FROM settings WHERE key = ?", (MARK,), one=True)["value"])
    assert all(status[i] == "accepted" for i in ids.values()) and status[tu] == "declined"
    assert mark["declined"] == ["KTS5-HEI-00900"] and len(mark["listed"]) == 7

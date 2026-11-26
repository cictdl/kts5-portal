"""
The list of the Nodal Institution of Chhattisgarh (1.2.220). CICT, 26 November 2026, with the file "KTS5_Chhattisgarh_Selected_
Institutions - Sent to CICT - 23-11-2026" (20 institutions of the 25 registered): "Chhattisgarh". The 20 stay as they are, details
and all; the others of Chhattisgarh registered up to 2:30 PM IST are declined, as those of Puducherry and Andhra Pradesh. On the live
site that is five.

    python -m pytest tests/test_cg_list_1126.py -q
"""
import json

from conftest import make_app
from test_reserve_1111 import _insert

MARK = "migrate.cg_list_1126"
BEFORE = "2026-11-20T06:00:00+00:00"
OFF = ["Chaitanya College, Pamgarh", "Hidayatullah National Law University", "Saraswati Mahavidyalay Koni Bilaspur",
       "Sarswati mahavidyalaya subhashnagar ambikapur surguja Chattisgarh",
       "Shri Shankaracharya Institute of Professional Management & Technology Raipur"]


def _listed():
    from kts.db import NODAL_LISTS_1126
    return next(nodal_list for nodal_list in NODAL_LISTS_1126 if nodal_list["key"] == "cg")


def test_the_list():
    cg = _listed()
    names = [r[0] for r in cg["listed"]]
    assert cg["state"] == "Chhattisgarh" and len(names) == 20 and all(r[1:] == ("", "", "") for r in cg["listed"])
    assert names[0] == "ACHARYA PANTH SHRI GRINDH MUNI NAAM SAHEB GOVT. P.G. COLLEGE, KAWARDHA DIST. KABIRDHAM (C.G.)"
    assert "GOVT WWP GIRLS' PG COLLEGE DURG (C.G.)" in names and names[-1] == "Shri Shankaracharya Professional University, Bhilai"
    assert not set(OFF) & set(names)
    assert cg["until"] == "2026-11-26T09:00:00+00:00"
    assert cg["note"] == ("Not among the 20 institutions of the list of the Nodal Institution of Chhattisgarh (Guru Ghasidas "
                          "Vishwavidyalaya), 26 November 2026")


def test_the_five_not_on_the_list_are_declined_and_the_20_stay_as_they_are():
    from kts.db import execute, init_db, query
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key = ?", (MARK,))
    names = [r[0] for r in _listed()["listed"]]
    ids = {name: _insert(app, name, "Chhattisgarh", "District", "accepted", created=BEFORE, ref=f"KTS5-HEI-05{n:03d}",
                         coord_email=f"coord{n}@cg.example") for n, name in enumerate(names + OFF)}
    init_db(app)
    with app.app_context():
        status = {r["name"]: r["status"] for r in query("SELECT name, status FROM institutions WHERE state = 'Chhattisgarh'")}
        emails = {r["name"]: r["coord_email"] for r in query("SELECT name, coord_email FROM institutions WHERE state = 'Chhattisgarh'")}
        mark = json.loads(query("SELECT value FROM settings WHERE key = ?", (MARK,), one=True)["value"])
    assert all(status[n] == "accepted" for n in names) and all(status[n] == "declined" for n in OFF)
    assert all(emails[n] == f"coord{i}@cg.example" for i, n in enumerate(names))
    assert len(mark["listed"]) == 20 and len(mark["declined"]) == 5 and mark["changed"] == []
    assert ids

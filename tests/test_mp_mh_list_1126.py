"""
The lists of the Nodal Institutions of Madhya Pradesh and Maharashtra (1.2.222). CICT, 26 November 2026, with the files "Final
Selected List _75_KTS5_Institutions_Madhya_Pradesh" (74 marked Selected) and "KTS5_Maharashtra_Evaluation_115_23_Final" (115
selected and a waitlist of 23, kept): "Madhya Pradesh", "Maharashtra". As the lists of 1.2.220; names registered more than once are
told apart by fields of their registration, or, where the copies are alike, the oldest stays.

    python -m pytest tests/test_mp_mh_list_1126.py -q
"""
import json

from conftest import make_app
from test_reserve_1111 import _insert

BEFORE = "2026-11-20T06:00:00+00:00"


def _entry(key):
    from kts.db import NODAL_LISTS_1126
    return next(nodal_list for nodal_list in NODAL_LISTS_1126 if nodal_list["key"] == key)


def _fresh(mark):
    from kts.db import execute
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key = ?", (mark,))
    return app


def _status(app, state):
    from kts.db import query
    with app.app_context():
        return {r["id"]: r["status"] for r in query("SELECT id, status FROM institutions WHERE state = ?", (state,))}


def _mark(app, mark):
    from kts.db import query
    with app.app_context():
        return json.loads(query("SELECT value FROM settings WHERE key = ?", (mark,), one=True)["value"])


def test_the_lists():
    from kts.db import NODAL_LISTS_1126
    mp, mh = _entry("mp"), _entry("mh")
    assert len(mp["listed"]) == 74 and len(mh["listed"]) == 138
    names = [r[0] for r in mp["listed"]]
    assert "JIWAJI UNIVERSITY, GWALIOR (MP)" in names and "Awadhesh Pratap Singh University" in names and "SCHOOL OF PLANNING AND ARCHITECTURE" in names
    assert mp["match"]["Lakshmi Narain college of technology"] == {"itype": "Engineering college"}
    assert mp["match"]["Devi Ahilya Vishwavidyalaya, Indore"] == {"aishe_code": "U-0270", "first": True}
    mh_names = [r[0] for r in mh["listed"]]
    assert mh_names[0] == "Shri shahaji chhatrapati mahavidyalaya Kolhapur" and mh_names[-1] == "Nava Samaj Mandal Degree College"
    assert any("_x0092_s, Adarsh Institute of Technology" in n for n in mh_names)       # as the portal has the name
    assert mh["match"] == {"NKES COLLEGE OF ARTS COMMERCE AND SCIENCE": {"first": True}, "Sanpada college of commerce and technology": {"first": True}}
    assert [nodal_list["key"] for nodal_list in NODAL_LISTS_1126][:7] == ["py", "ap", "cg", "hp", "jh", "mp", "mh"]


def test_madhya_pradesh():
    app = _fresh("migrate.mp_list_1126")
    names = [r[0] for r in _entry("mp")["listed"]]
    plain = [n for n in names if n not in ("Devi Ahilya Vishwavidyalaya, Indore", "Dr Harisingh Gour University, Sagar, Madhya Pradesh",
                                           "Lakshmi Narain college of technology", "Government polytechnic College Shajapur")]
    ids = {n: _insert(app, n, "Madhya Pradesh", "District", "accepted", created=BEFORE, ref=f"KTS5-HEI-02{i:03d}") for i, n in enumerate(plain)}
    dav_off = _insert(app, "Devi Ahilya Vishwavidyalaya, Indore", "Madhya Pradesh", "INDORE", "accepted", created=BEFORE, ref="KTS5-HEI-02900", aishe_code="")
    dav = _insert(app, "Devi Ahilya Vishwavidyalaya, Indore", "Madhya Pradesh", "INDORE", "accepted", created=BEFORE, ref="KTS5-HEI-02901", aishe_code="U-0270")
    hgu = _insert(app, "Dr Harisingh Gour University, Sagar, Madhya Pradesh", "Madhya Pradesh", "Sagar", "accepted", created=BEFORE, ref="KTS5-HEI-02902",
                  coord_email="someone@else.example")      # its e-mail is not the list's: the only copy is taken all the same ("first")
    lnct_off = _insert(app, "Lakshmi Narain College of Technology", "Madhya Pradesh", "Bhopal", "accepted", created=BEFORE, ref="KTS5-HEI-02903",
                       itype="Private / self-financing college")
    lnct = _insert(app, "Lakshmi Narain college of technology", "Madhya Pradesh", "Bhopal", "accepted", created=BEFORE, ref="KTS5-HEI-02904",
                   itype="Engineering college")
    poly_off = _insert(app, "GOVERNMENT POLYTECHNIC COLLEGE SHAJAPUR", "Madhya Pradesh", "Shajapur", "accepted", created=BEFORE, ref="KTS5-HEI-02905",
                       itype="Government college")
    poly = _insert(app, "Government polytechnic College Shajapur", "Madhya Pradesh", "Shajapur", "accepted", created=BEFORE, ref="KTS5-HEI-02906",
                   itype="Engineering college")
    off = _insert(app, "Avantika Avantika Dwivedi", "Madhya Pradesh", "SATNA", "accepted", created=BEFORE, ref="KTS5-HEI-02907")
    from kts.db import init_db
    init_db(app)
    status = _status(app, "Madhya Pradesh")
    assert all(status[i] == "accepted" for i in ids.values()) and all(status[i] == "accepted" for i in (dav, hgu, lnct, poly))
    assert all(status[i] == "declined" for i in (dav_off, lnct_off, poly_off, off))
    mark = _mark(app, "migrate.mp_list_1126")
    assert len(mark["listed"]) == 74 and len(mark["declined"]) == 4 and "skipped" not in mark


def test_maharashtra_keeps_the_oldest_of_alike_copies():
    app = _fresh("migrate.mh_list_1126")
    names = [r[0] for r in _entry("mh")["listed"]]
    ids = {n: _insert(app, n, "Maharashtra", "District", "accepted", created=BEFORE, ref=f"KTS5-HEI-01{i:03d}") for i, n in enumerate(names)}
    nkes_copy = _insert(app, "NKES COLLEGE OF ARTS COMMERCE AND SCIENCE", "Maharashtra", "Mumbai", "accepted", created=BEFORE, ref="KTS5-HEI-01900")
    sanpada_copy = _insert(app, "Sanpada college of commerce and Technology", "Maharashtra", "Thane", "accepted", created=BEFORE, ref="KTS5-HEI-01901")
    off = _insert(app, "USHA MORE", "Maharashtra", "THANE, NAVI MUMBAI", "accepted", created=BEFORE, ref="KTS5-HEI-01902")
    from kts.db import init_db
    init_db(app)
    status = _status(app, "Maharashtra")
    assert all(status[i] == "accepted" for i in ids.values())
    assert status[nkes_copy] == status[sanpada_copy] == status[off] == "declined"
    mark = _mark(app, "migrate.mh_list_1126")
    assert len(mark["listed"]) == 138 and sorted(mark["declined"]) == ["KTS5-HEI-01900", "KTS5-HEI-01901", "KTS5-HEI-01902"]

"""
The list of the Nodal Institution of Himachal Pradesh (1.2.221). CICT, 26 November 2026, with the file "KTS5-Institutions_Himachal
Pradesh" (19 of the 20 registered): "Himachal Pradesh". The 19 stay as they are; the others of Himachal Pradesh registered up to
2:35 PM IST are declined, as the lists of 1.2.220. On the live site that is one: GGDSD College Rajpur Palampur.

    python -m pytest tests/test_hp_list_1126.py -q
"""
import json

from conftest import make_app
from test_reserve_1111 import _insert

MARK = "migrate.hp_list_1126"
BEFORE = "2026-11-20T06:00:00+00:00"
OFF = "GGDSD College Rajpur Palampur"


def _listed():
    from kts.db import NODAL_LISTS_1126
    return next(nodal_list for nodal_list in NODAL_LISTS_1126 if nodal_list["key"] == "hp")


def test_the_list():
    from kts.db import NODAL_LISTS_1126
    hp = _listed()
    names = [r[0] for r in hp["listed"]]
    assert hp["state"] == "Himachal Pradesh" and len(names) == 19 and all(r[1:] == ("", "", "") for r in hp["listed"])
    assert names[0] == "Career Point University, Hamirpur" and names[-1] == "Sanatan dharam adarsh sanskrit college, Dohgi"
    assert OFF not in names and hp["until"] == "2026-11-26T09:05:00+00:00" and hp["release"] == "release 1.2.221"
    assert hp["note"] == ("Not among the 19 institutions of the list of the Nodal Institution of Himachal Pradesh (Central University "
                          "of Himachal Pradesh), 26 November 2026")
    # the lists of 1.2.220 are there as they were
    assert [nodal_list["key"] for nodal_list in NODAL_LISTS_1126] == ["py", "ap", "cg", "hp"]
    assert all("release" not in nodal_list for nodal_list in NODAL_LISTS_1126[:3])


def test_the_one_not_on_the_list_is_declined_once():
    from kts.db import execute, init_db, query
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key = ?", (MARK,))
    names = [r[0] for r in _listed()["listed"]]
    for n, name in enumerate(names + [OFF]):
        _insert(app, name, "Himachal Pradesh", "District", "accepted", created=BEFORE, ref=f"KTS5-HEI-04{n:03d}")
    with app.app_context():
        mail = execute("INSERT INTO outbox(to_addr, subject, body, status, created_at, priority) VALUES(?,?,?,?,?,0)",
                       ("x@y.example", f"Reminder – KTS 5.0: select your student – {OFF}", "Body", "queued", "2026-11-26T09:00:00+00:00"))
        audits = query("SELECT COUNT(*) AS n FROM audit_log", one=True)["n"]
    init_db(app)
    with app.app_context():
        status = {r["name"]: r["status"] for r in query("SELECT name, status FROM institutions WHERE state = 'Himachal Pradesh'")}
        lines = query("SELECT actor, action FROM audit_log ORDER BY id")[audits:]
        mark = json.loads(query("SELECT value FROM settings WHERE key = ?", (MARK,), one=True)["value"])
        withdrawn = query("SELECT status, error FROM outbox WHERE id = ?", (mail,), one=True)
    assert all(status[n] == "accepted" for n in names) and status[OFF] == "declined"
    assert [(r["actor"], r["action"]) for r in lines] == [("release 1.2.221", "institution_declined")]
    assert (withdrawn["status"], withdrawn["error"]) == ("failed", "withdrawn: the institution is declined (1.2.221)")
    assert len(mark["listed"]) == 19 and mark["declined"] == [f"KTS5-HEI-04{19:03d}"] and mark["mails_withdrawn"] == 1
    init_db(app)
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM audit_log", one=True)["n"] == audits + 1

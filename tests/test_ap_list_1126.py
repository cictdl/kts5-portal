"""
The list of the Nodal Institution of Andhra Pradesh (1.2.220). CICT, 26 November 2026, with the file "KTS5_Institutions Selected
Andhra_Pradesh" (17 institutions; the portal's own Annexure-II of 22 November): "Andhra Pradesh". The 17 stay as they are, details
and all; the others of Andhra Pradesh registered up to 2:25 PM IST are declined, as those of Puducherry (tests/test_py_list_1126.py).
On the live site that is one: Government Degree College, Tirupati.

    python -m pytest tests/test_ap_list_1126.py -q
"""
import json

from conftest import make_app
from test_reserve_1111 import _insert

MARK = "migrate.ap_list_1126"
BEFORE = "2026-11-20T06:00:00+00:00"
LISTED = ["ACHARYA NAGARJUNA UNIVERSITY", "Audisankara University", "Central Tribal University of Andhra Pradesh",
          "Central Unibversity of Andhra Pradesh", "Dr RVR NRI Institute of Technology",
          "Gandhi Institute of Technology and Management Deemed to be University", "Godavari Global University",
          "Government College (A), Ananthapuramu", "IIITDM kurnool", "Krea University", "National Sanskrit University, Turupati",
          "Sarat Chandra Degree College", "SGT & JVB DEGREE COLLEGE(149)THULLUR", "Sri Gorantla Venkanna Oriental College",
          "Sri Sathya Sai Institute of Higher Learning", "SVJV SANSKRIT COLLEGE", "Vignan institute of engineering for women"]


def test_the_list():
    from kts.db import NODAL_LISTS_1126
    ap = next(nodal_list for nodal_list in NODAL_LISTS_1126 if nodal_list["key"] == "ap")
    assert ap["state"] == "Andhra Pradesh" and [r[0] for r in ap["listed"]] == LISTED
    assert all(r[1:] == ("", "", "") for r in ap["listed"])          # nothing of the 17 changes
    assert ap["until"] == "2026-11-26T08:55:00+00:00"
    assert ap["note"] == ("Not among the 17 institutions of the list of the Nodal Institution of Andhra Pradesh (Central University of "
                          "Andhra Pradesh), 26 November 2026")


def test_the_one_not_on_the_list_is_declined_and_the_17_stay_as_they_are():
    from kts.db import execute, init_db, query
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key IN (?, 'migrate.py_list_1126')", (MARK,))
    ids = {name: _insert(app, name, "Andhra Pradesh", "District", "accepted", created=BEFORE, ref=f"KTS5-HEI-06{n:03d}",
                         coord_email=f"coord{n}@ap.example", head_email=f"head{n}@ap.example", coord_mobile=f"90000001{n:02d}")
           for n, name in enumerate(LISTED)}
    tirupati = _insert(app, "Government Degree College", "Andhra Pradesh", "Tirupati", "accepted", created=BEFORE, ref="KTS5-HEI-06100")
    later = _insert(app, "Later College", "Andhra Pradesh", "Guntur", "accepted", created="2026-11-26T09:30:00+00:00", ref="KTS5-HEI-06101")
    # another college whose name holds "Government Degree College": its mails stay; the declined one's (by its reference) go
    kangan = _insert(app, "Government Degree College Kangan", "Jammu and Kashmir", "Ganderbal", "accepted", created=BEFORE, ref="KTS5-HEI-06102")
    with app.app_context():
        theirs = execute("INSERT INTO outbox(to_addr, subject, body, status, created_at, priority) VALUES(?,?,?,?,?,0)",
                         ("c@k.example", "KTS 5.0: Government Degree College Kangan is registered as a Participating Institution (KTS5-HEI-06102)",
                          "Body", "queued", "2026-11-26T09:00:00+00:00"))
        ours = execute("INSERT INTO outbox(to_addr, subject, body, status, created_at, priority) VALUES(?,?,?,?,?,0)",
                       ("c@t.example", "KTS 5.0: Government Degree College is registered as a Participating Institution (KTS5-HEI-06100)",
                        "Body", "queued", "2026-11-26T09:00:00+00:00"))
    with app.app_context():
        before = {r["id"]: dict(r) for r in query("SELECT id, head_email, coord_email, coord_mobile FROM institutions")}
        audits = query("SELECT COUNT(*) AS n FROM audit_log", one=True)["n"]
    init_db(app)
    with app.app_context():
        rows = {r["id"]: dict(r) for r in query("SELECT id, status, head_email, coord_email, coord_mobile, decision_note FROM institutions")}
        lines = query("SELECT actor, action, entity_id FROM audit_log ORDER BY id")[audits:]
        mark = json.loads(query("SELECT value FROM settings WHERE key = ?", (MARK,), one=True)["value"])
    assert all(rows[iid]["status"] == "accepted" for iid in ids.values())
    assert all((rows[i]["head_email"], rows[i]["coord_email"], rows[i]["coord_mobile"]) ==
               (before[i]["head_email"], before[i]["coord_email"], before[i]["coord_mobile"]) for i in ids.values())
    assert rows[tirupati]["status"] == "declined" and rows[tirupati]["decision_note"].startswith("Not among the 17 institutions")
    assert rows[later]["status"] == "accepted" and rows[kangan]["status"] == "accepted"
    with app.app_context():
        status = {r["id"]: r["status"] for r in query("SELECT id, status FROM outbox")}
    assert status[theirs] == "queued" and status[ours] == "failed"
    assert [(r["actor"], r["action"], r["entity_id"]) for r in lines] == [("release 1.2.220", "institution_declined", tirupati)]
    assert mark["declined"] == ["KTS5-HEI-06100"] and mark["changed"] == [] and len(mark["listed"]) == 17
    page = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    section = page[page.index('id="st-andhra-pradesh"'):]
    section = section[:section.index("</table>")]
    assert "Krea University" in section and "Government Degree College<" not in section

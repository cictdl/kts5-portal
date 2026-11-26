"""
The list of the Nodal Institution of Puducherry (1.2.220). CICT, 26 November 2026, with the file "Pondicherry University KTS. 5.0
Selected List and mail ID" (5 institutions, with the e-mails of the Head and of the coordinator): "This is the new list Puducherry.
decline others. add the new list details"; the details: "E-mails and mobile".

At the first start of the release, once: the 5 are found by their names among the institutions of Puducherry and take the Head's
e-mail, the coordinator's e-mail and the coordinator's mobile of the list where they differ (the old values in the audit log); the
other institutions of Puducherry registered up to 2:20 PM IST are declined, as those of Jammu and Kashmir and Ladakh in 1.2.218.
If the names do not match one to one, nothing is done.

    python -m pytest tests/test_py_list_1126.py -q
"""
import json

from conftest import make_app
from test_reserve_1111 import _insert

MARK = "migrate.py_list_1126"
BEFORE = "2026-11-20T06:00:00+00:00"
NAMES = ["Perunthalaivar Kamarajar college of Education", "Pondicherry University", "Perunthalaivar Kamarajar Arts College",
         "IDHAYA COLLEGE OF ARTS AND SCIENCE FOR WOMEN", "Rashtriya Raksha University"]
OTHERS = ["Jawaharlal Institute of Postgraduate Medical Education and Research", "Kasturba Gandhi Nursing College",
          "MOTHER THERESA POST GRADUATE AND RESEARCH INSTITUTE OF HEALTH SCIENCS", "National Institute of Technology Puducherry",
          "School of Physiotherapy", "Sri Manakula Vinayagar Engineering College - School of Arts and Science College",
          "Tagore Government Arts and science College", "Vivekanandha College of Education"]


def _row(app, iid):
    from kts.db import query
    with app.app_context():
        return dict(query("SELECT * FROM institutions WHERE id = ?", (iid,), one=True))


def _fresh():
    from kts.db import execute
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key IN (?, 'migrate.ap_list_1126')", (MARK,))      # as on a database of 1.2.219
    return app


def _puducherry(app, more=()):
    ids = {}
    for n, name in enumerate(NAMES + OTHERS + list(more)):
        ids[name] = _insert(app, name, "Puducherry", "Puducherry", "accepted", created=BEFORE, ref=f"KTS5-HEI-07{n:03d}",
                            head_email=f"head{n}@old.example", coord_email=f"coord{n}@old.example", coord_mobile=f"90000000{n:02d}")
    return ids


def _mark(app):
    from kts.db import query
    with app.app_context():
        return json.loads(query("SELECT value FROM settings WHERE key = ?", (MARK,), one=True)["value"])


def test_the_list():
    from kts.db import NODAL_LISTS_1126
    py = next(nodal_list for nodal_list in NODAL_LISTS_1126 if nodal_list["key"] == "py")
    assert py["state"] == "Puducherry" and [r[0] for r in py["listed"]] == NAMES
    assert py["listed"][1] == ("Pondicherry University", "registrar@pondiuni.ac.in", "lakshmi.duttai@pondiuni.ac.in", "9944758909")
    # two rows give a second number in the unlabelled columns: both are kept, and either signs in (1.2.217)
    assert py["listed"][4] == ("Rashtriya Raksha University", "py.campusdirector@rru.ac.in", "tcro7.py@rru.ac.in", "9894881203 / 7550225772")
    assert py["listed"][2][3] == "9159106424 / 9994477028" and py["listed"][0][3] == "9944267630"
    assert py["until"] == "2026-11-26T08:50:00+00:00"
    assert py["note"] == "Not among the 5 institutions of the list of the Nodal Institution of Puducherry (Pondicherry University), 26 November 2026"


def test_the_five_take_the_details_and_the_others_are_declined_once():
    from kts.db import execute, init_db, query
    app = _fresh()
    ids = _puducherry(app)
    kerala = _insert(app, "Kerala College", "Kerala", "Thrissur", "accepted", created=BEFORE, ref="KTS5-HEI-07900")
    with app.app_context():
        # one of the five has the e-mail of the list already, in capitals
        execute("UPDATE institutions SET coord_email = 'BAVANIG80@gmail.com', coord_mobile = '+91 99442 67630 / 9811111111' WHERE id = ?",
                (ids[NAMES[0]],))
        mail = execute("INSERT INTO outbox(to_addr, subject, body, status, created_at, priority) VALUES(?,?,?,?,?,0)",
                       ("x@y.example", "Reminder – KTS 5.0: select your student – School of Physiotherapy", "Body", "queued", "2026-11-26T09:00:00+00:00"))
        audits = query("SELECT COUNT(*) AS n FROM audit_log", one=True)["n"]
        mails = query("SELECT COUNT(*) AS n FROM outbox", one=True)["n"]
    init_db(app)
    first = _row(app, ids[NAMES[0]])
    assert (first["status"], first["head_email"], first["coord_email"], first["coord_mobile"]) == (
        "accepted", "kandedu@gmail.com", "bavanig80@gmail.com", "+91 99442 67630 / 9811111111")      # the e-mail in the list's letters;
    # the field that holds the list's number already is left as it is, both numbers and all
    pu = _row(app, ids["Pondicherry University"])
    assert (pu["status"], pu["head_email"], pu["coord_email"], pu["coord_mobile"]) == (
        "accepted", "registrar@pondiuni.ac.in", "lakshmi.duttai@pondiuni.ac.in", "9944758909")
    for name in OTHERS:
        row = _row(app, ids[name])
        assert row["status"] == "declined" and row["decision_note"].startswith("Not among the 5 institutions of the list of the Nodal"), name
        assert row["coord_email"].endswith("@old.example"), name
    assert _row(app, kerala)["status"] == "accepted"
    with app.app_context():
        lines = query("SELECT actor, action, entity_id, detail FROM audit_log ORDER BY id")[audits:]
        assert query("SELECT COUNT(*) AS n FROM outbox", one=True)["n"] == mails
        assert query("SELECT status FROM outbox WHERE id = ?", (mail,), one=True)["status"] == "failed"
    updated = [json.loads(r["detail"]) for r in lines if r["action"] == "institution_updated"]
    assert len(updated) == 3 * 5 - 1 and all(r["actor"] == "release 1.2.220" for r in lines)
    assert {"ref": "KTS5-HEI-07001", "field": "coord_email", "was": "coord1@old.example", "now": "lakshmi.duttai@pondiuni.ac.in",
            "note": "the details of the list of the Nodal Institution of Puducherry, 26 November 2026"} in updated
    assert sum(1 for r in lines if r["action"] == "institution_declined") == 8
    mark = _mark(app)
    assert mark["listed"] == [f"KTS5-HEI-07{n:03d}" for n in range(5)] and len(mark["declined"]) == 8 and mark["mails_withdrawn"] == 1
    assert ["KTS5-HEI-07000", "head_email"] in mark["changed"] and ["KTS5-HEI-07000", "coord_email"] in mark["changed"]
    assert ["KTS5-HEI-07000", "coord_mobile"] not in mark["changed"]
    # once
    with app.app_context():
        execute("UPDATE institutions SET status = 'accepted' WHERE id = ?", (ids[OTHERS[0]],))
    init_db(app)
    assert _row(app, ids[OTHERS[0]])["status"] == "accepted"
    # the public list: Puducherry shows the five
    page = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    section = page[page.index('id="sel-puducherry"'):]      # the list of the selected institutions (1.2.229)
    section = section[:section.index("</table>")]
    import re
    heading = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", section[:section.index("Nodal Institution")]))
    assert "Puducherry (6)" in heading and all(n in section for n in NAMES) and "School of Physiotherapy" not in section
    assert OTHERS[0] in section          # the one accepted again
    # under the institutions registered: the same six and, shown still, the declined ones that are of the 31 lists of CICT (1.2.229)
    registered = page[page.index('id="st-puducherry"'):page.index('<h2 id="hei-selected"')]
    registered = registered[:registered.index("</table>")]
    assert all(n in registered for n in NAMES) and OTHERS[0] in registered and "School of Physiotherapy" in registered


def test_the_new_coordinator_signs_in_and_the_old_one_does_not():
    from kts.db import init_db, set_setting
    from test_signin_no_code_1126 import _sign_in
    app = _fresh()
    with app.app_context():
        set_setting("inst.code_mail", "0")
    ids = _puducherry(app)
    _c, r = _sign_in(app, "coord1@old.example", "9000000001")
    assert r.status_code == 302
    init_db(app)
    _c, r = _sign_in(app, "coord1@old.example", "9000000001")
    assert r.status_code == 400
    client, r = _sign_in(app, "lakshmi.duttai@pondiuni.ac.in", "9944758909")
    assert r.status_code == 302 and "Pondicherry University" in client.get("/institution").get_data(as_text=True)
    client, r = _sign_in(app, "registrar@pondiuni.ac.in", "9944758909")
    assert r.status_code == 302
    assert ids


def test_nothing_is_done_when_the_names_do_not_match_one_to_one():
    from kts.db import init_db
    app = _fresh()
    ids = _puducherry(app, more=["Pondicherry  University"])      # a second registration under the same name
    init_db(app)
    assert all(_row(app, iid)["status"] == "accepted" for iid in ids.values())
    assert _row(app, ids["Pondicherry University"])["coord_email"] == "coord1@old.example"
    mark = _mark(app)
    assert mark["skipped"].startswith("the list does not match") and len(mark["matches"]["Pondicherry University"]) == 2


def test_a_declined_one_cannot_register_again_under_its_name():
    from kts import heis
    from kts.db import init_db
    app = _fresh()
    data = {"name": "School of Physiotherapy", "state": "Puducherry", "aishe_code": ""}
    with app.app_context():
        key = heis.key_of(data)
    ids = _puducherry(app)
    from kts.db import execute
    with app.app_context():
        execute("UPDATE institutions SET inst_key = ? WHERE id = ?", (key, ids["School of Physiotherapy"]))
    init_db(app)
    with app.test_request_context():
        dup = heis.duplicate(data)
        assert dup is not None and dup["status"] == "declined"


def test_mails_waiting_for_an_old_address_go_to_the_new_one():
    from kts.db import execute, init_db, query
    app = _fresh()
    ids = _puducherry(app)
    with app.app_context():
        mine = execute("INSERT INTO outbox(to_addr, subject, body, status, created_at, priority) VALUES(?,?,?,?,?,0)",
                       ("coord1@old.example", "Reminder – KTS 5.0: select your student – Pondicherry University", "Body", "queued", "2026-11-26T09:00:00+00:00"))
        code = execute("INSERT INTO outbox(to_addr, subject, body, status, created_at, priority) VALUES(?,?,?,?,?,-1)",
                       ("coord1@old.example", "KTS 5.0: your sign-in code", "Body", "queued", "2026-11-26T09:00:00+00:00"))
        other = execute("INSERT INTO outbox(to_addr, subject, body, status, created_at, priority) VALUES(?,?,?,?,?,0)",
                        ("coord1@old.example", "KTS 5.0: something else", "Body", "queued", "2026-11-26T09:00:00+00:00"))
    init_db(app)
    with app.app_context():
        to = {r["id"]: r["to_addr"] for r in query("SELECT id, to_addr FROM outbox")}
    assert to[mine] == "lakshmi.duttai@pondiuni.ac.in" and to[code] == to[other] == "coord1@old.example"
    assert _mark(app)["mails_readdressed"] == 1
    # either number of a row that gives two signs in
    from kts.db import set_setting
    from test_signin_no_code_1126 import _sign_in
    with app.app_context():
        set_setting("inst.code_mail", "0")
    for number in ("9894881203", "7550225772"):
        client, r = _sign_in(app, "tcro7.py@rru.ac.in", number)
        assert r.status_code == 302, number
    assert ids

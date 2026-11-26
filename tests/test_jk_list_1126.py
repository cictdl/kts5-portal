"""
The list of the Nodal Officer of Jammu and Kashmir (1.2.218). CICT, 26 November 2026, with the file "KTS Institutions Selected
Details" (46 institutions: 42 of Jammu and Kashmir, 4 of Ladakh): "Jammu and Kashmir has (67) institutions registered. But the
nodal officer suggests 46. so add new list"; asked what becomes of the 27 registered institutions not on it: "Decline them".

At the first start of the release, once: the institutions of the two UTs registered up to 2:00 PM IST (an invited one: when it
completed its registration) that are not on the list are declined, each with a line of the audit log and no mail; one whose
nomination is submitted already (not withdrawn, not rejected) stays as it is; mails waiting for a declined one are withdrawn; a
declined one cannot register again under its name. The others - on the list, of other States/UTs, invited and never registered,
registered later - stay as they are.

    python -m pytest tests/test_jk_list_1126.py -q
"""
import json

from conftest import make_app
from test_reserve_1111 import _insert

MARK = "migrate.jk_list_1126"
BEFORE = "2026-11-20T06:00:00+00:00"
AFTER = "2026-11-26T09:15:00+00:00"


def _status(app, iid):
    from kts.db import query
    with app.app_context():
        return query("SELECT status, decision_note, decided_at FROM institutions WHERE id = ?", (iid,), one=True)


def _count(app, table):
    from kts.db import query
    with app.app_context():
        return query(f"SELECT COUNT(*) AS n FROM {table}", one=True)["n"]


def _application(app, iid, name, status=None):
    from kts.db import execute, utcnow
    with app.app_context():
        aid = execute("INSERT INTO applications(full_name, gender, dob, mobile, email, state, college_name, college_key, pref_lang, "
                      "created_at, updated_at, institution_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      ("A Student", "F", "2004-05-06", f"98765{iid:05d}", f"student{iid}@tests.example", "Jammu and Kashmir",
                       name, f"name:{name.lower()}|jammu and kashmir", "hi", utcnow(), utcnow(), iid))
        execute("UPDATE institutions SET application_id = ? WHERE id = ?", (aid, iid))
        if status:
            execute("UPDATE applications SET status = ? WHERE id = ?", (status, aid))


def _queue(app, to, subject, priority=0):
    from kts.db import execute, utcnow
    with app.app_context():
        return execute("INSERT INTO outbox(to_addr, subject, body, status, created_at, priority) VALUES(?,?,?,?,?,?)",
                       (to, subject, "Body", "queued", utcnow(), priority))


def test_the_list_of_the_nodal_officer():
    from kts.db import JK_LIST_UNTIL, JK_SELECTED_1126
    assert len(JK_SELECTED_1126) == 46 and all(r.startswith("KTS5-HEI-") and len(r) == 14 for r in JK_SELECTED_1126)
    # some of the list, as the file gives them (first, last, Ladakh)
    assert {"KTS5-HEI-08691", "KTS5-HEI-08521", "KTS5-HEI-00479", "KTS5-HEI-05556", "KTS5-HEI-07058", "KTS5-HEI-07310"} <= JK_SELECTED_1126
    assert JK_LIST_UNTIL == "2026-11-26T08:30:00+00:00"


def test_the_institutions_not_on_the_list_are_declined_once():
    from kts.db import execute, init_db, query
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        assert json.loads(query("SELECT value FROM settings WHERE key = ?", (MARK,), one=True)["value"]) == {
            "declined": [], "kept_nominated": [], "declined_with_students": [], "mails_withdrawn": 0}
        execute("DELETE FROM settings WHERE key = ?", (MARK,))      # as on a database of 1.2.217
    ids = {
        "on the list": _insert(app, "Altaf Memorial Government Degree College Kilam Kulgam", "Jammu and Kashmir", "Kulgam", "accepted",
                               created=BEFORE, ref="KTS5-HEI-08691"),
        "on the list, Ladakh": _insert(app, "Sindhu Central University", "Ladakh", "Leh", "accepted", created=BEFORE, ref="KTS5-HEI-05556"),
        "not on it": _insert(app, "Sri Pratap College", "Jammu and Kashmir", "Srinagar", "accepted", created=BEFORE, ref="KTS5-HEI-07999"),
        "not on it, pending": _insert(app, "GDC Budhal", "Jammu and Kashmir", "Rajouri", "pending", created=BEFORE, ref="KTS5-HEI-08001"),
        "not on it, Ladakh": _insert(app, "Govt Degree College Zanskar", "Ladakh", "Zanskar", "accepted", created=BEFORE, ref="KTS5-HEI-08002"),
        "not on it, nominated": _insert(app, "Cluster University of Jammu", "Jammu and Kashmir", "Jammu", "accepted", created=BEFORE,
                                        ref="KTS5-HEI-08003"),
        "not on it, nomination rejected": _insert(app, "GDC Pouni", "Jammu and Kashmir", "Reasi", "accepted", created=BEFORE,
                                                  ref="KTS5-HEI-08011"),
        "not on it, a student selected": _insert(app, "GDC Vilgam", "Jammu and Kashmir", "Kupwara", "accepted", created=BEFORE,
                                                 ref="KTS5-HEI-08012", winner_id=1),
        "not on it, registered later": _insert(app, "Later College", "Jammu and Kashmir", "Jammu", "accepted", created=AFTER,
                                               ref="KTS5-HEI-09001"),
        "invited, registered before": _insert(app, "GDC Thandapani", "Jammu and Kashmir", "Rajouri", "accepted", created=BEFORE,
                                              ref="KTS5-HEI-08013", invited_by=1, decided_at="2026-11-24T06:00:00+00:00"),
        "invited, registered later": _insert(app, "GDC Tral", "Jammu and Kashmir", "Pulwama", "accepted", created=BEFORE,
                                             ref="KTS5-HEI-08014", invited_by=1, decided_at=AFTER),
        "invited, never registered": _insert(app, "Invited College", "Jammu and Kashmir", "Jammu", "identified", created=BEFORE,
                                             ref="KTS5-HEI-08004"),
        "declined before": _insert(app, "Declined College", "Jammu and Kashmir", "Jammu", "declined", created=BEFORE, ref="KTS5-HEI-08005"),
        "another UT": _insert(app, "Kerala College", "Kerala", "Thrissur", "accepted", created=BEFORE, ref="KTS5-HEI-08006"),
    }
    _application(app, ids["not on it, nominated"], "Cluster University of Jammu")
    _application(app, ids["not on it, nomination rejected"], "GDC Pouni", status="rejected")
    # mails that wait in the queue (sending paused)
    mail = {
        "reminder of a declined one": _queue(app, "coord@x.example", "Reminder – KTS 5.0: select your student by 27 November 2026 – Sri Pratap College"),
        "registration of a declined one": _queue(app, "head@x.example", "KTS 5.0: GDC Budhal is registered as a Participating Institution (KTS5-HEI-08001)"),
        "of one on the list": _queue(app, "coord@y.example", "Reminder – KTS 5.0: select your student – Altaf Memorial Government Degree College Kilam Kulgam"),
        "a sign-in mail": _queue(app, "coord@x.example", "KTS 5.0: your sign-in code", priority=-1),
        "another": _queue(app, "someone@z.example", "KTS 5.0 application received: KTS5-2026-000123"),
    }
    mails, audits = _count(app, "outbox"), _count(app, "audit_log")
    init_db(app)
    status = {name: _status(app, iid)["status"] for name, iid in ids.items()}
    assert status == {"on the list": "accepted", "on the list, Ladakh": "accepted", "not on it": "declined",
                      "not on it, pending": "declined", "not on it, Ladakh": "declined", "not on it, nominated": "accepted",
                      "not on it, nomination rejected": "declined", "not on it, a student selected": "declined",
                      "not on it, registered later": "accepted", "invited, registered before": "declined",
                      "invited, registered later": "accepted", "invited, never registered": "identified",
                      "declined before": "declined", "another UT": "accepted"}
    row = _status(app, ids["not on it"])
    assert row["decision_note"].startswith("Not among the 46 institutions of the list of the Nodal Institution of Jammu and Kashmir")
    assert row["decided_at"]
    assert _count(app, "outbox") == mails                       # no mail is added
    with app.app_context():
        lines = query("SELECT actor, action, entity, entity_id, detail FROM audit_log ORDER BY id")[audits:]
        mark = json.loads(query("SELECT value FROM settings WHERE key = ?", (MARK,), one=True)["value"])
        outbox = {r["id"]: (r["status"], r["error"]) for r in query("SELECT id, status, error FROM outbox")}
    declined = ("not on it", "not on it, pending", "not on it, Ladakh", "not on it, nomination rejected", "not on it, a student selected",
                "invited, registered before")
    assert [(r["actor"], r["action"], r["entity_id"]) for r in lines] == [("release 1.2.218", "institution_declined", ids[n]) for n in declined]
    assert json.loads(lines[1]["detail"])["was"] == "pending"
    assert mark == {"declined": ["KTS5-HEI-07999", "KTS5-HEI-08001", "KTS5-HEI-08002", "KTS5-HEI-08011", "KTS5-HEI-08012", "KTS5-HEI-08013"],
                    "kept_nominated": ["KTS5-HEI-08003"], "declined_with_students": ["KTS5-HEI-08012"], "mails_withdrawn": 2}
    withdrawn = ("failed", "withdrawn: the institution is declined (1.2.218)")
    assert outbox[mail["reminder of a declined one"]] == withdrawn and outbox[mail["registration of a declined one"]] == withdrawn
    assert outbox[mail["of one on the list"]][0] == outbox[mail["a sign-in mail"]][0] == outbox[mail["another"]][0] == "queued"
    # once: a second start changes nothing, and CICT may accept one again
    with app.app_context():
        execute("UPDATE institutions SET status = 'accepted' WHERE id = ?", (ids["not on it"],))
    init_db(app)
    assert _status(app, ids["not on it"])["status"] == "accepted" and _count(app, "audit_log") == audits + len(declined)
    # the public list of the institutions: the declined ones are gone
    page = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    jk = page[page.index('id="st-jammu-and-kashmir"'):]
    assert "Altaf Memorial Government Degree College Kilam Kulgam" in jk and "GDC Budhal" not in jk and "Govt Degree College Zanskar" not in page


def test_a_declined_institution_cannot_register_again_under_its_name():
    from kts import heis
    from kts.db import execute, init_db
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key = ?", (MARK,))
    data = {"name": "Sri Pratap College", "state": "Jammu and Kashmir", "aishe_code": ""}
    with app.app_context():
        key = heis.key_of(data)
    iid = _insert(app, "Sri Pratap College", "Jammu and Kashmir", "Srinagar", "accepted", created=BEFORE, ref="KTS5-HEI-07999", inst_key=key)
    other = _insert(app, "Some College", "Kerala", "Thrissur", "declined", created=BEFORE, ref="KTS5-HEI-07998",
                    inst_key="name:some college|kerala")
    init_db(app)
    with app.test_request_context():
        dup = heis.duplicate(data)
        assert dup is not None and dup["id"] == iid and dup["status"] == "declined"
        # an institution declined for another reason may register again, as before
        assert heis.duplicate({"name": "Some College", "state": "Kerala", "aishe_code": ""}) is None
        # the Console edit of the declined one itself is not held back by it
        assert heis.duplicate(data, exclude_id=iid) is None
    assert other


def test_a_declined_institution_can_no_longer_sign_in():
    from kts.db import execute, init_db, set_setting
    from test_signin_no_code_1126 import _sign_in
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM settings WHERE key = ?", (MARK,))
        set_setting("inst.code_mail", "0")
    _insert(app, "GDC Tral", "Jammu and Kashmir", "Pulwama", "accepted", created=BEFORE, ref="KTS5-HEI-08010",
            coord_email="coord@tral.example", coord_mobile="9000000077")
    client, r = _sign_in(app, "coord@tral.example", "9000000077")
    assert r.status_code == 302 and client.get("/institution").status_code == 200
    init_db(app)
    assert client.get("/institution").status_code == 302          # the session ends with the decline
    _c, r = _sign_in(app, "coord@tral.example", "9000000077")
    assert r.status_code == 400

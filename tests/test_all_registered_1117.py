"""
Every institution that registers is a Participating Institution (1.2.201). CICT, 17 November 2026, of the Evaluation Committee:
"The committee will only select the student. so every institute is registered not selected"; asked what changes for the
institutions: "All registered take part"; of those that are pending: "Yes, mail them"; of the marks of the institutions in the
Console: "Hide them".

* A switch of Settings, hei.select_step, off: no selection of institutions. An institution that registers, or completes its
  registration from an invitation, is a Participating Institution at once and receives the mail of one; the Nodal Officers of its
  State/UT are told of it. The tests made before run with the selection on (tests/conftest.py).
* The institutions that awaited the selection become Participating Institutions, once for each database, and each is told by
  mail, once, at the start of the portal; not after the last day of the nomination.
* Console > Institutions without the selection: no Select, no marks of Annexure-V, "Registered" for "Selected".
* Five texts of the registration in the 23 languages.

    python -m pytest tests/test_all_registered_1117.py -q
"""
import json
import re

import pytest

from conftest import ROOT, make_app
from test_campus import _coordinator, _mails
from test_institutions import _apply
from test_no_reserve_1117 import _app as _app_1198, _count, _newest, _value
from test_nodal_access import _nodal
from test_reserve_1111 import LANGS, _act, _insert, _status

KEYS = ("hei.reg_intro", "hei.any_number", "hei.done_title", "hei.done_next", "hs.c2")
MARK, MAIL = "migrate.pending_registered_1117", "mail.pending_registered_1117"
LEAD = ("Dear Sir/Madam,\n\nYour institution is registered as a Participating Institution of Kashi Tamil Sangamam 5.0 – Thirukkural "
        "Payilvom.\n\nReference: KTS5-HEI-")
SUBJECT = "KTS 5.0: {} is registered as a Participating Institution"
WAS = (("Waiting One College", "Puducherry", "pending", {"head_email": "head@one.example", "coord_email": "coord@one.example"}),
       ("Waiting Two College", "Kerala", "pending", {"coord_email": "coord@two.example"}),
       ("Invited Unfinished College", "Puducherry", "pending", {"head_name": "", "invited_by": 1, "coord_email": "coord@unfinished.example"}),
       ("Selected College", "Puducherry", "accepted", {"head_email": "head@selected.example"}),
       ("Declined College", "Puducherry", "declined", {"head_email": "head@declined.example"}),
       ("Listed College", "Puducherry", "identified", {"head_name": "", "invited_by": 1, "coord_email": "coord@listed.example"}))
MOVED = ("Waiting One College", "Waiting Two College")


@pytest.fixture(autouse=True)
def empty_limiter():
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def _app(**settings):
    """The portal as the release leaves it: no selection of institutions, no reserve list, the list of the institutions public."""
    return _app_1198(**{"hei.select_step": "0", "hei.public": "1", **settings})


def _signs_up(app, name, **more):
    """An institution registers on the website; gives (the client, the answer)."""
    slug = re.sub(r"[^a-z]", "", name.lower())
    client = app.test_client()
    form = {"name": name, "state": "Puducherry", "district": "Karaikal", "aishe_code": "", "head_email": f"head@{slug}.example",
            "coord_email": f"coord@{slug}.example", **more}
    return client, _apply(client, **form)


def _row(app, name):
    from kts.db import query
    with app.app_context():
        return query("SELECT * FROM institutions WHERE name = ?", (name,), one=True)


def _console(officer, state="Puducherry"):
    return officer.get(f"/console/institutions?state={state}").get_data(as_text=True)


def _before(app):
    """The database of the live site as the release finds it: institutions that await the selection, and no mark of the release."""
    from kts.db import execute
    ids = {name: _insert(app, name, state, "District", status, None, **more) for name, state, status, more in WAS}
    with app.app_context():
        execute("DELETE FROM settings WHERE key IN (?, ?)", (MARK, MAIL))
    return ids


def test_the_switch_of_settings():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS["hei.select_step"] == "0"
    rows = {k: (label, kind) for _group, items in SETTING_GROUPS for k, label, kind in items}
    assert rows["hei.select_step"] == (
        "The Nodal Institutions select the Participating Institutions from those registered: the buttons “✓ Select” and “Marks”, "
        "the column “Pending” and the evaluation sheet of Console › Institutions (off since 18 November 2026: every institution "
        "that registers is a Participating Institution at once)", "bool")


def test_an_institution_that_registers_is_a_participating_institution_at_once():
    app = _app()
    _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    mails = _count(app, "outbox")
    client, r = _signs_up(app, "Alpha College")
    assert r.status_code == 302 and "/institutions/register/done/KTS5-HEI-" in r.headers["Location"]
    row = _row(app, "Alpha College")
    assert row["status"] == "accepted" and row["decided_at"] and row["decided_by"] is None
    # the page that follows says so
    done = client.get(r.headers["Location"] + "?lang=en").get_data(as_text=True)
    assert "<h1>Institution registered</h1>" in done and "Your institution is registered as a Participating Institution of Puducherry." in done
    assert "reviews the application" not in done and "with the decision" not in done
    # the mail of a Participating Institution, to the Head and the Coordinator; the Nodal Officer is told
    sent = _newest(app, "outbox", mails)
    heading = SUBJECT.format("Alpha College") + f" ({row['ref']})"
    assert [(m["to_addr"], m["subject"]) for m in sent] == [
        ("head@alphacollege.example", heading), ("coord@alphacollege.example", heading),
        ("nodal.py@tests.example", "KTS 5.0: Alpha College has registered (Puducherry)")]
    body = sent[0]["body"]
    assert body.startswith(LEAD) and "Please assess your interested students on the Thirukkural by " in body
    assert "/institution/login" in body and "/how-to-submit-the-student" in body and "does not by itself confer selection" not in body
    assert "has registered as a Participating Institution of KTS 5.0." in sent[2]["body"] and "/console/institutions" in sent[2]["body"]
    assert "record the marks" not in sent[2]["body"] and "Scrutinise" not in sent[2]["body"]
    # the list of the website holds it at once, and its Coordinator signs in to the page of a Participating Institution
    assert "Alpha College" in app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    coord, token = _coordinator(app, row)
    home = coord.get("/institution?lang=en").get_data(as_text=True)
    assert '<span class="pill green">participating institution</span>' in home and "awaiting the Nodal Officer" not in home
    page = coord.post("/institution/winner", data={"_csrf": token, "action": "enter", "name": "Arun Student", "email": "arun@student.example",
                                                    "mobile": "9123456781", "roll_no": "21ENG003", "course": "B.Sc Physics", "lang": "en"},
                      follow_redirects=True).get_data(as_text=True)
    assert "Arun Student is selected and informed by e-mail" in page and ">Submit the nomination</a>" in page


def test_an_invited_institution_that_completes_its_registration_too():
    app = _app()
    _insert(app, "Invited College", "Puducherry", "Karaikal", "identified", None, head_name="", invited_by=1, invite_token="invitation-of-the-test",
            coord_email="coord@invitedcollege.example")
    mails = _count(app, "outbox")
    client, r = _signs_up(app, "Invited College", invite="invitation-of-the-test")
    assert r.status_code == 302
    row = _row(app, "Invited College")
    assert row["status"] == "accepted" and row["decided_at"] and row["invite_token"] is None and row["head_name"]
    sent = _newest(app, "outbox", mails)
    assert sent[0]["subject"] == SUBJECT.format("Invited College") + f" ({row['ref']})" and sent[0]["body"].startswith(LEAD)
    assert "<h1>Institution registered</h1>" in client.get(r.headers["Location"] + "?lang=en").get_data(as_text=True)


def test_the_console_without_the_selection():
    app = _app()
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    _signs_up(app, "Alpha College")
    alpha = _row(app, "Alpha College")["id"]
    page = _console(officer)
    head = page[page.index("<thead>"):page.index("</thead>")]
    assert re.findall(r"<th[^>]*>([^<]+)</th>", head) == [
        "State/UT", "Annexure-I", "Identified, not registered", "Registered", "Assessing online", "Student selected", "Student registered",
        "Declined"]
    row = page[page.index("<tbody>"):page.index("</tbody>")]
    cells = re.sub(r"<[^>]+>", " ", row[:row.index("</tr>")]).split()
    assert len(re.findall(r"<td\b", row[:row.index("</tr>")])) == 8 and cells[1:4] == ["5", "0", "1"]   # Annexure-I, identified, registered
    assert "every institution that registers is a Participating Institution at once\n  (CICT, 17 November 2026): there is no selection of institutions, no reserve list and no ceiling." in page
    assert "the Nodal Institution scrutinises them" not in page and "selects the number" not in page
    # an institution: registered; it may be declined; no Select, no marks
    assert '<span class="pill green">registered</span>' in page and '<span class="pill green">selected</span>' not in page
    for gone in ("✓ Select", ">Marks</a>", "Record the marks", "Evaluation sheet (Annexure-V)", "By the marks of Annexure-V", "not marked yet",
                 "Selected without marks", 'value="pending"', "Status · marks"):
        assert gone not in page, gone
    assert "<th>Status</th>" in page and 'value="decline"' in page and ">Excel (Annexure-II)</a>" in page
    status = page[page.index('id="status_f"'):]
    assert re.findall(r"<option([^>]*)>([^<]+)</option>", status[:status.index("</select>")]) == [
        (' value=""', "Any"), (" ", "identified"), (' value="accepted" ', "registered"), (" ", "declined")]
    assert "Alpha College" in officer.get("/console/institutions?state=Puducherry&status=accepted").get_data(as_text=True)
    # nothing is returned to pending
    assert _act(officer, alpha, "pending").status_code == 400 and _status(app, alpha) == "accepted"
    # a decline, and its undoing into a registered institution: each told by mail
    mails = _count(app, "outbox")
    assert "Alpha College: declined" in _act(officer, alpha, "decline").get_data(as_text=True) and _status(app, alpha) == "declined"
    page = _console(officer)
    assert 'value="accept">Undo the decline</button>' in page
    answer = _act(officer, alpha, "accept").get_data(as_text=True)
    assert "Alpha College: registered – the Head of the Institution and the coordinator are informed by mail." in answer
    assert _status(app, alpha) == "accepted"
    last = _newest(app, "outbox", mails)[-1]
    assert last["subject"] == SUBJECT.format("Alpha College") and last["body"].startswith(LEAD)


def test_an_institution_left_pending_and_the_marks_first():
    # one that its Nodal Institution invited and that has not completed its registration stays pending, and is shown; the rule of
    # the marks first (hei.marks_first) stands in no one's way where there is no selection
    app = _app(**{"hei.marks_first": "1"})
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    stray = _insert(app, "Unfinished College", "Puducherry", "Karaikal", "pending", None, head_name="", invited_by=1)
    waiting = _insert(app, "Waiting College", "Puducherry", "Karaikal", "pending", None, head_email="head@waiting.example")
    page = _console(officer)
    assert '<th class="num">Pending</th><th class="num">Registered</th>' in page and ">pending</option>" in page
    assert 'value="accept">✓ Register</button>' in page
    answer = _act(officer, stray, "accept").get_data(as_text=True)
    assert ("Unfinished College has not completed its registration yet: it is a Participating Institution once it has registered with its "
            "invitation (↩ Back to invited mails the link once more).") in answer and _status(app, stray) == "pending"
    assert "Waiting College: registered" in _act(officer, waiting, "accept").get_data(as_text=True) and _status(app, waiting) == "accepted"


def test_switched_on_the_selection_is_as_it_was():
    app = _app(**{"hei.select_step": "1"})
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    mails = _count(app, "outbox")
    client, r = _signs_up(app, "Alpha College")
    row = _row(app, "Alpha College")
    assert row["status"] == "pending" and row["decided_at"] is None
    sent = _newest(app, "outbox", mails)
    assert sent[0]["subject"] == f"KTS 5.0: application of Alpha College received ({row['ref']})"
    assert sent[-1]["subject"] == "KTS 5.0: Alpha College applies to participate (Puducherry)"
    page = _console(officer)
    assert '<th class="num">Pending</th><th class="num">Selected</th>' in page and 'value="accept">✓ Select</button>' in page
    assert ">Marks</a>" in page and "Evaluation sheet (Annexure-V)" in page and "<th>Status · marks (Annexure-V)</th>" in page
    assert "the Nodal Institution scrutinises them" in page and "every institution that registers is a Participating Institution at once" not in page
    assert "Alpha College: accepted" in _act(officer, row["id"], "accept").get_data(as_text=True)
    assert _newest(app, "outbox", mails)[-1]["subject"] == "KTS 5.0: Alpha College is a Participating Institution"
    assert '<span class="pill green">selected</span>' in _console(officer)


def test_the_institutions_that_awaited_the_selection_become_participating_institutions_once():
    from kts.db import init_db, query
    app = _app()
    assert _value(app, MARK) == "0" and _value(app, MAIL) == "[]"       # a database that starts with this release
    ids = _before(app)
    mails, audits = _count(app, "outbox"), _count(app, "audit_log")
    init_db(app)
    with app.app_context():
        status = {r["name"]: (r["status"], bool(r["decided_at"])) for r in query("SELECT name, status, decided_at FROM institutions")}
    assert status == {"Waiting One College": ("accepted", True), "Waiting Two College": ("accepted", True),
                      "Invited Unfinished College": ("pending", False), "Selected College": ("accepted", False),
                      "Declined College": ("declined", False), "Listed College": ("identified", False)}
    lines = _newest(app, "audit_log", audits)
    assert [(r["actor"], r["action"], r["entity"], r["entity_id"]) for r in lines] == [
        ("release 1.2.201", "institution_accepted", "institution", ids[name]) for name in MOVED]
    assert json.loads(lines[0]["detail"])["was"] == "pending"
    assert _value(app, MARK) == "2" and json.loads(_value(app, MAIL)) == [ids[name] for name in MOVED]
    assert _count(app, "outbox") == mails          # the start of the portal sends the mails
    # once: one that awaits a selection later, where Settings switch the selection on again, stays as it is
    later = _insert(app, "Later College", "Puducherry", "District", "pending", None)
    init_db(app)
    assert _status(app, later) == "pending" and _value(app, MARK) == "2"


def test_they_are_told_by_mail_once():
    from kts import heis as HEI
    from kts.db import init_db
    app = _app()
    _before(app)
    init_db(app)
    mails = _count(app, "outbox")
    with app.app_context():
        assert HEI.mail_pending_registered() == 2
    sent = _newest(app, "outbox", mails)
    assert [(m["to_addr"], m["subject"]) for m in sent] == [
        ("head@one.example", SUBJECT.format("Waiting One College")), ("coord@one.example", SUBJECT.format("Waiting One College")),
        ("coord@two.example", SUBJECT.format("Waiting Two College"))]
    body = sent[0]["body"]
    assert body.startswith(LEAD) and "Please assess your interested students on the Thirukkural by " in body
    assert "and nominate one student on merit, with one Faculty Supervisor/Guide, by " in body and "/institution/login" in body
    assert body.endswith("/institutions\n\nCentral Institute of Classical Tamil, Chennai")
    assert _value(app, MAIL) == "mailed 2 institutions"
    with app.app_context():
        assert HEI.mail_pending_registered() == 0
    init_db(app)
    with app.app_context():
        assert HEI.mail_pending_registered() == 0
    assert _count(app, "outbox") == mails + 3


def test_the_start_of_the_portal_sends_the_mails():
    app = _app()
    _before(app)
    mails = _count(app, "outbox")
    again = make_app(DATABASE=app.config["DATABASE"], INSTANCE_DIR=app.config["INSTANCE_DIR"], UPLOAD_DIR=app.config["UPLOAD_DIR"],
                     ADMIN_PASSWORD=None)
    sent = _newest(again, "outbox", mails)
    assert len(sent) == 3 and {m["subject"] for m in sent} == {SUBJECT.format(name) for name in MOVED}
    assert _value(again, MAIL) == "mailed 2 institutions" and _value(again, MARK) == "2"


def test_no_mail_after_the_last_day_of_the_nomination_and_once_for_two_starts(monkeypatch):
    from kts import heis as HEI
    from kts.db import execute, init_db, set_setting
    app = _app()
    ids = _before(app)
    init_db(app)
    mails = _count(app, "outbox")
    real = HEI.now_ist

    def the_other_start_first():
        execute("UPDATE settings SET value = 'mailing 2 institutions' WHERE key = ?", (MAIL,))
        return real()

    monkeypatch.setattr(HEI, "now_ist", the_other_start_first)
    with app.app_context():
        assert HEI.mail_pending_registered() == 0
    assert _count(app, "outbox") == mails and _value(app, MAIL) == "mailing 2 institutions"
    monkeypatch.setattr(HEI, "now_ist", real)
    with app.app_context():
        execute("UPDATE settings SET value = ? WHERE key = ?", (json.dumps([ids[name] for name in MOVED]), MAIL))
        set_setting("reg.end", "2020-01-01")
        assert HEI.mail_pending_registered() == 0
    assert _count(app, "outbox") == mails and _value(app, MAIL) == "not mailed: after the last day of the nomination"


def test_the_mails_to_the_nodal_officers():
    from kts import nodal
    from kts.db import query, set_setting
    from test_nodal_signin import _account
    app = _app()
    uid = _account(app, "new.kerala@tests.example", ["Kerala"])
    with app.app_context():
        text = nodal.account_paragraph(["Kerala"])
        assert text.startswith("As Nodal Officer for Kerala and Lakshadweep, you see the institutions of your State/UT that register on the "
                               "portal, each of them a Participating Institution: Console > Institutions. Then you see the applications")
        assert "scrutinise" not in text and "select the number" not in text
        _subject, body = nodal.signin_mail(query("SELECT * FROM users WHERE id = ?", (uid,), one=True))
        assert "• Every institution that registers is a Participating Institution; the Console lists them (Institutions)." in body
        assert "• Each Participating Institution nominates one student" in body and "The Nodal Institution selects the" not in body
        set_setting("hei.select_step", "1")
        assert "and select the number of Participating Institutions that Annexure-I prescribes" in nodal.account_paragraph(["Kerala"])
        _subject, body = nodal.signin_mail(query("SELECT * FROM users WHERE id = ?", (uid,), one=True))
        assert "• The Nodal Institution selects the 21 Participating Institutions that Annexure-I prescribes" in body
        assert "• Each selected institution nominates one student" in body


def test_the_texts_in_23_languages():
    from kts.i18n import CATALOG
    en = CATALOG["en"]
    assert len(en) == 1557      # 1.2.231: the four texts of the shorts; 1.2.209: 26 texts without the last days (<key>_nd); 1.2.229: the two headings of /institutions
    assert en["hei.any_number"] == "Any number of institutions of a State/UT may register. Every institution that registers is a Participating Institution."
    assert en["hei.done_title"] == "Institution registered"
    assert en["hei.done_next"] == ("Your institution is registered as a Participating Institution of {state}. The Head of the Institution and "
                                   "the coordinator receive an email now, with the steps: assess your interested students and nominate one "
                                   "on merit.")
    assert "registration does not by itself confer selection" not in en["hei.reg_intro"] and "selects" not in en["hei.reg_intro"]
    assert en["hs.c2"].endswith("The assessment and the nomination are open to every registered Participating Institution.")
    assert sorted(CATALOG) == sorted(LANGS)
    for code in LANGS:
        c = CATALOG[code]
        for key in KEYS:
            text = c[key]
            assert text.strip() == text and "\n" not in text and "  " not in text, (code, key)
            assert sorted(re.findall(r"\{[^}]*\}", text)) == sorted(re.findall(r"\{[^}]*\}", en[key])), (code, key)
            assert code == "en" or text != en[key], (code, key)
        assert c["hei.any_number"].startswith(c["hei.no_limit"]) and c["hei.any_number"] != c["hei.no_limit"], code
    # the pages of the registration in English
    app = _app(**{"join.on": "1"})
    client = app.test_client()
    page = client.get("/institutions/register?lang=en").get_data(as_text=True)
    assert "Every institution that registers is a Participating Institution.</b>" in page
    assert "does not by itself confer selection" not in page and "selects the number" not in page
    page = client.get("/how-to-submit-the-student?lang=en").get_data(as_text=True)
    assert "The assessment and the nomination are open to every registered Participating Institution." in page

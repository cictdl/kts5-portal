"""
The reserve list is no more (1.2.198). CICT, 17 November 2026: "remove the reserve list condition" and "in console reserve column
should be removed"; asked what the institutions on it become: "Selected, like the 551"; and, while the release was made: "for
the reserve list send an email".

* Console > Institutions offers no reserve list: no column "Reserve", no button "Reserve list", no status "reserve" in the filter,
  and the action is refused. A switch of Settings (hei.reserve_list, off) brings it back as it was; the tests made before run
  with it on (tests/conftest.py).
* The institutions that were on the reserve list become selected, once for each database, with a line of the audit log each;
  each is told by mail, once, when the portal starts, and not after the last day of the nomination.
* The public pages and the mails to the Nodal Officers say nothing of a reserve list, in the 23 languages.

    python -m pytest tests/test_no_reserve_1117.py -q
"""
import json
import re

import pytest

from conftest import ROOT, make_app
from test_nodal_access import _nodal
from test_reserve_1111 import LANGS, _act, _app as _app_1111, _insert, _mark, _register, _status

KEYS = ("nodal.p1", "hei.reg_intro", "hei.any_number", "guide.n2", "timeline.hei_select", "dash.marks_note", "hub.n_sel", "join.over",
        "ng.g5", "ng.rank", "ng.records", "hs.n2", "ng.replace")
MARK = "migrate.reserve_off_1117"
MAIL = "migrate.reserve_off_1117.mail"
WAS = (("Marked Reserve College", "Puducherry", "reserve", 70, {"head_email": "head@marked.example", "coord_email": "coord@marked.example"}),
       ("Unmarked Reserve College", "Puducherry", "reserve", None, {"head_email": "one@unmarked.example", "coord_email": "one@unmarked.example"}),
       ("Kerala Reserve College", "Kerala", "reserve", 65, {"coord_email": "coord@kerala.example"}),
       ("Selected College", "Puducherry", "accepted", 80, {"head_email": "head@selected.example"}),
       ("Pending College", "Puducherry", "pending", 60, {"head_email": "head@pending.example"}),
       ("Declined College", "Puducherry", "declined", 40, {"head_email": "head@declined.example"}))
MOVED = ("Marked Reserve College", "Unmarked Reserve College", "Kerala Reserve College")


@pytest.fixture(autouse=True)
def empty_limiter():
    """The registrations here count against the limit of an address per hour; the other tests' count stays as it was."""
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def _app(**settings):
    """The portal as the release leaves it: no reserve list, the marks at a later stage (1.2.175)."""
    from kts.db import set_setting
    app = _app_1111()
    with app.app_context():
        for key, value in {"hei.reserve_list": "0", "hei.marks_first": "0", **settings}.items():
            set_setting(key, value)
    return app


def _console(officer, state="Puducherry"):
    return officer.get(f"/console/institutions?state={state}").get_data(as_text=True)


def _before(app):
    """The database of the live site as the release finds it: institutions on the reserve list, and no mark of the release."""
    from kts.db import execute
    ids = {name: _insert(app, name, state, "District", status, total, **more) for name, state, status, total, more in WAS}
    with app.app_context():
        execute("DELETE FROM settings WHERE key IN (?, ?)", (MARK, MAIL))
    return ids


def _value(app, key):
    from kts.db import query
    with app.app_context():
        return query("SELECT value FROM settings WHERE key = ?", (key,), one=True)["value"]


def _count(app, table):
    from kts.db import query
    with app.app_context():
        return query(f"SELECT COUNT(*) AS n FROM {table}", one=True)["n"]


def _newest(app, table, since):
    """The rows of the table written after it held `since` rows, the oldest first."""
    from kts.db import query
    with app.app_context():
        return query(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (_count(app, table) - since,))[::-1]


def test_the_switch_of_settings():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS["hei.reserve_list"] == "0"
    rows = {k: (label, kind) for _group, items in SETTING_GROUPS for k, label, kind in items}
    assert rows["hei.reserve_list"] == (
        "The Nodal Institutions keep a reserve list of institutions: the button “Reserve list” and the column “Reserve” of "
        "Console › Institutions (off since 17 November 2026: there is no reserve list, and the institutions that were on it are "
        "selected)", "bool")
    group = [g for g, items in SETTING_GROUPS if any(k == "hei.reserve_list" for k, _l, _k in items)]
    assert group == ["Participating institutions (Console › Institutions; the website: /institutions)"]


def test_the_console_offers_no_reserve_list():
    app = _app()
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    alpha = _register(app, "Alpha College")
    page = _console(officer)
    # the table of the States/UTs: nine columns, none of a reserve list
    head = page[page.index("<thead>"):page.index("</thead>")]
    assert re.findall(r"<th[^>]*>([^<]+)</th>", head) == [
        "State/UT", "Annexure-I", "Identified, not registered", "Pending", "Selected", "Assessing online", "Student selected",
        "Student registered", "Declined"]
    row = page[page.index("<tbody>"):page.index("</tbody>")]
    assert len(re.findall(r"<td\b", row[:row.index("</tr>")])) == 9
    # the buttons of an institution, and the filter
    assert 'value="accept"' in page and 'value="decline"' in page and 'value="reserve"' not in page and "Reserve list</button>" not in page
    status = page[page.index('id="status_f"'):]
    assert re.findall(r"<option[^>]*>([^<]+)</option>", status[:status.index("</select>")]) == ["Any", "identified", "pending", "accepted", "declined"]
    # the words: no reserve list, and what became of it
    assert "There is no reserve list any more (CICT, 17 November 2026): the institutions that\n  were on it are selected." in page
    for gone in ("form the reserve list", "Reserve list</b>", "replaced from the reserve list", "put on the reserve list"):
        assert gone not in page, gone
    assert "(the marks may\n  be recorded at a later stage, CICT, 12 November 2026). There is no reserve list any more" in page
    # the action is refused, nothing changes and nobody is told
    mails = _count(app, "outbox")
    assert _act(officer, alpha, "reserve").status_code == 400 and _status(app, alpha) == "pending"
    assert _count(app, "outbox") == mails
    # the page of the marks
    marks = officer.get(f"/console/institutions/{alpha}/marks").get_data(as_text=True)
    assert "reserve list" not in marks.lower() and "Institutions for Puducherry. The marks may be recorded at a later stage.</p>" in marks
    # an institution is selected as before, and told
    assert "Alpha College: accepted" in _act(officer, alpha, "accept").get_data(as_text=True) and _status(app, alpha) == "accepted"
    assert "is a Participating Institution" in _newest(app, "outbox", mails)[-1]["subject"]


def test_the_marks_first_without_a_reserve_list():
    app = _app(**{"hei.marks_first": "1"})
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    alpha = _register(app, "Alpha College")
    page = _console(officer)
    assert ": an institution is selected once its marks are recorded. There is no reserve list any more" in page
    assert '<span class="small muted">Select follows the marks</span>' in page and 'value="accept"' not in page
    answer = _act(officer, alpha, "accept").get_data(as_text=True)
    assert ("Alpha College: record the marks of the Evaluation Committee first (Marks, Annexure-V). An institution is selected on its "
            "marks.") in answer
    marks = officer.get(f"/console/institutions/{alpha}/marks").get_data(as_text=True)
    assert "reserve list" not in marks.lower()
    assert "its marks are recorded here, with <b>Select</b> in the list of the institutions.</p>" in marks
    assert _mark(officer, alpha, (20, 15, 15, 10, 10, 5)).status_code == 302
    page = _console(officer)
    assert 'value="accept"' in page and 'value="reserve"' not in page


def test_the_number_of_annexure_i_without_a_reserve_list():
    # where CICT keeps the ceiling of Annexure-I (off since 1.2.178), the answer no longer points to a reserve list
    app = _app(**{"hei.cap_annexure": "1", "hei.end": "2020-01-01"})
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    for n in range(5):
        _insert(app, f"Selected College {n}", "Puducherry", "Karaikal", "accepted", 80)
    sixth = _insert(app, "Sixth College", "Puducherry", "Karaikal", "pending", 70)
    answer = _act(officer, sixth, "accept").get_data(as_text=True)
    assert "Puducherry has 5 accepted institutions: that is the number Annexure-I prescribes for it" in answer
    assert "may be placed on the reserve list" not in answer and _status(app, sixth) == "pending"


def test_switched_on_the_reserve_list_comes_back():
    app = _app(**{"hei.reserve_list": "1"})
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    alpha = _register(app, "Alpha College")
    page = _console(officer)
    assert '<th class="num">Selected</th><th class="num">Reserve</th>' in page and 'value="reserve">Reserve list</button>' in page
    assert "place each of them on it with the button <b>Reserve list</b>" in page and "There is no reserve list" not in page
    mails = _count(app, "outbox")
    assert "Alpha College: reserve" in _act(officer, alpha, "reserve").get_data(as_text=True) and _status(app, alpha) == "reserve"
    assert "is in the reserve list" in _newest(app, "outbox", mails)[-1]["subject"]
    assert '<span class="pill saffron">reserve list</span>' in _console(officer)


def test_the_institutions_of_the_reserve_list_become_selected_once():
    from kts.db import init_db, query
    app = _app()
    # a database that starts with this release has nothing to do, and says so
    assert _value(app, MARK) == "0" and _value(app, MAIL) == "[]"
    ids = _before(app)
    mails, audits = _count(app, "outbox"), _count(app, "audit_log")
    init_db(app)
    with app.app_context():
        status = {r["name"]: r["status"] for r in query("SELECT name, status FROM institutions")}
        assert status == {"Marked Reserve College": "accepted", "Unmarked Reserve College": "accepted", "Kerala Reserve College": "accepted",
                          "Selected College": "accepted", "Pending College": "pending", "Declined College": "declined"}
        # their marks and the rest of them stay
        assert query("SELECT sop_total FROM institutions WHERE id = ?", (ids["Marked Reserve College"],), one=True)["sop_total"] == 70
    # each has its line in the audit log; the marks hold their number, and them for the mail
    lines = _newest(app, "audit_log", audits)
    assert [(r["actor"], r["action"], r["entity"], r["entity_id"]) for r in lines] == [
        ("release 1.2.198", "institution_accepted", "institution", ids[name]) for name in MOVED]
    detail = json.loads(lines[0]["detail"])
    assert detail["was"] == "reserve" and detail["ref"].startswith("KTS5-HEI-")
    assert _value(app, MARK) == "3" and json.loads(_value(app, MAIL)) == [ids[name] for name in MOVED]
    assert _count(app, "outbox") == mails        # the database is made ready without a mail; the start of the portal sends them
    # the Console counts them with the selected, and they are selected like the others
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    page = _console(officer)
    summary = page[page.index("<tbody>"):page.index("</tbody>")]
    row = summary[summary.index("Puducherry"):]
    assert re.sub(r"<[^>]+>", " ", row[:row.index("</tr>")]).split()[1:5] == ["5", "0", "1", "3"]   # Annexure-I, identified, pending, selected
    assert page.count('<span class="pill green">selected</span>') == 3 and "reserve list" not in page.replace("There is no reserve list any more", "")
    # once only: an institution put on a reserve list later, where Settings switch it on again, stays on it
    later = _insert(app, "Later Reserve College", "Puducherry", "District", "reserve", 50, head_email="head@later.example")
    init_db(app)
    assert _status(app, later) == "reserve" and _value(app, MARK) == "3"


def test_they_are_told_by_mail_once():
    from kts import heis as HEI
    from kts.db import init_db, query
    app = _app()
    _before(app)
    init_db(app)
    mails = _count(app, "outbox")
    with app.app_context():
        assert HEI.mail_reserve_selected() == 3
    sent = _newest(app, "outbox", mails)
    # the Head and the Institutional Coordinator of each; one mail where the two share an address; none to the others
    subject = "KTS 5.0: {} is a Participating Institution"
    assert [(m["to_addr"], m["subject"]) for m in sent] == [
        ("head@marked.example", subject.format("Marked Reserve College")), ("coord@marked.example", subject.format("Marked Reserve College")),
        ("one@unmarked.example", subject.format("Unmarked Reserve College")), ("coord@kerala.example", subject.format("Kerala Reserve College"))]
    body = sent[0]["body"]
    assert body.startswith(
        "Dear Sir/Madam,\n\nYour institution is now a selected Participating Institution of Kashi Tamil Sangamam 5.0 – Thirukkural "
        "Payilvom. The Nodal Institution of Puducherry had placed it in the reserve list; the reserve list has been discontinued, and "
        "every institution that was in it is selected.\n\nReference: KTS5-HEI-")
    assert "has selected your institution" not in body
    # ... and then the mail of a selected institution, as it is: the days, the steps, the page of the institution
    assert "Please assess your interested students on the Thirukkural by " in body and "nominate one student on merit" in body
    assert "/institution/login" in body and "/how-to-submit-the-student" in body
    assert body.endswith("/institutions\n\nCentral Institute of Classical Tamil, Chennai")
    assert "The Nodal Institution of Kerala had placed it in the reserve list" in sent[3]["body"]
    assert _value(app, MAIL) == "mailed 3 institutions"
    # once: neither a second start of the portal nor a second making of the database sends them again
    with app.app_context():
        assert HEI.mail_reserve_selected() == 0
    init_db(app)
    with app.app_context():
        assert HEI.mail_reserve_selected() == 0
    assert _count(app, "outbox") == mails + 4 and _value(app, MAIL) == "mailed 3 institutions"
    # the mail of a selection by the Nodal Institution is as it was
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    with app.app_context():
        pending = query("SELECT id FROM institutions WHERE name = 'Pending College'", one=True)["id"]
    assert "Pending College: accepted" in _act(officer, pending, "accept").get_data(as_text=True)
    last = _newest(app, "outbox", mails + 4)[-1]
    assert last["to_addr"] == "head@pending.example" and last["body"].startswith(
        "Dear Sir/Madam,\n\nThe Nodal Institution of Puducherry has selected your institution as a Participating Institution of Kashi "
        "Tamil Sangamam 5.0 – Thirukkural Payilvom.\n\nReference: KTS5-HEI-")


def test_the_start_of_the_portal_sends_the_mails():
    # the portal started on the database of before: create_app makes the database ready and then tells the institutions
    from kts.db import query
    app = _app()
    _before(app)
    mails = _count(app, "outbox")
    again = make_app(DATABASE=app.config["DATABASE"], INSTANCE_DIR=app.config["INSTANCE_DIR"], UPLOAD_DIR=app.config["UPLOAD_DIR"],
                     ADMIN_PASSWORD=None)
    assert _count(again, "outbox") == mails + 4 and _value(again, MAIL) == "mailed 3 institutions" and _value(again, MARK) == "3"
    with again.app_context():
        assert {r["status"] for r in query("SELECT status FROM institutions WHERE name LIKE '%Reserve College'")} == {"accepted"}


def test_two_starts_at_once_send_the_mails_once(monkeypatch):
    # another start of the portal has turned the mark between the reading of it and the turning of it here: this one sends nothing
    from kts import heis as HEI
    from kts.db import execute, init_db
    app = _app()
    _before(app)
    init_db(app)
    mails = _count(app, "outbox")
    real = HEI.now_ist

    def the_other_start_first():
        execute("UPDATE settings SET value = 'mailing 3 institutions' WHERE key = ?", (MAIL,))
        return real()

    monkeypatch.setattr(HEI, "now_ist", the_other_start_first)
    with app.app_context():
        assert HEI.mail_reserve_selected() == 0
    assert _count(app, "outbox") == mails and _value(app, MAIL) == "mailing 3 institutions"


def test_no_mail_after_the_last_day_of_the_nomination():
    # a copy of the database of before, restored when the nomination is over: the institutions become selected, and none is mailed
    from kts import heis as HEI
    from kts.db import init_db
    app = _app(**{"reg.end": "2020-01-01"})
    ids = _before(app)
    init_db(app)
    mails = _count(app, "outbox")
    with app.app_context():
        assert HEI.mail_reserve_selected() == 0
    assert _count(app, "outbox") == mails and _value(app, MAIL) == "not mailed: after the last day of the nomination"
    assert [_status(app, ids[name]) for name in MOVED] == ["accepted"] * 3


def test_the_public_pages_say_nothing_of_a_reserve_list():
    app = _app(**{"hei.public": "1"})
    _insert(app, "Kochi College", "Kerala", "Ernakulam", "accepted", 70)
    client = app.test_client()
    pages = {}
    for path in ("/", "/institutions", "/institutions/register", "/how-to-take-part", "/how-to-submit-the-student",
                 "/guidelines-for-nodal-institutions", "/nodal-institutions", "/join/kl", "/schedule"):
        r = client.get(path + "?lang=en")
        assert r.status_code == 200, path
        page = pages[path] = r.get_data(as_text=True)
        main = page[page.index("<main"):page.index("</main>")]
        assert "reserve list" not in main.lower() and ">Reserve<" not in main, path
    # the registration of institutions speaks of no selection since 1.2.201 (tests/test_all_registered_1117.py)
    assert "Every institution that registers is a Participating Institution.</" in pages["/institutions/register"]
    assert "does not by itself confer selection" not in pages["/institutions/register"]
    assert "the next eligible institution in the order of the marks may be included" in pages["/guidelines-for-nodal-institutions"]
    assert "select only the number prescribed for the State/UT in Annexure-I.</p>" in pages["/guidelines-for-nodal-institutions"]
    assert "every institution that registers is a Participating Institution" in pages["/how-to-submit-the-student"]      # 1.2.202
    assert "{reserve}" not in pages["/how-to-submit-the-student"]
    assert "See the Participating Institutions" in pages["/how-to-take-part"]      # 1.2.202
    # the step of the schedule: its title in the file, and in a database that held the title of before
    step = "Scrutiny and selection of the Participating Institutions by the Nodal Institutions"
    # (the schedule, which keeps the past steps: the home page lists only the next ones, and 22 November is past from the 23rd)
    assert f"<bdi>{step}</bdi>" in pages["/schedule"] and step + "," not in pages["/"] and step + "," not in pages["/schedule"]


def test_the_step_of_the_schedule_in_a_database_of_before():
    from kts.db import execute, init_db, query
    from kts.i18n import CATALOG
    step = "Scrutiny and selection of the Participating Institutions by the Nodal Institutions"
    app = _app()
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM events WHERE title = ?", (step,), one=True)["n"] == 1
        execute("UPDATE events SET title = ? WHERE title = ?", (step + ", with a reserve list", step))
    init_db(app)
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM events WHERE title = ?", (step,), one=True)["n"] == 1
        assert query("SELECT COUNT(*) AS n FROM events WHERE title LIKE '%reserve list%'", one=True)["n"] == 0
        # a title that CICT wrote in the Console stays
        execute("UPDATE events SET title = ? WHERE title = ?", ("Selection of the institutions, as CICT words it", step))
    init_db(app)
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM events WHERE title = 'Selection of the institutions, as CICT words it'", one=True)["n"] == 1
        execute("UPDATE events SET title = ? WHERE title LIKE 'Selection of the institutions, as%'", (step,))
    # the schedule finds the translation of the title (the schedule, not the home page: the step is past from 23 November 2026)
    page = app.test_client().get("/schedule?lang=ta").get_data(as_text=True)
    assert CATALOG["ta"]["timeline.hei_select"] in page and CATALOG["ta"]["timeline.hei_select"] != step


def test_the_texts_in_23_languages():
    from kts.i18n import CATALOG
    en = CATALOG["en"]
    new = json.loads((ROOT / "data" / "i18n" / "en.json").read_text(encoding="utf-8"))
    assert len(en) == 1547 and all(en[k] == new[k] for k in KEYS)
    # its second sentence since 1.2.201: every institution that registers is a Participating Institution
    assert en["hei.any_number"] == ("Any number of institutions of a State/UT may register. Every institution that registers is a "
                                    "Participating Institution.")
    assert en["timeline.hei_select"] == "Scrutiny and selection of the Participating Institutions by the Nodal Institutions"
    assert en["join.over"] == "More institutions have registered than will be selected: the Nodal Institution selects {n} on merit."
    assert en["ng.g5"] == "The Committee shall recommend the selected list for approval by the competent authority of the Nodal Institution."
    assert sorted(CATALOG) == sorted(LANGS)
    for code in LANGS:
        c = CATALOG[code]
        for key in KEYS:
            text = c[key]
            assert text.strip() == text and "\n" not in text and "  " not in text, (code, key)
            assert sorted(re.findall(r"\{[^}]*\}", text)) == sorted(re.findall(r"\{[^}]*\}", en[key])), (code, key)
            assert "reserve" not in text.lower() and (code == "en" or text != en[key]), (code, key)
        # the label beside the buttons of registration is still the first sentence of "any number"
        assert c["hei.any_number"].startswith(c["hei.no_limit"]), code


def test_the_mails_to_the_nodal_officers():
    from kts.db import set_setting
    from kts.nodal import account_paragraph
    app = _app()
    with app.app_context():
        text = account_paragraph(["Kerala"])
        assert "select the number of Participating Institutions that Annexure-I prescribes: Console > Institutions. " in text
        assert "reserve" not in text
        set_setting("hei.reserve_list", "1")
        assert "that Annexure-I prescribes, with a reserve list: Console > Institutions. " in account_paragraph(["Kerala"])

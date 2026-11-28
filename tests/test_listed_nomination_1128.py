"""
The institutions on the lists of the Nodal Officers assess and nominate up to 1 December 2026, 5:00 PM (1.2.236). CICT, 28 November
2026: "the selected from List of selected institutions given by the Nodal Officers (https://kts.cict.in/institutions#hei-selected) can
nominate the students for 3 days from now onwards. do all the modalities"; asked: "1 Dec 2026, 5:00 PM", "No mails", "Home band +
notice", and then "send mail for nomination only": the usual mails of the selection and the nomination go for a listed
institution; every other institution stays as it was (the last day of the nomination was 27 November 2026, 5:00 PM), without mail.

    python -m pytest tests/test_listed_nomination_1128.py -q
"""
import re

from test_campus import _accepted, _coordinator, _mails, _portal
from test_coordinator_nomination_1105 import _form, empty_limiter  # noqa: F401 - the limiter afresh for each test
from test_dates_hidden_1122 import _at
from test_quiz_band_1125 import _contrast
from test_timeline import _sql

LISTED = "Tamil Nadu"     # a State/UT whose Nodal Officer has given the list of the selected institutions
TITLE = "Nomination open again until 1 December 2026, 5:00 PM for the institutions on the lists of the Nodal Officers"
FLOW = ("KTS 5.0: you are selected by", "KTS 5.0: submit the nomination of", "KTS 5.0 application received:",
        "KTS 5.0: the nomination of", "KTS 5.0: the student of")


def _live(app, state=LISTED, **settings):
    """The days of the live portal (the assessments by 27 November, the nomination up to 27 November 2026, 5:00 PM) and an accepted
    institution of `state`, its coordinator signed in."""
    from kts.db import set_setting
    inst = _accepted(app)
    _sql(app, "UPDATE institutions SET state = ? WHERE id = ?", (state, inst["id"]))
    coord, token = _coordinator(app, inst)
    with app.app_context():
        for key, value in {"reg.end": "2026-11-27", "reg.end_time": "17:00", "camp.to": "2026-11-27", **settings}.items():
            set_setting(key, value)
    return inst, coord, token


def _flow_mails(app):
    return [m for m in _mails(app) if m["subject"].startswith(FLOW)]


def test_who_and_up_to_when(monkeypatch):
    from kts import heis as HEI
    from kts.db import all_settings, query, set_setting
    app = _portal()
    inst, _coord, _token = _live(app)
    assert LISTED in HEI.listed_states() and "Kerala" not in HEI.listed_states() and len(HEI.listed_states()) == 21
    with app.app_context():
        row = query("SELECT * FROM institutions WHERE id = ?", (inst["id"],), one=True)
        assert row["status"] == "accepted" and HEI.listed_until(all_settings()) == "2026-12-01T17:00"
        for moment, shown in (("2026-11-28T12:00:00", True), ("2026-12-01T17:00:00", True), ("2026-12-01T17:01:00", False),
                              ("2026-12-05T09:00:00", False)):
            _at(monkeypatch, moment)
            assert HEI.listed_open(row, all_settings()) is shown, moment
        _at(monkeypatch, "2026-11-29T10:00:00")
        # not of a State/UT without a list, not declined, not without a row
        assert not HEI.listed_open(dict(row, state="Kerala"), all_settings())
        assert not HEI.listed_open(dict(row, status="declined"), all_settings()) and not HEI.listed_open(None, all_settings())
        # the mails of the selection and the nomination: after the last day of the nomination for a listed institution only
        assert HEI.flow_mail(all_settings()) is False and HEI.flow_mail(all_settings(), row) is True
        assert HEI.flow_mail(all_settings(), dict(row, state="Kerala")) is False
        _at(monkeypatch, "2026-12-01T17:01:00")
        assert HEI.flow_mail(all_settings(), row) is False
        _at(monkeypatch, "2026-11-27T16:59:00")
        assert HEI.flow_mail(all_settings()) is True
        _at(monkeypatch, "2026-11-29T10:00:00")
        # the Console's setting: empty or unreadable, nobody
        for value in ("", "1 Dec 2026", "2026-12-01"):
            set_setting("nominate.listed_until", value)
            assert HEI.listed_until(all_settings()) == "" and not HEI.listed_open(row, all_settings()), value


def test_a_listed_institution_assesses_and_nominates_with_its_mails(monkeypatch):
    from kts.db import query
    app = _portal()
    inst, coord, token = _live(app, **{"camp.on": "0"})       # even with the assessments switched off for the others
    _at(monkeypatch, "2026-11-29T10:00:00")
    before = max([m["id"] for m in _mails(app)] or [0])
    home = coord.get("/institution").get_data(as_text=True)
    assert "<b>The nomination is open again for your institution until 01 December 2026, 5:00 PM</b>" in home
    assert f"(the institutions on the list of the Nodal Officer of {LISTED})" in home and "No e-mail is sent in these days" not in home
    assert "on or before <b>01 December 2026, 5:00 PM</b>" in home and "27 November 2026" not in home
    assert "The student is informed by e-mail; you then submit the nomination." in home     # the confirmation of "Select"
    assert 'name="test_from"' in home and 'max="2026-12-01"' in home          # the assessment form, whatever camp.on says
    # the online assessment, its days up to 1 December; its students take it
    page = coord.post("/institution/assessment", data={"_csrf": token, "action": "on", "test_from": "2026-11-29", "test_to": "2026-12-01",
                                                       "syllabus": "108"}, follow_redirects=True).get_data(as_text=True)
    assert "The online assessment is on" in page
    with app.app_context():
        row = query("SELECT test_on, test_from, test_to, test_slug FROM institutions WHERE id = ?", (inst["id"],), one=True)
    assert (row["test_on"], row["test_from"], row["test_to"]) == (1, "2026-11-29", "2026-12-01")
    home = coord.get("/institution").get_data(as_text=True)
    with app.app_context():
        code = query("SELECT test_code FROM institutions WHERE id = ?", (inst["id"],), one=True)["test_code"]
    assert f"/assessment/{row['test_slug']}" in home and code in home          # the link and the access code for the students
    signup = app.test_client().get(f"/assessment/{row['test_slug']}?lang=en")
    assert signup.status_code == 200 and 'name="code"' in signup.get_data(as_text=True)
    # the selection: the student and the coordinator are mailed, as before the last day
    page = coord.post("/institution/winner", data={"_csrf": token, "action": "enter", "name": "Arun Student", "email": "arun@student.example",
                                                    "mobile": "9123456781", "roll_no": "21ENG003", "course": "B.Sc Physics", "lang": "en"},
                      follow_redirects=True).get_data(as_text=True)
    assert "Arun Student is selected and informed by e-mail." in page
    assert ", and informed by e-mail.</p>" in page and "no e-mail" not in page
    link = re.search(r'href="(https?://[^"]+/register\?token=[A-Za-z0-9_-]+)"', page).group(1)
    # the nomination, submitted by the coordinator; the application number mailed to the student
    form_page, data = _form(coord, link)
    assert 'id="no-mail"' not in form_page
    r = coord.post("/register", data=data, content_type="multipart/form-data")
    assert r.status_code == 302 and "/register/done/" in r.headers["Location"]
    done = coord.get(r.headers["Location"] + "?lang=en").get_data(as_text=True)
    assert "No e-mail is sent now" not in done and "The student receives it by e-mail" in done
    with app.app_context():
        a = query("SELECT * FROM applications", one=True)
        inst_row = query("SELECT * FROM institutions WHERE id = ?", (inst["id"],), one=True)
    assert inst_row["application_id"] == a["id"] and a["status"] == "submitted" and a["app_no"] in done
    # the four mails of the selection and the nomination, and nothing else
    sent = sorted((m["to_addr"], m["subject"]) for m in _mails(app) if m["id"] > before)
    assert sent == sorted([("arun@student.example", f"KTS 5.0: you are selected by {inst['name']}"),
                           (inst["coord_email"], f"KTS 5.0: submit the nomination of Arun Student ({inst['ref']})"),
                           ("arun@student.example", f"KTS 5.0 application received: {a['app_no']}"),
                           (inst["coord_email"], f"KTS 5.0: the nomination of Arun Student is submitted ({a['app_no']})")])
    home = coord.get("/institution").get_data(as_text=True)
    assert "The nomination of <b>Arun Student</b> is submitted" in home and a["app_no"] in home
    # after 1 December 2026, 5:00 PM: nothing more
    _at(monkeypatch, "2026-12-01T17:01:00")
    home = coord.get("/institution").get_data(as_text=True)
    assert 'id="listed-open"' not in home


def test_any_other_institution_stays_closed(monkeypatch):
    from kts.db import query
    app = _portal()
    inst, coord, token = _live(app, state="Kerala")
    _at(monkeypatch, "2026-11-29T10:00:00")
    home = coord.get("/institution").get_data(as_text=True)
    assert 'id="listed-open"' not in home and "01 December 2026" not in home
    # its assessment cannot go past 27 November
    page = coord.post("/institution/assessment", data={"_csrf": token, "action": "on", "test_from": "2026-11-29", "test_to": "2026-12-01"},
                      follow_redirects=True).get_data(as_text=True)
    assert "The assessment must fall between" in page
    with app.app_context():
        assert query("SELECT test_on FROM institutions WHERE id = ?", (inst["id"],), one=True)["test_on"] == 0
    # its selection sends no mail either, and its nomination is closed
    page = coord.post("/institution/winner", data={"_csrf": token, "action": "enter", "name": "Arun Student", "email": "arun@student.example",
                                                    "mobile": "9123456781", "roll_no": "21ENG003", "course": "B.Sc Physics", "lang": "en"},
                      follow_redirects=True).get_data(as_text=True)
    link = re.search(r'href="(https?://[^"]+/register\?token=[A-Za-z0-9_-]+)"', page).group(1)
    _page, data = _form(coord, link)
    r = coord.post("/register", data=data, content_type="multipart/form-data")
    assert r.status_code == 403
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM applications", one=True)["n"] == 0
    assert _flow_mails(app) == []


def test_the_notice_and_the_band(monkeypatch):
    from kts.db import LISTED_NOTICE, LISTED_NOTICE_LINK, query
    from kts.i18n import CATALOG
    from test_timeline import _start
    app = _portal()
    assert LISTED_NOTICE[0] == TITLE and LISTED_NOTICE_LINK == "/institution/login"
    body = LISTED_NOTICE[1]
    assert body.startswith("The institutions on the lists of selected institutions given by the Nodal Officers (Participating "
                           "Institutions: https://kts.cict.in/institutions#hei-selected) may assess their students and nominate one "
                           "student on this portal until 1 December 2026, 5:00 PM (IST).")
    assert "The student is informed by e-mail when selected, and receives the application number by e-mail" in body
    assert "No e-mail" not in body and body.endswith("The nomination of the other institutions remains closed.")
    assert "27 November" not in body
    rows = _sql(app, "SELECT title, category, lang, pinned, published, link FROM notices WHERE link = ?", (LISTED_NOTICE_LINK,))
    assert rows == [(TITLE, "registration", "en", 1, 1, LISTED_NOTICE_LINK)]
    # once for each database: deleted in the Console, it does not come back; no mail with it
    again = _start(app)
    assert _sql(again, "SELECT COUNT(*) FROM notices WHERE link = ?", (LISTED_NOTICE_LINK,)) == [(1,)]
    assert _flow_mails(app) == []
    client = app.test_client()
    with app.app_context():
        nid = query("SELECT id FROM notices WHERE link = ?", (LISTED_NOTICE_LINK,), one=True)["id"]
    _at(monkeypatch, "2026-11-29T10:00:00")
    page = client.get("/?lang=en").get_data(as_text=True)
    band = page[page.index('<div class="listed-band"'):page.index('<div class="nodal-attention">')]
    assert re.search(r'<a class="listed-link" href="/institution/login" lang="en" dir="auto" style="[^"]*color:#fff;font-weight:800;font-size:1.4rem[^"]*">'
                     r'<span aria-hidden="true">📝 </span>' + re.escape(TITLE), band)
    assert f'<a class="listed-notice" href="/notices/{nid}"' in band and "Read more" in band and '<span class="new-badge">NEW</span>' in band
    assert "background:linear-gradient(90deg,#083f4a,#0b5563)" in band
    assert _contrast("#ffffff", "#0b5563") > 7 and _contrast("#ffd166", "#0b5563") > 4.5
    assert page.index('class="listed-band"') < page.index('class="pib-band"') < page.index('class="nodal-attention"')
    assert '<link rel="stylesheet" href="/static/css/portal.css?v=59">' in page
    # first among the latest notices of the home page (pinned, the newest: on the live portal it is put in after all the others; in a
    # new database all the notices of the start have the same moment)
    # (1.2.238: a moment after the start of the test, not 28 November 2026, 8:00 UTC, which that day passed)
    from datetime import datetime, timedelta, timezone
    later = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
    _sql(app, "UPDATE notices SET created_at = ? WHERE link = ?", (later, LISTED_NOTICE_LINK))
    page = client.get("/?lang=en").get_data(as_text=True)
    latest = page[page.index('<ul class="notice-list">'):]
    assert latest.index(f'href="/notices/{nid}"') < latest.index("</li>")
    for code in ("ta", "hi", "ur"):
        other = client.get(f"/?lang={code}").get_data(as_text=True)
        assert TITLE in other and CATALOG[code]["circ.new"] in other, code
    # up to 1 December 2026, 5:00 PM; while the notice is published
    _at(monkeypatch, "2026-12-01T17:01:00")
    assert '<div class="listed-band"' not in client.get("/?lang=en").get_data(as_text=True)
    _at(monkeypatch, "2026-11-29T10:00:00")
    _sql(app, "UPDATE notices SET published = 0 WHERE link = ?", (LISTED_NOTICE_LINK,))
    assert '<div class="listed-band"' not in client.get("/?lang=en").get_data(as_text=True)


def test_the_console():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS["nominate.listed_until"] == "2026-12-01T17:00"
    site = {k: kind for k, _label, kind in dict(SETTING_GROUPS)["Site"]}
    assert site["nominate.listed_until"] == "text"

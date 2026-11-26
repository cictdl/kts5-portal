"""
The registration of institutions, the assessment and the nomination up to 27 November 2026, the registration and the nomination up
to 5:00 PM of that day (1.2.209). CICT, 22 November 2026: "Registration * Up to 27 Nov 2026, 5:00 PM Last date for the registration
of institutions extend"; "Extend both to 27 Nov, 5 PM". CICT first wrote "But dont post the date outside" and then "change and show
in the portal", "show everywhere": the days are shown, and a switch of the Console, dates.public, takes them off every public page
and every mail when CICT wants that; then only the Console gives them.

    python -m pytest tests/test_dates_hidden_1122.py -q
"""
import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from conftest import make_app
from test_timeline import _sql, _start

ROOT = Path(__file__).resolve().parent.parent
# the last days as the pages and the mails write them: "27 Nov 2026", "27-11-2026", "27 November 2026"; and the days before the
# extension, as the |date filter writes them
NEW_DAY = re.compile(r"27(?:\s|&nbsp;)+Nov|27-11-2026|27\s+November|Nov(?:ember)?\s+27|2026-11-27")
OLD_DAYS = re.compile(r"\b(?:21|23|24) Nov 2026|\b(?:21|23|24)-11-2026")
PAGES = ("/", "/how-to-take-part", "/institutions", "/institutions/register", "/help", "/programme", "/schedule", "/examination",
         "/how-to-submit-the-student", "/register", "/register?token=not-a-token", "/join", "/join/tn", "/join/tn/poster", "/progress",
         "/progress.json", "/dashboard", "/my-college", "/nodal-institutions", "/notices")


@pytest.fixture(autouse=True)
def empty_limiter():
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def _portal(**settings):
    """The portal as the live one is set from this release: the built-in days, shown."""
    from kts.db import DEFAULT_SETTINGS, set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for key in ("hei.end", "hei.end_time", "camp.to", "reg.end", "reg.end_time", "dates.public", "kd.select_rows", "hei.select_step"):
            set_setting(key, DEFAULT_SETTINGS[key])
        for key, value in {"hei.open": "1", "reg.open": "0", "launch.on": "0", "hei.start": "2026-10-22", "join.on": "1",
                           **settings}.items():
            set_setting(key, value)
    # the notices put in by the start of the portal carry a day of their own, not the day the tests run
    _sql(app, "UPDATE notices SET created_at = '2026-11-13T05:00:00+00:00', updated_at = '2026-11-13T05:00:00+00:00'")
    return app


def _hidden(**settings):
    """
    ... with the last days taken off the public pages and the mails (dates.public off), and the pinned notice of the extension to
    27 November (1.2.210) taken off the notices, as CICT does then in the Console: the notices keep their own words.
    """
    app = _portal(**{"dates.public": "0", **settings})
    _sql(app, "UPDATE notices SET published = 0 WHERE title LIKE 'Registration of institutions extended to 27 November 2026%'")
    return app


def _at(monkeypatch, moment):
    """The clock of the portal at that moment (IST)."""
    from kts import campus, dashboard, drive, finder, heis, nodal, progress, public, utils
    when = datetime.fromisoformat(moment + "+05:30")
    for module in (utils, heis, public, finder, dashboard, progress, campus, drive, nodal):
        if hasattr(module, "now_ist"):
            monkeypatch.setattr(module, "now_ist", lambda: when)


def _get(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def _words(page):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))


def _without_own_days(page):
    """
    The page without the days that are its own - the day of the Kural of the day, and the day of the release ("Last updated", in
    the footer and on the pages of the policies) - which may fall on a day that the tests look for, as the release of 23 November
    2026 did (1.2.211).
    """
    import html
    from kts.i18n import CATALOG
    labels = sorted({html.escape(c["pol.updated"]) for c in CATALOG.values() if c.get("pol.updated")}, key=len, reverse=True)
    page = re.sub(r'<div class="label">[^<]*</div>', "", page)
    return re.sub("(?:" + "|".join(re.escape(label) for label in labels) + r"): <bdi>[^<]*</bdi>", "", page)


def _outbox(app):
    from kts.db import query
    with app.app_context():
        return query("SELECT * FROM outbox ORDER BY id")


# ---- the days ------------------------------------------------------------------------------------------------------------------

def test_the_settings():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS, RETIRED_DEFAULTS
    assert [DEFAULT_SETTINGS[k] for k in ("hei.end", "hei.end_time", "camp.to", "reg.end", "reg.end_time", "dates.public")] == [
        "2026-11-27", "17:00", "2026-11-27", "2026-11-27", "17:00", "1"]
    # a database that still holds the days of the extension to 21 November takes the new ones
    assert "2026-11-21" in RETIRED_DEFAULTS["hei.end"] and "2026-11-23" in RETIRED_DEFAULTS["camp.to"]
    assert "2026-11-24" in RETIRED_DEFAULTS["reg.end"]
    rows = {k: (label, kind) for _g, items in SETTING_GROUPS for k, label, kind in items}
    assert rows["dates.public"][1] == "bool" and rows["dates.public"][0].startswith("Show the last days of the registration of institutions")
    assert rows["reg.end_time"] == ("Hour of that day at which the nomination closes (HH:MM, IST; empty: at the end of the day)", "time")
    timeline = {r["key"]: r for r in json.loads((ROOT / "data" / "timeline.json").read_text(encoding="utf-8"))}
    assert timeline["hei_reg"]["starts"] == timeline["assess"]["starts"] == "2026-11-27"


def test_a_live_database_takes_the_days_once():
    app = make_app(ADMIN_PASSWORD=None)
    # the live database: the days of 1.2.208, and their two steps of the schedule
    for key, value in (("hei.end", "2026-11-21"), ("camp.to", "2026-11-23"), ("reg.end", "2026-11-24")):
        _sql(app, "UPDATE settings SET value = ? WHERE key = ?", (value, key))
    steps = {r["key"]: r["title"] for r in json.loads((ROOT / "data" / "timeline.json").read_text(encoding="utf-8"))}
    _sql(app, "UPDATE events SET starts_at = '2026-11-21T00:00' WHERE title = ?", (steps["hei_reg"],))
    _sql(app, "UPDATE events SET starts_at = '2026-11-23T00:00' WHERE title = ?", (steps["assess"],))
    _sql(app, "DELETE FROM settings WHERE key IN ('reg.end_time', 'dates.public')")      # not there before this release
    again = _start(app)
    assert _sql(again, "SELECT key, value FROM settings WHERE key IN ('hei.end', 'camp.to', 'reg.end', 'reg.end_time') ORDER BY key") == [
        ("camp.to", "2026-11-27"), ("hei.end", "2026-11-27"), ("reg.end", "2026-11-27"), ("reg.end_time", "17:00")]
    assert _sql(again, "SELECT starts_at FROM events WHERE title IN (?, ?)", (steps["hei_reg"], steps["assess"])) == [
        ("2026-11-27T00:00",), ("2026-11-27T00:00",)]
    # a day that CICT sets in the Console afterwards stays
    _sql(again, "UPDATE settings SET value = '2026-11-30' WHERE key = 'hei.end'")
    third = _start(again)
    assert _sql(third, "SELECT value FROM settings WHERE key = 'hei.end'") == [("2026-11-30",)]


def test_up_to_5_pm_on_27_november(monkeypatch):
    from kts import heis as HEI, public
    from kts.db import all_settings
    app = _portal()
    client = app.test_client()
    with app.app_context():
        settings = all_settings()
    for moment, open_ in (("2026-11-25T10:00:00", True), ("2026-11-27T16:59:00", True), ("2026-11-27T17:00:00", False),
                          ("2026-11-28T09:00:00", False)):
        _at(monkeypatch, moment)
        assert (HEI.window(settings) == "open") is open_, moment
        assert public.nomination_open(settings) is open_, moment
    page = _get(client, "/institutions/register?lang=en")
    assert 'name="head_name"' not in page and "Applications of institutions closed on 27 Nov 2026, 5:00 PM." in _words(page)
    # from the hour the pages say that it is closed, not only from the next day: the banner, the form of the nomination
    from kts.utils import reg_over, registration_state
    _at(monkeypatch, "2026-11-27T16:30:00")
    assert "Registration is now open for Participating Institutions." in _get(client, "/?lang=en")
    _at(monkeypatch, "2026-11-27T17:30:00")
    home, register = _get(client, "/?lang=en"), _get(client, "/register?lang=en")
    assert "Registration is closed." in home and "Registration is now open for Participating Institutions." not in home
    assert "Registration is closed." in register and "Registrations closed on" in register
    assert "Registration is now open for Participating Institutions." not in register
    # ... and with the students' registration switched on (reg.open), the form closes at the hour all the same
    opened = dict(settings, **{"reg.open": "1", "reg.start": "2026-10-22"})
    assert registration_state(opened) == "closed" and reg_over(opened)
    _at(monkeypatch, "2026-11-27T16:59:00")
    assert registration_state(opened) == "open" and not reg_over(opened)
    # without an hour, the whole day, as before
    _at(monkeypatch, "2026-11-27T20:00:00")
    assert public.nomination_open(dict(settings, **{"reg.end_time": ""})) and registration_state(dict(opened, **{"reg.end_time": ""})) == "open"
    assert not public.nomination_open(dict(settings, **{"reg.end_time": "17:00"}))
    assert not reg_over(dict(settings, **{"reg.end": ""})) and not reg_over(dict(settings, **{"reg.end_time": "5 pm"}))
    assert HEI.nominate_hour_words("en", {"reg.end_time": "17:00"}) == ", 5:00 PM" and HEI.nominate_hour_words("ta", {"reg.end_time": ""}) == ""


def test_the_pages_give_the_days(monkeypatch):
    app = _portal()
    _at(monkeypatch, "2026-11-25T10:00:00")
    client = app.test_client()
    page = _get(client, "/?lang=en")
    home = _words(page)
    assert "Registration Up to 27 Nov 2026, 5:00 PM Last date for the registration of institutions" in home
    assert re.search(r'<li class="kd-blink"><span class="kd-when"><bdi>Up to 27 Nov 2026, 5:00 PM</bdi></span>', page)
    assert re.search(r'<span class="banner-date">Last date: <bdi>(<bdi dir="ltr">)?27 Nov 2026, 5:00 PM', page)
    assert not OLD_DAYS.search(_without_own_days(page))
    assert 'name="head_name"' in _get(client, "/institutions/register?lang=en")
    guide = _words(_get(client, "/how-to-take-part?lang=en"))
    assert "Last date for institutions to register 27 Nov 2026, 5:00 PM" in guide and "Assessments at the institutions By 27 Nov 2026" in guide
    assert "Nomination of one student by each Participating Institution on the portal 27 Nov 2026, 5:00 PM" in guide
    assert "Register your institution by 27 Nov 2026, 5:00 PM" in guide and "Submit the nomination by 27 Nov 2026, 5:00 PM" in guide
    # no selection of institutions since 1.2.201: its tile goes with its rows of the Key dates (kd.select_rows)
    assert "Selection of the Participating Institutions by the Nodal Institutions 22 Nov 2026" not in guide
    helps = _words(_get(client, "/help?lang=en"))
    assert "by 27 Nov 2026, 5:00 PM , or complete" in helps or "by 27 Nov 2026, 5:00 PM, or complete" in helps
    assert "on or before 27 Nov 2026, 5:00 PM" in helps and "By 27 Nov 2026 it assesses" in helps
    submit = _words(_get(client, "/how-to-submit-the-student?lang=en"))
    assert "27 Nov 2026, 5:00 PM" in submit
    # in the other languages, as the portal writes days and hours in them
    assert "27-11-2026, 17:00" in _get(client, "/?lang=hi") and "27-11-2026, 17:00" in _get(client, "/how-to-take-part?lang=ta")
    from kts import finder
    from kts.db import all_settings
    with app.test_request_context():
        words = finder.hub(all_settings(), "en")["words"]
        assert words["hei_end"] == "27 November 2026, 5:00 PM" and words["reg_end"] == "27 November 2026, 5:00 PM"
        assert words["camp_to"] == "27 November 2026"


def test_the_schedule_without_the_selection(monkeypatch):
    from kts import dashboard as D, public
    from kts.db import all_settings, set_setting
    app = _portal()
    _at(monkeypatch, "2026-11-25T10:00:00")
    steps = {r["key"]: r["title"] for r in json.loads((ROOT / "data" / "timeline.json").read_text(encoding="utf-8"))}
    with app.test_request_context():
        upcoming, past = public._timeline(all_settings())
        titles = {r["title"] for r in upcoming + past}
        assert {steps["hei_reg"], steps["assess"], "Last date for the institutions to register their selected students"} <= titles
        assert steps["hei_select"] not in titles
        keys = {m["key"] for m in D.pipeline_view()["milestones"]}
        assert {"hei_reg", "assess", "reg_close"} <= keys and "hei_select" not in keys
    schedule = _words(_get(app.test_client(), "/schedule?lang=en"))
    assert "27 Nov 2026 Last date for the registration of institutions" in schedule and "Scrutiny and selection" not in schedule
    # the last day of the nomination at its hour
    assert "27 Nov 2026, 05:00 PM Last date for the institutions to register their selected students" in schedule
    # while the rows of the selection are shown (kd.select_rows), the step is on the schedule, and the Key dates give the
    # nomination with its hour
    with app.app_context():
        set_setting("kd.select_rows", "1")
    with app.test_request_context():
        upcoming, past = public._timeline(all_settings())
        assert steps["hei_select"] in {r["title"] for r in upcoming + past}
        assert "hei_select" in {m["key"] for m in D.pipeline_view()["milestones"]}
    home = _words(_get(app.test_client(), "/?lang=en"))
    assert "By 27 Nov 2026 Thirukkural assessment of the interested students by each Participating Institution" in home
    assert "27 Nov 2026, 5:00 PM Each Participating Institution nominates one student on merit through the CICT portal" in home


def test_the_circular_and_the_notice_of_the_launch_take_the_days_once():
    from kts.db import LAUNCH_BODY_1208, LAUNCH_NOTICE, NODAL_DAYS, NODAL_DAYS_1208
    assert NODAL_DAYS.startswith("up to 27 November 2026, 5:00 PM. The Nodal Institution of each State/UT scrutinises them")
    assert "by 27 November and nominates one on merit by 27 November 2026, 5:00 PM" in NODAL_DAYS
    assert not re.search(r"\b2[1-4] November", NODAL_DAYS) and "up to 21 November 2026" in NODAL_DAYS_1208
    assert "register on kts.cict.in up to 27 November 2026, 5:00 PM; the Nodal Institutions select" in LAUNCH_NOTICE[1]
    assert not re.search(r"\b2[1-4] November", LAUNCH_NOTICE[1]) and "up to 21 November 2026; the Nodal" in LAUNCH_BODY_1208
    app = make_app(ADMIN_PASSWORD=None)
    bodies = " ".join(body for (body,) in _sql(app, "SELECT body FROM notices"))
    assert NODAL_DAYS in bodies and LAUNCH_NOTICE[1] in bodies
    # the live database: the two notices as 1.2.203 left them
    _sql(app, "UPDATE notices SET body = replace(body, ?, ?) WHERE category = 'circular'", (NODAL_DAYS, NODAL_DAYS_1208))
    _sql(app, "UPDATE notices SET body = ? WHERE title = ?", (LAUNCH_BODY_1208, LAUNCH_NOTICE[0]))
    _sql(app, "DELETE FROM settings WHERE key = 'migrate.dates_1122.notices'")
    again = _start(app)
    bodies = " ".join(body for (body,) in _sql(again, "SELECT body FROM notices"))
    assert NODAL_DAYS in bodies and NODAL_DAYS_1208 not in bodies and LAUNCH_NOTICE[1] in bodies and LAUNCH_BODY_1208 not in bodies
    # once: a notice in the words of CICT stays
    _sql(again, "UPDATE notices SET body = 'In the words of CICT.' WHERE title = ?", (LAUNCH_NOTICE[0],))
    third = _start(again)
    assert _sql(third, "SELECT body FROM notices WHERE title = ?", (LAUNCH_NOTICE[0],)) == [("In the words of CICT.",)]


def test_the_mails_give_the_days(monkeypatch):
    from kts import campus, heis as HEI, nodal, progress as P
    from kts.db import execute, query
    from test_nodal_signin import _account
    from test_progress import _inst, _student
    app = _portal()
    _at(monkeypatch, "2026-11-25T10:00:00")
    iid = _inst(app, "Dated College", state="Kerala")
    sid = _student(app, iid, "Mala Student")
    invited = _inst(app, "Asked College", state="Kerala", status="identified")
    uid = _account(app, "dated.kerala@tests.example", ["Kerala"])
    with app.test_request_context():
        execute("UPDATE institutions SET invite_token = 'tok-1209' WHERE id = ?", (invited,))
        row = query("SELECT * FROM institutions WHERE id = ?", (iid,), one=True)
        HEI.mail_decision(row)
        HEI.mail_invited(query("SELECT * FROM institutions WHERE id = ?", (invited,), one=True))
        _subject, nodal_body = nodal.signin_mail(query("SELECT * FROM users WHERE id = ?", (uid,), one=True))
        inst = P.institutions(ids=[iid])[0]
        select = P.mails_for(inst, "select")[0]
        campus.registration_mail(row, query("SELECT * FROM campus_students WHERE id = ?", (sid,), one=True))
    bodies = "\n".join(m["body"] for m in _outbox(app))
    assert "on the Thirukkural by 27 November 2026 (a short written test" in bodies
    assert "Supervisor/Guide, by 27 November 2026, 5:00 PM.\n" in bodies
    assert "nominates one student on merit on the portal by 27 November 2026, 5:00 PM. The steps" in bodies
    assert "your nomination on the KTS 5.0 portal on or before 27 November 2026, 5:00 PM. Give the coordinator" in bodies
    assert "register on the portal up to 27 November 2026, 5:00 PM: " in nodal_body
    assert "nominates one student by 27 November 2026, 5:00 PM; " in nodal_body
    assert "KTS 5.0: select your student by 27 November 2026 – Dated College" in select[1]
    assert "on or before 27 November 2026: with the online" in select[2] and "on or before 27 November 2026, 5:00 PM, with the" in select[2]


def test_the_letter_of_the_nodal_institutions_gives_the_days(monkeypatch):
    app = _portal()
    _at(monkeypatch, "2026-11-25T10:00:00")
    r = app.test_client().get("/nodal-institutions/letter.docx?state=Kerala&lang=en")
    assert r.status_code == 200
    xml = zipfile.ZipFile(io.BytesIO(r.data)).read("word/document.xml").decode("utf-8")
    assert "Assess your students by 27 November 2026." in xml and "Nominate one student on merit by 27 November 2026, 5:00 PM." in xml
    assert "24 November" not in xml and "23 November" not in xml


# ---- the switch: the last days off the public pages and the mails ---------------------------------------------------------------

def test_the_texts_without_a_date_in_the_23_languages():
    from kts import i18n
    undated = sorted(i18n.UNDATED)
    assert len(undated) == 26 and "hub.i_shut_t" in undated and "guide.s4_t" in undated and "hei.ended" in undated
    for code in i18n.CATALOG:
        for key in undated:
            text = i18n.CATALOG[code].get(key + "_nd")
            assert text, (code, key)
            assert not re.search(r"\{(date|hei_end|camp_to|reg_end|select)\}", text), (code, key)
    assert len(i18n.CATALOG["en"]) == 1551
    # outside a request the texts are as they were; in one, as the setting says
    assert "{camp_to}" in i18n.text("hub.i_shut_t", "en")
    app = _hidden()
    with app.test_request_context("/?lang=en"):
        assert i18n.t("hub.i_shut_t") == "Participating Institutions: assess your students and nominate one"
        assert i18n.t("guide.s4_t") == "Your nomination" and i18n.t("guide.i1_t") == "Register your institution"
    from kts.db import set_setting
    with app.app_context():
        set_setting("dates.public", "1")
    with app.test_request_context("/?lang=en"):
        assert "{camp_to}" in i18n.t("hub.i_shut_t") and i18n.t("guide.s4_t") == "Your nomination by {reg_end}"


@pytest.mark.parametrize("lang", ["en", "hi", "ta", "ur"])
def test_switched_off_no_public_page_gives_a_last_day(monkeypatch, lang):
    app = _hidden()
    _at(monkeypatch, "2026-11-25T10:00:00")
    client = app.test_client()
    # (the notices keep their own words: the circular of the Nodal Institutions gives the days, switched off or not)
    for path in (p for p in PAGES if p != "/notices"):
        page = _without_own_days(_get(client, path + ("&" if "?" in path else "?") + f"lang={lang}"))
        assert not NEW_DAY.search(page), (lang, path, NEW_DAY.search(page).group(0) if NEW_DAY.search(page) else "")
        assert not OLD_DAYS.search(page), (lang, path, OLD_DAYS.search(page).group(0) if OLD_DAYS.search(page) else "")
        # no "n days left" to the last days either (the Nodal Officers' days of the verification keep theirs)
        if path.startswith("/join"):
            assert 'class="hub-chip' not in page, (lang, path)
    from kts import finder, public
    from kts.db import all_settings
    with app.test_request_context(f"/?lang={lang}"):
        chips = finder.hub(all_settings(), lang)["chips"]
        assert chips["student"] is None and chips["inst"] is None and chips["nodal"]
    # the registration of institutions and the nomination are open all the same
    assert 'name="head_name"' in _get(client, f"/institutions/register?lang={lang}")
    with app.app_context():
        assert public.nomination_open(all_settings())


def test_switched_off_the_pages_say_it_without_the_day(monkeypatch):
    app = _hidden()
    _at(monkeypatch, "2026-11-25T10:00:00")
    client = app.test_client()
    home = _get(client, "/?lang=en")
    assert "Last date: " not in home and 'class="kd-blink"' not in home and "Last date for the registration of institutions" not in home
    guide = _get(client, "/how-to-take-part?lang=en")
    assert "Register your institution</b>" in guide and "Last date for institutions to register" not in guide
    assert "Nomination of one student by each Participating Institution on the portal" not in guide
    helps = _words(re.sub(r"<[^>]+>", "", _get(client, "/help?lang=en")))
    assert "Register your institution, or complete the registration" in helps and "It assesses its interested students" in helps
    assert "Assess your students, select one on merit, and make sure the student registers." in helps
    assert "க்குள்" not in re.sub(r"<[^>]+>", "", _get(client, "/help?lang=ta"))
    hindi = re.sub(r"<[^>]+>", "", _get(client, "/help?lang=hi"))
    assert " तक अपने विद्यार्थियों" not in hindi and "विद्यार्थी  तक" not in hindi
    assert "Last date for institutions" not in _get(client, "/institutions/register?lang=en")
    assert "Last date for institutions" not in _get(client, "/institutions?lang=en")
    # after the hour: closed, without the day
    _at(monkeypatch, "2026-11-27T17:00:00")
    page = _get(client, "/institutions/register?lang=en")
    assert 'name="head_name"' not in page and "Applications of institutions are closed." in page and not NEW_DAY.search(page)
    schedule = _get(client, "/schedule?lang=en")
    assert "Last date for the registration of institutions" not in schedule and "Last date for the assessment" not in schedule


def test_switched_off_the_console_gives_the_day(monkeypatch):
    from test_public_fixes import _staff
    app = _hidden()
    _at(monkeypatch, "2026-11-25T10:00:00")
    admin = _staff(app, "dates.admin@tests.example", "superadmin")
    assert "27 Nov 2026, 5:00 PM" in admin.get("/console/institutions").get_data(as_text=True)
    settings = admin.get("/console/settings").get_data(as_text=True)
    assert 'name="hei.end" value="2026-11-27"' in settings and 'name="reg.end" value="2026-11-27"' in settings
    assert 'name="camp.to" value="2026-11-27"' in settings and 'name="dates.public"' in settings


def test_switched_off_the_mails_leave_the_day_out(monkeypatch):
    from kts import campus, heis as HEI, nodal, progress as P
    from kts.db import execute, query
    from test_nodal_signin import _account
    from test_progress import _inst, _student
    app = _hidden()
    _at(monkeypatch, "2026-11-25T10:00:00")
    iid = _inst(app, "Quiet College", state="Kerala")
    sid = _student(app, iid, "Mala Student")
    invited = _inst(app, "Invited College", state="Kerala", status="identified")
    uid = _account(app, "quiet.kerala@tests.example", ["Kerala"])
    with app.test_request_context():
        execute("UPDATE institutions SET invite_token = 'tok-1209' WHERE id = ?", (invited,))
        row = query("SELECT * FROM institutions WHERE id = ?", (iid,), one=True)
        HEI.mail_decision(row)
        HEI.mail_invited(query("SELECT * FROM institutions WHERE id = ?", (invited,), one=True))
        _subject, nodal_body = nodal.signin_mail(query("SELECT * FROM users WHERE id = ?", (uid,), one=True))
        inst = P.institutions(ids=[iid])[0]
        reminders = P.mails_for(inst, "start") + P.mails_for(inst, "select")
        campus.registration_mail(row, query("SELECT * FROM campus_students WHERE id = ?", (sid,), one=True))
    mails = [(m["subject"], m["body"]) for m in _outbox(app)] + [(s, b) for _a, s, b in reminders] + [("", nodal_body)]
    assert len(mails) >= 8
    for subject, body in mails:
        assert not NEW_DAY.search(subject + body), (subject, NEW_DAY.search(subject + body).group(0))
    decision = next(b for s, b in mails if "is a Participating Institution" in s)
    assert "on the Thirukkural (a short written test" in decision and "Faculty Supervisor/Guide.\n" in decision
    assert any("nominates one student on merit on the portal. The steps" in b for _s, b in mails)
    assert "register on the portal: " in nodal_body and "• Each Participating Institution nominates one student; " in nodal_body
    assert any("KTS 5.0: select your student – Quiet College" in s for _a, s, _b in reminders)
    assert any("Assess your interested students on the Thirukkural: with the online" in b for _a, _s, b in reminders)
    assert any("your nomination on the KTS 5.0 portal. Give the coordinator" in b for _s, b in mails)


def test_switched_off_the_letter_the_schedule_and_the_milestones(monkeypatch):
    from kts import dashboard as D, public
    from kts.db import all_settings
    app = _hidden()
    _at(monkeypatch, "2026-11-25T10:00:00")
    for lang in ("en", "ta"):
        r = app.test_client().get(f"/nodal-institutions/letter.docx?state=Kerala&lang={lang}")
        assert r.status_code == 200
        xml = zipfile.ZipFile(io.BytesIO(r.data)).read("word/document.xml").decode("utf-8")
        assert not NEW_DAY.search(xml) and "24 November" not in xml and "23 November" not in xml, lang
        if lang == "en":
            assert "Assess your students." in xml and "Nominate one student on merit." in xml
    steps = {r["key"]: r["title"] for r in json.loads((ROOT / "data" / "timeline.json").read_text(encoding="utf-8"))}
    hidden = {steps["hei_reg"], steps["hei_select"], steps["assess"], "Last date for the institutions to register their selected students"}
    with app.test_request_context():
        upcoming, past = public._timeline(all_settings())
        assert not hidden & {r["title"] for r in upcoming + past}
        assert not {"hei_reg", "hei_select", "assess", "reg_close"} & {m["key"] for m in D.pipeline_view()["milestones"]}


# ---- what goes with the extension -----------------------------------------------------------------------------------------------

def test_the_notice_of_the_extension_to_21_november_is_taken_off_once():
    from kts.db import EXT21_NOTICE
    app = _portal()
    assert _sql(app, "SELECT published FROM notices WHERE title = ?", (EXT21_NOTICE[0],)) == [(0,)]
    assert EXT21_NOTICE[0] not in app.test_client().get("/notices?lang=en").get_data(as_text=True)
    # once: published again by CICT, it stays
    _sql(app, "UPDATE notices SET published = 1 WHERE title = ?", (EXT21_NOTICE[0],))
    again = _start(app)
    assert _sql(again, "SELECT published FROM notices WHERE title = ?", (EXT21_NOTICE[0],)) == [(1,)]


def test_the_nomination_form_and_the_posters_give_the_new_day():
    import fitz
    with fitz.open(str(ROOT / "static" / "KTS5-nomination-form.pdf")) as doc:
        text = " ".join(" ".join(page.get_text().split()) for page in doc)
    assert "24 November" not in text and text.count("27 November 2026, 5:00 PM") == 2
    assert "Engagement Programme of Kashi Tamil Sangamam 5.0 (nomination on or before 27 November 2026, 5:00 PM)" in text
    assert "https://kts.cict.in/register on or before 27 November 2026, 5:00 PM. The institution keeps the original." in text
    posters = sorted((ROOT / "static" / "posters").glob("KTS5-poster-1-*.pdf"))
    assert len(posters) == 23
    for pdf in posters:
        with fitz.open(str(pdf)) as doc:
            text = " ".join(page.get_text() for page in doc)
        assert "27 Nov 2026" in text and not re.search(r"\b(?:21|23|24) Nov", text), pdf.name


def test_the_press_release_of_21_november():
    news = json.loads((ROOT / "data" / "news.json").read_text(encoding="utf-8"))
    item = next(n for n in news if n["key"] == "pib-2026-11-21-kts5-rangoli")
    assert item["date"] == "2026-11-21" and item["kind"] == "press"      # (reports of later days follow it since 1.2.211)
    assert [v["lang"] for v in item["versions"]] == ["en", "as", "or", "ta", "ur"]
    assert all(v["time"] == "7:27 PM" and v["url"].startswith("https://www.pib.gov.in/PressReleasePage.aspx?PRID=233") for v in item["versions"])
    app = make_app(ADMIN_PASSWORD=None)
    page = app.test_client().get("/in-the-news?lang=en").get_data(as_text=True)
    assert "Rangoli competition at Assi Ghat builds enthusiasm for Kashi Tamil Sangamam 5.0" in page
    tamil = app.test_client().get("/in-the-news?lang=ta").get_data(as_text=True)
    assert "அஸ்ஸி படித்துறையில் ரங்கோலிப் போட்டி" in tamil

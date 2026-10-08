"""
The tentative timeline of KTS 5.0 (28.11.2026 – 12.12.2026): the dates of registration and of the
test, the timeline on the schedule page, the banner.

    python -m pytest tests -q
"""
import json
import sqlite3
from datetime import datetime

import pytest
from markupsafe import escape

from conftest import ROOT, make_app

SEEDS = json.loads((ROOT / "data" / "timeline.json").read_text(encoding="utf-8"))
NAMES = ("INSTANCE_DIR", "DATABASE", "UPLOAD_DIR")
# the rows in the order of the timeline; those marked are dates kept as settings
ORDER = ["circular", "reg_open*", "reg_close*", "exam*", "selection", "letters", "internship", "live", "papers", "forward",
         "eval_start", "eval_end", "booklet", "present", "printed", "inauguration*", "valedictory*"]
KEYS = ["timeline." + name.rstrip("*") for name in ORDER]


def _portal(**changed):
    """A portal of its own with the dates it comes with (make_app opens the registration wide)."""
    from kts.db import DEFAULT_SETTINGS, set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for key in ("reg.start", "reg.end"):
            set_setting(key, DEFAULT_SETTINGS[key])
        for key, value in changed.items():
            set_setting(key, value)
    return app


def _start(app):
    """The portal started again on the same database, as after an update; nothing set by the tests."""
    from config import Config
    from kts import create_app
    values = {name: app.config[name] for name in NAMES}
    values["ADMIN_PASSWORD"] = None
    return create_app(type("StartedAgain", (Config,), values))


def _sql(app, statement, args=()):
    conn = sqlite3.connect(str(app.config["DATABASE"]))
    rows = conn.execute(statement, args).fetchall()
    conn.commit()
    conn.close()
    return rows


def _settings(app):
    return dict(_sql(app, "SELECT key, value FROM settings"))


def _on(monkeypatch, day, time="09:00"):
    """The clock of the portal stands at this moment (IST)."""
    from kts import public, utils
    now = datetime.fromisoformat(f"{day}T{time}").replace(tzinfo=utils.IST)
    monkeypatch.setattr(utils, "now_ist", lambda: now)
    monkeypatch.setattr(public, "now_ist", lambda: now)


def _text(key, lang="en"):
    from kts.i18n import CATALOG
    return str(escape(CATALOG[lang][key]))


def _page(app, path):
    r = app.test_client().get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def _halves(page):
    """(upcoming, past) of the schedule page."""
    start = page.index("<h2>" + _text("schedule.upcoming") + "</h2>")
    mark = '<h2 style="margin-top:28px">' + _text("schedule.past") + "</h2>"
    if mark not in page:
        return page[start:], ""
    return page[start:page.index(mark)], page[page.index(mark):]


def _banner(page):
    start = page.index('<div class="banner">')
    return page[start:page.index("</div></div>", start)]


# ---- the dates ---------------------------------------------------------------------------------

def test_the_dates_of_the_timeline_are_the_defaults():
    from kts.db import DEFAULT_SETTINGS
    # the timeline of 8 October 2026
    assert DEFAULT_SETTINGS["reg.start"] == "2026-10-15" and DEFAULT_SETTINGS["reg.end"] == "2026-10-21"
    assert DEFAULT_SETTINGS["exam.date"] == "2026-10-22"
    assert DEFAULT_SETTINGS["letter.date"] == "2026-10-25" and DEFAULT_SETTINGS["internship.start"] == "2026-10-26"
    assert DEFAULT_SETTINGS["papers.due"] == "2026-11-05" and DEFAULT_SETTINGS["present.due"] == "2026-11-15"
    assert DEFAULT_SETTINGS["kts.start"] == "2026-11-28" and DEFAULT_SETTINGS["kts.end"] == "2026-12-12"
    # the days of the week as the calendar has them
    days = [datetime.fromisoformat(DEFAULT_SETTINGS[key]).strftime("%a") for key in ("reg.start", "reg.end", "exam.date", "kts.start", "kts.end")]
    assert days == ["Thu", "Wed", "Thu", "Sat", "Sat"]


def test_a_database_of_an_earlier_version_receives_the_dates():
    app = make_app(ADMIN_PASSWORD=None)
    for key, old in (("reg.start", "2026-09-25"), ("reg.end", "2026-11-15"), ("exam.date", "2026-11-29")):
        _sql(app, "UPDATE settings SET value = ? WHERE key = ?", (old, key))
    _sql(app, "DELETE FROM settings WHERE key IN ('kts.start', 'kts.end', 'schedule.tentative')")
    settings = _settings(_start(app))
    assert (settings["reg.start"], settings["reg.end"], settings["exam.date"]) == ("2026-10-15", "2026-10-21", "2026-10-22")
    assert (settings["kts.start"], settings["kts.end"], settings["schedule.tentative"]) == ("2026-11-28", "2026-12-12", "1")

def test_the_live_database_moves_to_the_timeline_of_8_october():
    """Version 1.2.31 on the live site held the earlier dates as they came: all of them move."""
    app = make_app(ADMIN_PASSWORD=None)
    for key, old in (("reg.start", "2026-10-10"), ("reg.end", "2026-10-16"), ("exam.date", "2026-10-19"),
                     ("letter.date", "2026-10-22"), ("internship.start", "2026-10-23")):
        _sql(app, "UPDATE settings SET value = ? WHERE key = ?", (old, key))
    for title, starts, ends in ((SEEDS[1]["title"], "2026-10-20T00:00", "2026-10-21T00:00"),
                                (SEEDS[2]["title"], "2026-10-22T00:00", None),
                                (SEEDS[3]["title"], "2026-10-23T00:00", None)):
        _sql(app, "UPDATE events SET starts_at = ?, ends_at = ? WHERE title = ?", (starts, ends, title))
    # another event that an administrator moved by hand
    _sql(app, "UPDATE events SET starts_at = '2026-11-06T10:00' WHERE title = ?", (SEEDS[7]["title"],))
    again = _start(app)
    settings = _settings(again)
    moved = [settings[k] for k in ("reg.start", "reg.end", "exam.date", "letter.date", "internship.start")]
    assert moved == ["2026-10-15", "2026-10-21", "2026-10-22", "2026-10-25", "2026-10-26"]
    rows = {t: (s, e) for t, s, e in _sql(again, "SELECT title, starts_at, ends_at FROM events")}
    assert rows[SEEDS[1]["title"]] == ("2026-10-23T00:00", "2026-10-24T00:00")
    assert rows[SEEDS[2]["title"]] == ("2026-10-25T00:00", None) and rows[SEEDS[3]["title"]] == ("2026-10-26T00:00", None)
    assert rows[SEEDS[7]["title"]][0] == "2026-11-06T10:00"
    # an event that the administrator moved away from the old days stays where it was put
    app = make_app(ADMIN_PASSWORD=None)
    _sql(app, "UPDATE events SET starts_at = '2026-10-22T15:00', ends_at = NULL WHERE title = ?", (SEEDS[2]["title"],))
    assert _sql(_start(app), "SELECT starts_at FROM events WHERE title = ?", (SEEDS[2]["title"],)) == [("2026-10-22T15:00",)]


def test_dates_set_by_the_administrator_are_left_alone():
    app = make_app(ADMIN_PASSWORD=None)
    for key, own in (("reg.start", "2026-10-01"), ("reg.end", "2026-11-20"), ("exam.date", "2026-12-01"), ("kts.end", "2026-12-14")):
        _sql(app, "UPDATE settings SET value = ? WHERE key = ?", (own, key))
    settings = _settings(_start(app))
    assert (settings["reg.start"], settings["reg.end"], settings["exam.date"]) == ("2026-10-01", "2026-11-20", "2026-12-01")
    assert settings["kts.end"] == "2026-12-14"


@pytest.mark.parametrize("day, state", [("2026-10-14", "not_yet"), ("2026-10-15", "open"), ("2026-10-21", "open"), ("2026-10-22", "closed")])
def test_registration_follows_the_dates(monkeypatch, day, state):
    app = _portal()
    _on(monkeypatch, day)
    page = _page(app, "/register?lang=en")
    assert ('name="full_name"' in page) == (state == "open")
    if state == "not_yet":
        assert _text("reg.not_yet") + " 15 Oct 2026" in page
    # the button of the hero is there while registration is open
    home = _page(app, "/?lang=en")
    assert ('<a class="btn saffron" href="/register">' in home) == (state == "open")


# ---- the timeline on the schedule page -------------------------------------------------------------

def test_the_seed_file_has_the_wording_of_the_catalogue():
    from kts.admin import EVENT_KINDS
    from kts.i18n import CATALOG, TIMELINE_KEYS
    assert [s["key"] for s in SEEDS] == [name for name in ORDER if not name.endswith("*")]
    for s in SEEDS:
        assert s["title"] == CATALOG["en"]["timeline." + s["key"]]
        assert s["kind"] in EVENT_KINDS
        assert datetime.fromisoformat(s["starts"]) <= datetime.fromisoformat(s.get("ends", s["starts"]))
    assert [s["description"] for s in SEEDS if "description" in s] == [CATALOG["en"]["timeline.present_note"]]
    # no two rows share their wording, or the translation of one would be shown for the other
    assert len(TIMELINE_KEYS) == len(KEYS) + 1


def test_the_schedule_shows_the_timeline_in_order(monkeypatch):
    app = _portal()
    _on(monkeypatch, "2026-10-01")
    upcoming, past = _halves(_page(app, "/schedule?lang=en"))
    assert past == ""
    places = [upcoming.index("<bdi>" + _text(key) + "</bdi>") for key in KEYS]
    assert places == sorted(places)
    for day in ("07 Oct 2026", "15 Oct 2026", "21 Oct 2026", "23 Oct 2026", "– 24 Oct 2026", "25 Oct 2026", "26 Oct 2026",
                "05 Nov 2026", "06 Nov 2026", "07 Nov 2026", "12 Nov 2026", "13 Nov 2026", "– 16 Nov 2026", "15 Nov 2026", "20 Nov 2026",
                "28 Nov 2026", "12 Dec 2026"):
        assert day in upcoming, day
    # a day without a time of day stands alone; the test has the hours of its settings
    assert "12:00 AM" not in upcoming
    assert "22 Oct 2026, 11:00 AM" in upcoming and "– 22 Oct 2026, 12:00 PM" in upcoming
    assert _text("timeline.present_note") in upcoming
    # the evaluation is the work of CIIL
    row = upcoming[upcoming.index(_text("timeline.eval_start")):upcoming.index(_text("timeline.eval_end"))]
    assert "<bdi>CIIL</bdi>" in row


def test_what_is_over_moves_to_the_past(monkeypatch):
    app = _portal()
    _on(monkeypatch, "2026-10-24")
    upcoming, past = _halves(_page(app, "/schedule?lang=en"))
    for key in ("timeline.circular", "timeline.reg_open", "timeline.reg_close", "timeline.exam"):
        assert _text(key) in past and _text(key) not in upcoming, key
    # the selection takes two days and is not over on its second
    assert _text("timeline.selection") in upcoming and _text("timeline.selection") not in past
    _on(monkeypatch, "2026-10-25")
    upcoming, past = _halves(_page(app, "/schedule?lang=en"))
    assert _text("timeline.selection") in past and _text("timeline.letters") in upcoming
    # the last that is over stands first
    assert past.index(_text("timeline.selection")) < past.index(_text("timeline.exam")) < past.index(_text("timeline.circular"))


def test_the_home_page_shows_the_next_four_and_the_days_of_the_sangamam(monkeypatch):
    app = _portal()
    _on(monkeypatch, "2026-10-01")
    page = _page(app, "/?lang=en")
    assert '<span class="kicker"><bdi>28 Nov 2026 – 12 Dec 2026</bdi></span>' in page
    card = page[page.index("<h3>" + _text("schedule.upcoming") + "</h3>"):]
    card = card[:card.index("</ul>")]
    assert [key for key in KEYS if _text(key) in card] == KEYS[:4]
    assert "07 Oct 2026" in card and "12:00 AM" not in card
    _on(monkeypatch, "2026-12-13")
    page = _page(app, "/?lang=en")
    assert _text("common.none") in page[page.index("<h3>" + _text("schedule.upcoming") + "</h3>"):]


@pytest.mark.parametrize("lang", ["ta", "hi", "ur", "sat", "mni"])
def test_the_timeline_is_in_the_language_of_the_page(monkeypatch, lang):
    app = _portal()
    _on(monkeypatch, "2026-10-01")
    page = _page(app, f"/schedule?lang={lang}")
    for key in KEYS + ["timeline.present_note", "schedule.tentative"]:
        assert _text(key, lang) != _text(key), key
        assert _text(key, lang) in page, key
    assert _text("timeline.circular") not in page
    assert "07-10-2026" in page and "22-10-2026, 11:00" in page


def test_wording_entered_in_the_console_is_shown_as_it_is(monkeypatch):
    app = _portal()
    _on(monkeypatch, "2026-10-01")
    _sql(app, "UPDATE events SET title = 'Circular sent to all colleges' WHERE title = ?", (SEEDS[0]["title"],))
    for lang in ("en", "ta"):
        page = _page(app, f"/schedule?lang={lang}")
        assert "Circular sent to all colleges" in page
        assert _text("timeline.circular", lang) not in page


def test_an_event_hidden_in_the_console_leaves_the_schedule(monkeypatch):
    app = _portal()
    _on(monkeypatch, "2026-10-01")
    _sql(app, "UPDATE events SET published = 0 WHERE title = ?", (_plain("timeline.printed"),))
    page = _page(app, "/schedule?lang=en")
    assert _text("timeline.printed") not in page and _text("timeline.booklet") in page


def _plain(key):
    from kts.i18n import CATALOG
    return CATALOG["en"][key]


def test_the_five_dates_of_the_settings_stand_in_one_place_only(monkeypatch):
    app = _portal(**{"exam.date": "2026-10-25", "exam.start_time": "15:00", "exam.end_time": "16:30", "reg.end": "2026-10-18",
                     "kts.start": "2026-11-30"})
    _on(monkeypatch, "2026-10-01")
    titles = [row[0] for row in _sql(app, "SELECT title FROM events")]
    assert sorted(titles) == sorted(s["title"] for s in SEEDS)
    upcoming, _past = _halves(_page(app, "/schedule?lang=en"))
    assert "25 Oct 2026, 03:00 PM" in upcoming and "– 25 Oct 2026, 04:30 PM" in upcoming and "19 Oct 2026" not in upcoming
    assert "18 Oct 2026" in upcoming and "30 Nov 2026" in upcoming and "28 Nov 2026" not in upcoming
    # the test now comes after the selection of the seed file, and the page follows
    assert upcoming.index(_text("timeline.letters")) < upcoming.index(_text("timeline.exam")) < upcoming.index(_text("timeline.live"))


def test_a_date_that_cannot_be_read_leaves_its_row_out(monkeypatch):
    app = _portal(**{"kts.start": "", "kts.end": "soon", "exam.start_time": "eleven"})
    _on(monkeypatch, "2026-10-01")
    page = _page(app, "/schedule?lang=en")
    for key in ("timeline.inauguration", "timeline.valedictory", "timeline.exam"):
        assert _text(key) not in page, key
    assert _text("timeline.reg_open") in page
    home = _page(app, "/?lang=en")
    assert '<span class="kicker">' + _text("home.kicker") + "</span>" in home


def test_the_note_tentative_can_be_switched_off(monkeypatch):
    app = _portal()
    _on(monkeypatch, "2026-10-01")
    assert _text("schedule.tentative") in _page(app, "/schedule?lang=en")
    with app.app_context():
        from kts.db import set_setting
        set_setting("schedule.tentative", "0")
    assert _text("schedule.tentative") not in _page(app, "/schedule?lang=en")


def test_the_settings_page_offers_the_days_of_the_sangamam():
    from kts.admin import SETTING_GROUPS
    group = [items for title, items in SETTING_GROUPS if title == "Kashi Tamil Sangamam 5.0"]
    assert len(group) == 1
    # with the live stream of the inauguration and its attendance code (version 1.2.10)
    assert [(key, kind) for key, _label, kind in group[0]] == [("kts.start", "date"), ("kts.end", "date"), ("inaug.link", "text"),
                                                              ("inaug.code", "text"), ("schedule.tentative", "bool")]


# ---- the events are put in once ----------------------------------------------------------------------

def _titles(app):
    return [row[0] for row in _sql(app, "SELECT title FROM events ORDER BY starts_at, id")]


def test_a_new_installation_carries_the_timeline():
    app = make_app(ADMIN_PASSWORD=None)
    rows = _sql(app, "SELECT title, kind, starts_at, ends_at, published, description FROM events ORDER BY starts_at, id")
    assert [row[0] for row in rows] == [s["title"] for s in SEEDS]
    assert all(row[4] == 1 for row in rows)
    assert rows[0][2] == "2026-10-07T00:00" and rows[0][3] is None
    assert rows[1][2:4] == ("2026-10-23T00:00", "2026-10-24T00:00")


def test_the_timeline_is_put_in_once():
    app = make_app(ADMIN_PASSWORD=None)
    assert _titles(_start(_start(app))) == [s["title"] for s in SEEDS]


def test_a_deleted_event_does_not_come_back():
    app = make_app(ADMIN_PASSWORD=None)
    _sql(app, "DELETE FROM events WHERE title = ?", (SEEDS[0]["title"],))
    assert _titles(_start(app)) == [s["title"] for s in SEEDS[1:]]


def test_an_event_entered_by_hand_is_not_doubled():
    app = make_app(ADMIN_PASSWORD=None)
    _sql(app, "DELETE FROM events")
    _sql(app, "DELETE FROM settings WHERE key LIKE 'seed.event.%'")
    _sql(app, "INSERT INTO events(title, starts_at, created_at, updated_at) VALUES(?, '2026-11-06T10:30', '2026-10-01', '2026-10-01')",
         (SEEDS[5]["title"],))
    again = _start(app)
    assert sorted(_titles(again)) == sorted(s["title"] for s in SEEDS)
    assert _sql(again, "SELECT starts_at FROM events WHERE title = ?", (SEEDS[5]["title"],)) == [("2026-11-06T10:30",)]


def test_the_live_database_receives_the_timeline():
    # a database of version 1.1.4: no event, none of the marks
    app = make_app(ADMIN_PASSWORD=None)
    _sql(app, "DELETE FROM events")
    _sql(app, "DELETE FROM settings WHERE key LIKE 'seed.event.%'")
    assert _titles(_start(app)) == [s["title"] for s in SEEDS]


# ---- the banner -------------------------------------------------------------------------------------

def test_the_banner_does_not_announce_open_applications_before_the_first_day(monkeypatch):
    app = _portal()
    _on(monkeypatch, "2026-10-01")
    banner = _banner(_page(app, "/?lang=en"))
    assert _text("reg.not_yet") + " 15 Oct 2026" in banner and "are open" not in banner
    banner = _banner(_page(app, "/programme?lang=ta"))
    assert _text("reg.not_yet", "ta") in banner and "15-10-2026" in banner
    assert _text("set.banner", "ta") not in banner


def test_the_banner_announces_them_while_they_are_open(monkeypatch):
    app = _portal()
    _on(monkeypatch, "2026-10-15")
    assert _text("set.banner") in _banner(_page(app, "/?lang=en"))
    assert _text("set.banner", "hi") in _banner(_page(app, "/?lang=hi"))


def test_the_banner_says_so_when_registration_is_closed(monkeypatch):
    app = _portal()
    _on(monkeypatch, "2026-10-22")
    banner = _banner(_page(app, "/?lang=en"))
    assert _text("reg.closed") in banner and "are open" not in banner
    # also when the administrator has switched the registration off inside the dates
    app = _portal(**{"reg.open": "0"})
    _on(monkeypatch, "2026-10-17")
    assert _text("reg.closed") in _banner(_page(app, "/?lang=en"))


def test_wording_of_the_administrator_stands_in_the_banner_whatever_the_day(monkeypatch):
    app = _portal(**{"site.banner": "The helpdesk is closed on Sunday."})
    for day in ("2026-10-01", "2026-10-12", "2026-10-20"):
        _on(monkeypatch, day)
        assert "The helpdesk is closed on Sunday." in _banner(_page(app, "/?lang=ta"))


def test_no_banner_when_it_is_switched_off(monkeypatch):
    app = _portal(**{"site.banner_on": "0"})
    _on(monkeypatch, "2026-10-01")
    assert '<div class="banner">' not in _page(app, "/?lang=en")


# ---- a day without a time of day ------------------------------------------------------------------------

def test_the_day_alone_for_an_event_without_a_time():
    from kts.utils import fmt_when
    assert fmt_when("2026-10-07T00:00") == "07 Oct 2026"
    assert fmt_when("2026-10-07T00:00", numeric=True) == "07-10-2026"
    assert fmt_when("2026-10-19T11:00") == "19 Oct 2026, 11:00 AM"
    assert fmt_when("2026-10-19T11:00", numeric=True) == "19-10-2026, 11:00"
    assert fmt_when("2026-10-19") == "19 Oct 2026"
    assert fmt_when("") == "" and fmt_when(None) == "" and fmt_when("soon") == "soon"

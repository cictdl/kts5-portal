"""
The central online test from 10 to 20 November 2026 (version 1.2.120): open from 10 November 00:00 to 20 November 23:59
IST, at any time in these days, each attempt its 30 minutes and ending at the close at the latest; the days put in once
over the values of each database, which the Console may change afterwards; the pages name the days.

    python -m pytest tests -q
"""
from datetime import datetime, timedelta

from test_exam_modalities import _attempt, _ready, _signed_in
from test_timeline import _settings, _sql, _start


def _at(monkeypatch, moment):
    from kts import candidate, utils
    now = datetime.fromisoformat(moment).replace(tzinfo=utils.IST)
    monkeypatch.setattr(utils, "now_ist", lambda: now)
    monkeypatch.setattr(candidate, "now_ist", lambda: now)


def _days(app):
    """The window of the days of the test (the setting the tests start from forces it open)."""
    from kts.db import set_setting
    with app.app_context():
        set_setting("exam.open", "auto")


def test_the_days_and_their_window(monkeypatch):
    from kts.db import all_settings
    from kts.utils import exam_window
    app, _students = _ready()
    _days(app)
    with app.app_context():
        settings = all_settings()
    assert {k: settings[k] for k in ("exam.date", "exam.date_to", "exam.start_time", "exam.end_time", "exam.open", "exam.unverified")} == {
        "exam.date": "2026-11-10", "exam.date_to": "2026-11-20", "exam.start_time": "00:00", "exam.end_time": "23:59",
        "exam.open": "auto", "exam.unverified": "1"}
    for moment, is_open in (("2026-11-09T23:59", False), ("2026-11-10T00:00", True), ("2026-11-15T13:00", True),
                            ("2026-11-20T23:59", True), ("2026-11-21T00:00", False)):
        _at(monkeypatch, moment)
        assert exam_window(settings)[2] is is_open, moment
    # a last day before the first: the first day alone; none: the first day alone
    for last in ("2026-11-01", ""):
        start, end, _ = exam_window(dict(settings, **{"exam.date_to": last}))
        assert (start.isoformat(), end.isoformat()) == ("2026-11-10T00:00:00+05:30", "2026-11-10T23:59:00+05:30")


def test_a_student_takes_it_in_these_days(monkeypatch):
    from kts.db import execute
    from kts.utils import parse_iso
    app, students = _ready(2)
    _days(app)
    with app.app_context():
        execute("UPDATE applications SET status = 'submitted'")
    # not before the first day
    _at(monkeypatch, "2026-11-09T18:00")
    client, token = _signed_in(app, students[0])
    assert client.post("/candidate/exam", data={"_csrf": token}).headers["Location"].endswith("/candidate/")
    # any day in between: the whole 30 minutes
    _at(monkeypatch, "2026-11-15T13:00")
    assert client.post("/candidate/exam", data={"_csrf": token}).headers["Location"].endswith("/candidate/exam/paper")
    attempt = _attempt(app, students[0])
    assert parse_iso(attempt["deadline_at"]) - parse_iso(attempt["started_at"]) == timedelta(minutes=30)
    # late on the last day: only until the close
    _at(monkeypatch, "2026-11-20T23:45")
    other, t2 = _signed_in(app, students[1])
    assert other.post("/candidate/exam", data={"_csrf": t2}).headers["Location"].endswith("/candidate/exam/paper")
    assert parse_iso(_attempt(app, students[1])["deadline_at"]).strftime("%d %H:%M") == "20 23:59"


def test_the_pages_name_the_days(monkeypatch):
    app, students = _ready()
    _days(app)
    _at(monkeypatch, "2026-11-12T10:00")
    client, _token = _signed_in(app, students[0])
    page = client.get("/candidate/exam?lang=en").get_data(as_text=True)
    assert '<div class="val">10 Nov 2026 – 20 Nov 2026</div>' in page
    assert ("The test is open from 10 Nov 2026, 00:00 to 20 Nov 2026, 23:59 IST: take it at any time in these days. "
            "It lasts 30 minutes, and every attempt ends at 20 Nov 2026, 23:59 at the latest.") in page
    assert "Start at 00:00 to have the full" not in page
    assert "<dd><b>10 Nov 2026 – 20 Nov 2026</b></dd>" in client.get("/candidate/admit-card?lang=en").get_data(as_text=True)
    login = app.test_client().get("/candidate/login?lang=en").get_data(as_text=True)
    assert "<bdi>10 Nov 2026 – 20 Nov 2026 · 00:00–23:59 IST</bdi>" in login
    # in Tamil and Hindi, the note of the days
    from kts.i18n import CATALOG
    for code in ("ta", "hi"):
        page = client.get(f"/candidate/exam?lang={code}").get_data(as_text=True)
        before = CATALOG[code]["exam.days_note"].split("{from}")[0]
        assert before.strip() and before.strip() in page, code


def test_put_in_once_over_the_values_of_the_database():
    from kts.db import DEFAULT_SETTINGS, EXAM_DAYS
    app, _students = _ready()
    # a portal of before 1.2.120: one day, 11:30 to 12:00, the test closed
    for key, value in (("exam.date", "2026-10-29"), ("exam.start_time", "11:30"), ("exam.end_time", "12:00"), ("exam.open", "0")):
        _sql(app, "UPDATE settings SET value = ? WHERE key = ?", (value, key))
    _sql(app, "DELETE FROM settings WHERE key IN ('exam.date_to', 'migrate.exam_days')")
    again = _start(app)
    settings = _settings(again)
    assert {k: settings[k] for k in EXAM_DAYS} == {k: DEFAULT_SETTINGS[k] for k in EXAM_DAYS}
    # changed in the Console afterwards, they stay so
    _sql(again, "UPDATE settings SET value = '2026-11-25' WHERE key = 'exam.date_to'")
    _sql(again, "UPDATE settings SET value = '0' WHERE key = 'exam.open'")
    settings = _settings(_start(again))
    assert settings["exam.date_to"] == "2026-11-25" and settings["exam.open"] == "0"


def test_the_console_has_the_last_day():
    from kts.admin import SETTING_GROUPS
    fields = {key: label for _title, items in SETTING_GROUPS for key, label, _kind in items}
    assert fields["exam.date_to"].startswith("Last day of the test (YYYY-MM-DD; empty: the test date only)")
    assert any(title.startswith("The central online test of CICT") for title, _items in SETTING_GROUPS)

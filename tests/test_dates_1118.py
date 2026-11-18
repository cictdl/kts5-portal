"""
The registration of institutions up to 21 November 2026 and their selection on 22 November (1.2.203). CICT, 18 November 2026,
with the box of the key dates: "Registration and selection - Up to 21 Nov 2026 Last date for the registration of institutions -
22 Nov 2026 Selection of the Participating Institutions by the Nodal Institutions - change very carefully".

The two days were 18 and 19 November. A live database at those days takes the new ones at the next start: the two settings, the
two steps of the schedule, and the two notices that give the days in words, where their text is unchanged. What CICT set in the
Console stays. Nothing else moves: the assessment by 23 November, the nomination on 24 November, the verification up to
5 December; the notices of the letters of the Ministry and of AICTE keep the days those letters give.

    python -m pytest tests/test_dates_1118.py -q
"""
import re

from conftest import make_app
from test_timeline import S, _settings, _sql, _start

NEW = {"hei.end": "2026-11-21", "hei.select_end": "2026-11-22"}
OLD = {"hei.end": "2026-11-18", "hei.select_end": "2026-11-19"}
STAY = {"camp.to": "2026-11-23", "reg.end": "2026-11-24", "verify.end": "2026-12-05", "kts.start": "2026-11-28", "kts.end": "2026-12-12"}
OLD_DAYS = {"hei_reg": ("2026-11-18T00:00", None), "hei_select": ("2026-11-19T00:00", None)}
MARK = "migrate.dates_1118.notices"


def _before(app):
    """The live database as the release finds it: the two days of before in the settings, the schedule and the two notices."""
    from kts.db import LAUNCH_BODY_1202, LAUNCH_NOTICE, NODAL_DAYS, NODAL_DAYS_1202
    for key, value in OLD.items():
        _sql(app, "UPDATE settings SET value = ? WHERE key = ?", (value, key))
    for key, (starts, ends) in OLD_DAYS.items():
        _sql(app, "UPDATE events SET starts_at = ?, ends_at = ? WHERE title = ?", (starts, ends, S[key]["title"]))
    _sql(app, "UPDATE notices SET body = replace(body, ?, ?) WHERE category = 'circular'", (NODAL_DAYS, NODAL_DAYS_1202))
    _sql(app, "UPDATE notices SET body = ? WHERE title = ?", (LAUNCH_BODY_1202, LAUNCH_NOTICE[0]))
    _sql(app, "DELETE FROM settings WHERE key = ?", (MARK,))


def _main(client, path):
    page = client.get(path + "?lang=en").get_data(as_text=True)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page[page.index("<main"):page.index("</main>")]))


def test_the_two_days():
    from kts.db import DEFAULT_SETTINGS, RETIRED_DEFAULTS, RETIRED_EVENT_DAYS
    assert {k: DEFAULT_SETTINGS[k] for k in NEW} == NEW
    assert {k: DEFAULT_SETTINGS[k] for k in STAY} == STAY                   # nothing else moves
    for key, old in OLD.items():
        assert old in RETIRED_DEFAULTS[key] and NEW[key] not in RETIRED_DEFAULTS[key], key
    # the schedule, in the order of its days: registration, selection, assessment, the consolidation and verification
    assert (S["hei_reg"]["starts"], S["hei_reg"].get("ends"), S["hei_select"]["starts"], S["hei_select"].get("ends")) == (
        "2026-11-21", None, "2026-11-22", None)
    assert (S["assess"]["starts"], S["selection"]["starts"], S["selection"]["ends"]) == ("2026-11-23", "2026-11-25", "2026-12-05")
    assert S["hei_reg"]["starts"] < S["hei_select"]["starts"] < S["assess"]["starts"] < S["selection"]["starts"]
    assert OLD_DAYS["hei_reg"] in RETIRED_EVENT_DAYS["hei_reg"] and OLD_DAYS["hei_select"] in RETIRED_EVENT_DAYS["hei_select"]


def test_the_pages_give_the_two_days():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    home = _main(client, "/")
    assert "Registration and selection Up to 21 Nov 2026 Last date for the registration of institutions 22 Nov 2026 Selection of the Participating Institutions by the Nodal Institutions" in home
    # (the home page also gives the day itself, with the Kural of the day: only the days of the two steps are looked for)
    assert "By 23 Nov 2026" in home and "Up to 18 Nov 2026" not in home and "19 Nov 2026 Selection" not in home
    schedule = _main(client, "/schedule")
    assert "21 Nov 2026 Last date for the registration of institutions; wide outreach by the Nodal Institutions" in schedule
    assert "22 Nov 2026 Scrutiny and selection of the Participating Institutions by the Nodal Institutions" in schedule
    assert schedule.index("21 Nov 2026 Last date for the registration") < schedule.index("22 Nov 2026 Scrutiny") < schedule.index("23 Nov 2026 Last date for the assessment")
    assert "18 Nov 2026 Last date for the registration" not in schedule and "19 Nov 2026 Scrutiny" not in schedule
    assert "Up to 18 Nov 2026" not in schedule and "19 Nov 2026 Selection" not in schedule
    guide = _main(client, "/how-to-take-part")
    assert "Last date for institutions to register 21 Nov 2026 Selection of the Participating Institutions by the Nodal Institutions 22 Nov 2026" in guide
    assert "Register your institution by 21 Nov 2026" in guide and "By 23 Nov 2026" in guide
    assert "register 18 Nov 2026" not in guide and "Institutions 19 Nov 2026" not in guide and "by 18 Nov 2026" not in guide


def test_the_registration_of_institutions_is_open_up_to_21_november(monkeypatch):
    from datetime import datetime
    from kts import heis as HEI
    from kts.db import all_settings
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        settings = all_settings()
        for day, state in (("2026-11-18", "open"), ("2026-11-19", "open"), ("2026-11-21", "open"), ("2026-11-22", "ended")):
            monkeypatch.setattr(HEI, "now_ist", lambda day=day: datetime.fromisoformat(day + "T23:59:00+05:30"))
            assert HEI.window(settings) == state, day


def test_a_live_database_takes_the_two_days_once():
    from kts.db import LAUNCH_BODY_1202, LAUNCH_NOTICE, NODAL_DAYS, NODAL_DAYS_1202
    app = make_app(ADMIN_PASSWORD=None)
    _before(app)
    again = _start(app)
    settings = _settings(again)
    assert {k: settings[k] for k in NEW} == NEW and {k: settings[k] for k in STAY if k not in ("reg.end",)} == {
        k: v for k, v in STAY.items() if k != "reg.end"}
    rows = {t: (s, e) for t, s, e in _sql(again, "SELECT title, starts_at, ends_at FROM events")}
    assert rows[S["hei_reg"]["title"]] == ("2026-11-21T00:00", None) and rows[S["hei_select"]["title"]] == ("2026-11-22T00:00", None)
    assert rows[S["assess"]["title"]] == ("2026-11-23T00:00", None) and rows[S["selection"]["title"]] == ("2026-11-25T00:00", "2026-12-05T00:00")
    bodies = "\n".join(n[0] for n in _sql(again, "SELECT body FROM notices WHERE published = 1"))
    assert NODAL_DAYS in bodies and NODAL_DAYS_1202 not in bodies
    assert LAUNCH_NOTICE[1] in bodies and LAUNCH_BODY_1202 not in bodies
    assert "up to 21 November 2026" in NODAL_DAYS and "on 22 November 2026" in NODAL_DAYS
    assert "kts.cict.in up to 21 November 2026; the Nodal Institutions select the Participating Institutions on 22 November" in LAUNCH_NOTICE[1]
    # the notices of the letters keep the days of the letters
    assert "up to 18 November 2026 (earlier 15 November)" in bodies
    # once: a notice that CICT words anew afterwards stays as CICT words it
    _sql(again, "UPDATE notices SET body = ? WHERE title = ?", ("As CICT words it.", LAUNCH_NOTICE[0]))
    third = _start(again)
    assert _sql(third, "SELECT body FROM notices WHERE title = ?", (LAUNCH_NOTICE[0],))[0][0] == "As CICT words it."


def test_what_cict_set_in_the_console_stays():
    from kts.db import LAUNCH_NOTICE
    app = make_app(ADMIN_PASSWORD=None)
    _before(app)
    # another last date of registration set in the Console, the step of the selection moved by hand, the notice of the launch
    # worded anew
    _sql(app, "UPDATE settings SET value = '2026-11-25' WHERE key = 'hei.end'")
    _sql(app, "UPDATE events SET starts_at = '2026-11-20T00:00' WHERE title = ?", (S["hei_select"]["title"],))
    _sql(app, "UPDATE notices SET body = 'The launch, in the words of CICT.' WHERE title = ?", (LAUNCH_NOTICE[0],))
    again = _start(app)
    settings = _settings(again)
    assert (settings["hei.end"], settings["hei.select_end"]) == ("2026-11-25", "2026-11-22")
    rows = {t: (s, e) for t, s, e in _sql(again, "SELECT title, starts_at, ends_at FROM events")}
    assert rows[S["hei_reg"]["title"]] == ("2026-11-21T00:00", None) and rows[S["hei_select"]["title"]] == ("2026-11-20T00:00", None)
    assert _sql(again, "SELECT body FROM notices WHERE title = ?", (LAUNCH_NOTICE[0],))[0][0] == "The launch, in the words of CICT."

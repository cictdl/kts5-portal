"""
The last date for the registration of institutions moves from 15 to 18 November 2026 (1.2.171; CICT, 10 November 2026:
"Register your institution -> Last date: 18 Nov 2026", only the registration moves). The selection by the Nodal Institutions
(16-17 November), the assessment (19 November) and the nomination (20 November) stay; so does the notice that quotes the D.O.
letter of 31 October. A live database still at 15 November takes the 18th at the next start, the setting and the step of the
schedule alike; a date CICT set in the Console stays.

    python -m pytest tests/test_hei_end_1110.py -q
"""
import re

from conftest import make_app
from test_timeline import S, _settings, _sql, _start


def test_the_dates():
    from kts.db import DEFAULT_SETTINGS
    # 21 November since 1.2.203 (CICT, 18 November 2026; tests/test_dates_1118.py), and the selection on 22 November
    # ... 27 November since 1.2.209 (CICT, 22 November 2026; tests/test_dates_hidden_1122.py), the setting and the step alike
    assert DEFAULT_SETTINGS["hei.end"] == "2026-11-27" and S["hei_reg"]["starts"] == "2026-11-27"
    # the selection, the assessment and the nomination as the Ministry moved them on 10 November too (1.2.172)
    # ... the assessment and the nomination up to 27 November as well since 1.2.209 (23 and 24 November before)
    assert (DEFAULT_SETTINGS["hei.select_end"], DEFAULT_SETTINGS["camp.to"], DEFAULT_SETTINGS["reg.end"]) == (
        "2026-11-22", "2026-11-27", "2026-11-27")
    assert (S["hei_select"]["starts"], S["hei_select"].get("ends"), S["assess"]["starts"]) == ("2026-11-22", None, "2026-11-27")


def test_a_live_database_at_15_november_takes_the_18th_once():
    app = make_app(ADMIN_PASSWORD=None)
    title = S["hei_reg"]["title"]
    _sql(app, "UPDATE settings SET value = '2026-11-15' WHERE key = 'hei.end'")
    _sql(app, "UPDATE events SET starts_at = '2026-11-15T00:00', ends_at = NULL WHERE title = ?", (title,))
    again = _start(app)
    assert _settings(again)["hei.end"] == "2026-11-27"      # the day of now (1.2.209; 21 November by 1.2.203)
    assert _sql(again, "SELECT starts_at, ends_at FROM events WHERE title = ?", (title,)) == [("2026-11-27T00:00", None)]
    # a date set by CICT in the Console, the setting or the step, stays
    _sql(again, "UPDATE settings SET value = '2026-11-16' WHERE key = 'hei.end'")
    _sql(again, "UPDATE events SET starts_at = '2026-11-16T00:00' WHERE title = ?", (title,))
    third = _start(again)
    assert _settings(third)["hei.end"] == "2026-11-16"
    assert _sql(third, "SELECT starts_at FROM events WHERE title = ?", (title,)) == [("2026-11-16T00:00",)]


def test_the_strip_and_the_schedule(monkeypatch):
    from kts import heis as HEI, utils
    from kts.db import set_setting
    from test_timeline import _on
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():   # as on the live site: the students do not register, the institutions do
        for key, value in {"reg.open": "0", "launch.on": "0", "hei.open": "1", "hei.start": "2026-10-22"}.items():
            set_setting(key, value)
    _on(monkeypatch, "2026-11-12")
    # ... and the clock of the registration of institutions, which kts.heis keeps for itself: the strip gives the last date while
    # that registration is open, and in the tests' portal it closed on 21 November 2026 (conftest, the day of 1.2.208; 1.2.209)
    monkeypatch.setattr(HEI, "now_ist", utils.now_ist)
    client = app.test_client()
    home = client.get("/?lang=en").get_data(as_text=True)
    assert re.search(r'<span class="banner-date">Last date: <bdi>(<bdi dir="ltr">)?21 Nov 2026', home)
    assert "15 Nov 2026" not in home
    schedule = client.get("/schedule?lang=en").get_data(as_text=True)
    at = schedule.index(S["hei_reg"]["title"])
    row = schedule[schedule.rindex("<tr>", 0, at):at]
    # the step of the schedule has the day of data/timeline.json: 27 November 2026 since 1.2.209 (21 November before)
    assert "27 Nov 2026" in row and "15 Nov 2026" not in row and "21 Nov 2026" not in row
    # the selection by the Nodal Institutions follows it (19 November since 1.2.172)
    # ... it stands before it since 1.2.209, the steps being in the order of their days (22 November, then 27 November); the
    # assessment, up to 27 November too, comes after the registration as before
    assert schedule.index(S["hei_select"]["title"]) < at < schedule.index(S["assess"]["title"])


def test_the_selection_keeps_its_days():
    """The Key dates box and the hub of the home page: registration up to 18 November, selection 16-17 November as the
    schedule has it (not the day after the registration, which would be after the selection)."""
    import re as _re
    from kts import finder
    from kts.db import all_settings
    app = make_app(ADMIN_PASSWORD=None)
    page = app.test_client().get("/schedule?lang=en").get_data(as_text=True)
    box = page[page.index('<div class="kd-box">'):]
    text = _re.sub(r"<[^>]+>", "|", box[:6000])
    assert "|Up to 21 Nov 2026|" in text and "|22 Nov 2026|" in text and "|By 23 Nov 2026|" in text   # 1.2.172
    with app.test_request_context():
        words = finder.hub(all_settings(), "en")["words"]
        assert words["select"] == "22 November 2026" and words["hei_end"] == "21 November 2026"

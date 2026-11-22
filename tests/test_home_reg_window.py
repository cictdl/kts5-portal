"""
While registration is switched off with the postponed launch (1.2.69), the pages say that registration opens after the
launch of the portal, in place of its dates: the Registration window tile and the Register step of the home page, the
schedule, the programme and the register page (1.2.76). Registration is called closed only once its last day has
passed (1.2.75); open, it shows its dates.

    python -m pytest tests -q
"""
from markupsafe import escape

from test_launch import _app, _at, _clock as _launch_clock

AFTER = "Opens after the launch of the portal"
# the window of the registration as the pages write it: to 27 November 2026 since 1.2.209 (CICT, 22 November 2026; "22 Oct 2026 –
# 24 Nov 2026" up to 1.2.208)
WINDOW = "22 Oct 2026 – 27 Nov 2026"
NOTE = "Registration is now open for Participating Institutions."   # since 1.2.147 ("Registration will open after the launch of the portal. The date is yet to be announced." before)


def _clock(monkeypatch, now):
    """The clock of the portal at this moment, for the registration of institutions too (kts.heis): the banner of the pages asks
    whether that registration is open (heis.window), and its last day in the database of the tests, 21 November 2026
    (tests/conftest.py, 1.2.209), is past by the clock of the machine."""
    from kts import heis
    _launch_clock(monkeypatch, now)
    monkeypatch.setattr(heis, "now_ist", lambda: now)


def _tile(page):
    # alone under the key dates since 1.2.152: up to the end of its section (home) or the next heading (schedule)
    start = page.index('<div class="lbl">Registration window</div>')
    return page[start:min(i for i in (page.find("</section>", start), page.find("<h2", start)) if i > 0)]


def test_registration_opens_after_the_launch(monkeypatch):
    app = _app(**{"launch.on": "0"})
    with app.app_context():   # the students' registration shown (hidden by default since 1.2.147)
        from kts.db import set_setting as _set
        _set("reg.public", "1")
    with app.app_context():
        from kts.db import set_setting
        set_setting("reg.open", "0")
    _clock(monkeypatch, _at(22, 17))
    client = app.test_client()
    home = client.get("/?lang=en").get_data(as_text=True)
    tile = _tile(home)
    assert AFTER in tile and "pill" not in tile
    assert WINDOW not in home and home.count(AFTER) == 2      # the tile and the Register step
    schedule = client.get("/schedule?lang=en").get_data(as_text=True)
    assert AFTER in schedule and WINDOW not in schedule
    assert f"Registration window: {AFTER}" in client.get("/programme?lang=en").get_data(as_text=True)
    register = client.get("/register?lang=en").get_data(as_text=True)
    assert NOTE in register and "Registration is closed." not in register and "Registrations closed on" not in register
    # in every language
    from kts.i18n import CATALOG
    for code, catalogue in CATALOG.items():
        assert str(escape(catalogue["reg.after_launch"])) in client.get(f"/?lang={code}").get_data(as_text=True), code
        assert str(escape(catalogue["reg.after_launch_note"])) in client.get(f"/register?lang={code}").get_data(as_text=True), code
    # on the last day too: 27 November 2026 since 1.2.209 (24 November up to 1.2.208)
    _clock(monkeypatch, _at(27, 23, 59, month=11))
    assert AFTER in _tile(app.test_client().get("/?lang=en").get_data(as_text=True))
    # once it has passed, registration is closed, with its dates
    _clock(monkeypatch, _at(28, 0, 1, month=11))
    tile = _tile(app.test_client().get("/?lang=en").get_data(as_text=True))
    assert WINDOW in tile and "Registration is closed." in tile and AFTER not in tile


def test_the_dates_while_registration_is_open_or_after_the_launch(monkeypatch):
    app = _app(**{"launch.on": "0"})
    with app.app_context():   # the students' registration shown (hidden by default since 1.2.147)
        from kts.db import set_setting as _set
        _set("reg.public", "1")
    _clock(monkeypatch, _at(23, 10))
    home = app.test_client().get("/?lang=en").get_data(as_text=True)
    tile = _tile(home)
    assert '<span class="pill green">' in tile and WINDOW in tile and AFTER not in home
    # switched off by CICT once the launch is on again: its dates, and not "after the launch"
    with app.app_context():
        from kts.db import set_setting
        set_setting("launch.on", "1")
        set_setting("reg.open", "0")
    tile = _tile(app.test_client().get("/?lang=en").get_data(as_text=True))
    assert WINDOW in tile and AFTER not in tile and "Registration is closed." not in tile

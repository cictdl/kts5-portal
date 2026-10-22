"""
While registration is switched off with the postponed launch (1.2.69), the pages say that registration opens after the
launch of the portal, in place of its dates: the Registration window tile and the Register step of the home page, the
schedule, the programme and the register page (1.2.76). Registration is called closed only once its last day has
passed (1.2.75); open, it shows its dates.

    python -m pytest tests -q
"""
from markupsafe import escape

from test_launch import _app, _at, _clock

AFTER = "Opens after the launch of the portal"
NOTE = "Registration will open after the launch of the portal. The date is yet to be announced."


def _tile(page):
    start = page.index('<div class="lbl">Registration window</div>')
    return page[start:page.index('<div class="date-tile">', start)]


def test_registration_opens_after_the_launch(monkeypatch):
    app = _app(**{"launch.on": "0"})
    with app.app_context():
        from kts.db import set_setting
        set_setting("reg.open", "0")
    _clock(monkeypatch, _at(22, 17))
    client = app.test_client()
    home = client.get("/?lang=en").get_data(as_text=True)
    tile = _tile(home)
    assert AFTER in tile and "pill" not in tile
    assert "22 Oct 2026 – 29 Oct 2026" not in home and home.count(AFTER) == 2      # the tile and the Register step
    schedule = client.get("/schedule?lang=en").get_data(as_text=True)
    assert AFTER in schedule and "22 Oct 2026 – 29 Oct 2026" not in schedule
    assert f"Registration window: {AFTER}" in client.get("/programme?lang=en").get_data(as_text=True)
    register = client.get("/register?lang=en").get_data(as_text=True)
    assert NOTE in register and "Registration is closed." not in register and "Registrations closed on" not in register
    # in every language
    from kts.i18n import CATALOG
    for code, catalogue in CATALOG.items():
        assert str(escape(catalogue["reg.after_launch"])) in client.get(f"/?lang={code}").get_data(as_text=True), code
        assert str(escape(catalogue["reg.after_launch_note"])) in client.get(f"/register?lang={code}").get_data(as_text=True), code
    # on the last day too
    _clock(monkeypatch, _at(29, 23, 59))
    assert AFTER in _tile(app.test_client().get("/?lang=en").get_data(as_text=True))
    # once it has passed, registration is closed, with its dates
    _clock(monkeypatch, _at(30, 0, 1))
    tile = _tile(app.test_client().get("/?lang=en").get_data(as_text=True))
    assert "22 Oct 2026 – 29 Oct 2026" in tile and "Registration is closed." in tile and AFTER not in tile


def test_the_dates_while_registration_is_open_or_after_the_launch(monkeypatch):
    app = _app(**{"launch.on": "0"})
    _clock(monkeypatch, _at(23, 10))
    home = app.test_client().get("/?lang=en").get_data(as_text=True)
    tile = _tile(home)
    assert '<span class="pill green">' in tile and "22 Oct 2026 – 29 Oct 2026" in tile and AFTER not in home
    # switched off by CICT once the launch is on again: its dates, and not "after the launch"
    with app.app_context():
        from kts.db import set_setting
        set_setting("launch.on", "1")
        set_setting("reg.open", "0")
    tile = _tile(app.test_client().get("/?lang=en").get_data(as_text=True))
    assert "22 Oct 2026 – 29 Oct 2026" in tile and AFTER not in tile and "Registration is closed." not in tile

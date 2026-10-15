"""
The home page names the registration window, 14 Oct 2026 – 22 Oct 2026, and calls registration closed only once its
last day has passed: switched off before it, as while the launch is postponed, the tile shows the window alone
(version 1.2.75).

    python -m pytest tests -q
"""
from test_launch import _app, _at, _clock


def _tile(page):
    start = page.index('<div class="lbl">Registration window</div>')
    return page[start:page.index('<div class="date-tile">', start)]


def test_the_window_alone_while_registration_is_switched_off(monkeypatch):
    app = _app(**{"launch.on": "0"})
    with app.app_context():
        from kts.db import set_setting
        set_setting("reg.open", "0")
    _clock(monkeypatch, _at(15, 17))
    tile = _tile(app.test_client().get("/?lang=en").get_data(as_text=True))
    assert "14 Oct 2026 – 22 Oct 2026" in tile and "Registration is closed." not in tile and "pill" not in tile
    # on the last day too
    _clock(monkeypatch, _at(22, 23, 59))
    assert "Registration is closed." not in _tile(app.test_client().get("/?lang=en").get_data(as_text=True))
    # and once it has passed, registration is closed
    _clock(monkeypatch, _at(23, 0, 1))
    tile = _tile(app.test_client().get("/?lang=en").get_data(as_text=True))
    assert "14 Oct 2026 – 22 Oct 2026" in tile and "Registration is closed." in tile


def test_open_registration_is_still_called_open(monkeypatch):
    app = _app(**{"launch.on": "0"})
    _clock(monkeypatch, _at(16, 10))
    tile = _tile(app.test_client().get("/?lang=en").get_data(as_text=True))
    assert '<span class="pill green">' in tile and "Registration is closed." not in tile

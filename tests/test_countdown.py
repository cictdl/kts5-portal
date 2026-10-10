"""
The countdown to Kashi Tamil Sangamam 5.0 on the home page (version 1.2.50): days, hours, minutes and
seconds to kts.start at kts.start_time (IST) before it, "under way" from then to the end of the day of
kts.end, nothing after it.

    python -m pytest tests -q
"""
from datetime import datetime

from conftest import ROOT, make_app
from test_public_fixes import _staff


def _at(month, day, hour=0, minute=0):
    from kts.utils import IST
    return datetime(2026, month, day, hour, minute, tzinfo=IST)


def _home(app, monkeypatch, now, lang="en"):
    from kts import public
    monkeypatch.setattr(public, "now_ist", lambda: now)
    return app.test_client().get(f"/?lang={lang}").get_data(as_text=True)


def test_the_moment_and_the_phases():
    from kts.db import DEFAULT_SETTINGS
    from kts.public import kts_at, kts_phase
    s = dict(DEFAULT_SETTINGS)
    assert s["kts.start"] == "2026-11-28" and s["kts.end"] == "2026-12-12" and s["kts.start_time"] == ""
    assert kts_at(s).isoformat() == "2026-11-28T00:00:00+05:30"
    assert kts_phase(s, _at(10, 10)) == "before" and kts_phase(s, _at(11, 27, 23, 59)) == "before"
    assert kts_phase(s, _at(11, 28)) == "during" and kts_phase(s, _at(12, 12, 23, 59)) == "during"
    assert kts_phase(s, _at(12, 13)) is None
    s["kts.start_time"] = "10:30"
    assert kts_at(s).isoformat() == "2026-11-28T10:30:00+05:30" and kts_phase(s, _at(11, 28, 10, 29)) == "before"
    for wrong in ("25:00", "10.30", "10:3", "ten"):
        s["kts.start_time"] = wrong
        assert kts_at(s).isoformat() == "2026-11-28T00:00:00+05:30"
    s["kts.start"] = ""
    assert kts_at(s) is None and kts_phase(s, _at(10, 10)) is None
    # without a valedictory day, the first day only
    s.update({"kts.start": "2026-11-28", "kts.end": "", "kts.start_time": ""})
    assert kts_phase(s, _at(11, 28, 20)) == "during" and kts_phase(s, _at(11, 29)) is None


def test_the_home_page_counts_down_then_says_under_way(monkeypatch):
    app = make_app(ADMIN_PASSWORD=None)
    page = _home(app, monkeypatch, _at(10, 10))
    assert 'class="kts-countdown" data-countdown="2026-11-28T00:00:00+05:30" data-done="Kashi Tamil Sangamam 5.0 is under way"' in page
    assert "Kashi Tamil Sangamam 5.0 begins in</span>" in page and 'data-cd-label' in page
    for unit in ('<b data-u="d">', '<b data-u="h">', '<b data-u="m">', '<b data-u="s">', "<span>days</span>", "<span>seconds</span>"):
        assert unit in page
    # in the hero, under the dates of the Sangamam
    assert page.index("28 Nov 2026") < page.index("kts-countdown") < page.index("<h1>")
    tamil = _home(app, monkeypatch, _at(10, 10), "ta")
    assert "காசி தமிழ்ச் சங்கமம் 5.0 தொடங்க இன்னும்" in tamil and "<span>நாள்கள்</span>" in tamil
    urdu = _home(app, monkeypatch, _at(10, 10), "ur")
    assert 'class="units" dir="ltr"' in urdu and "کاشی تمل سنگمم 5.0 شروع ہونے میں" in urdu
    during = _home(app, monkeypatch, _at(12, 1))
    assert '<div class="kts-countdown live"><span class="cd-label">Kashi Tamil Sangamam 5.0 is under way</span></div>' in during
    assert "data-countdown" not in during
    after = _home(app, monkeypatch, _at(12, 13))
    assert "kts-countdown" not in after and "is under way" not in after


def test_the_hour_of_the_inauguration_is_a_setting(monkeypatch):
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    admin = _staff(app, "cd-admin@tests.example", role="admin")
    assert 'name="kts.start_time"' in admin.get("/console/settings").get_data(as_text=True)
    with app.app_context():
        set_setting("kts.start_time", "10:30")
    assert 'data-countdown="2026-11-28T10:30:00+05:30"' in _home(app, monkeypatch, _at(11, 28, 9))
    assert "kts-countdown live" in _home(app, monkeypatch, _at(11, 28, 10, 30))


def test_the_script_writes_the_text_when_the_moment_comes():
    js = (ROOT / "static" / "js" / "portal.js").read_text(encoding="utf-8")
    assert "[data-cd-label]" in js and "label.textContent = el.dataset.done" in js
    # the text of the translation is never put in as HTML
    assert 'innerHTML = "<b>" + el.dataset.done' not in js
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    assert ".kts-countdown .unit b" in css and ".kts-countdown.live .cd-label" in css

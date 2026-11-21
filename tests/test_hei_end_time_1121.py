"""
The registration of institutions closes at 5:00 PM of its last day (1.2.208). CICT, 21 November 2026, with the row of the Key
dates "Up to 21 Nov 2026 - Last date for the registration of institutions": "5 pm is the deadline. change".

    python -m pytest tests/test_hei_end_time_1121.py -q
"""
import re
from datetime import datetime

import pytest

from conftest import make_app
from test_timeline import _sql, _start


@pytest.fixture(autouse=True)
def empty_limiter():
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def _portal(**settings):
    """The portal as the live one is set: the registration of institutions up to 21 November 2026, 5:00 PM."""
    from kts.db import DEFAULT_SETTINGS, set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for key, value in {"hei.open": "1", "hei.end": DEFAULT_SETTINGS["hei.end"], "hei.end_time": DEFAULT_SETTINGS["hei.end_time"],
                           "kd.select_rows": "0", **settings}.items():
            set_setting(key, value)
    return app


def _at(monkeypatch, moment):
    from kts import heis as HEI
    monkeypatch.setattr(HEI, "now_ist", lambda: datetime.fromisoformat(moment + "+05:30"))


def _main(client, path):
    page = client.get(path).get_data(as_text=True)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page[page.index("<main"):page.index("</main>")])), page


def test_the_setting():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS
    assert (DEFAULT_SETTINGS["hei.end"], DEFAULT_SETTINGS["hei.end_time"]) == ("2026-11-21", "17:00")
    rows = {k: (label, kind) for _g, items in SETTING_GROUPS for k, label, kind in items}
    assert rows["hei.end_time"] == ("Hour of that day at which the registration of institutions closes (HH:MM, IST; empty: at the end of the "
                                    "day)", "time")


def test_the_registration_closes_at_5_pm(monkeypatch):
    from kts import heis as HEI
    from kts.db import all_settings
    app = _portal()
    with app.app_context():
        settings = all_settings()
    for moment, state in (("2026-11-20T23:59:00", "open"), ("2026-11-21T09:00:00", "open"), ("2026-11-21T16:59:59", "open"),
                          ("2026-11-21T17:00:00", "ended"), ("2026-11-21T17:01:00", "ended"), ("2026-11-22T10:00:00", "ended")):
        _at(monkeypatch, moment)
        assert HEI.window(settings) == state, moment
    # without an hour, the whole day, as before
    settings["hei.end_time"] = ""
    _at(monkeypatch, "2026-11-21T23:59:00")
    assert HEI.window(settings) == "open"
    for odd in ("5 pm", "25:00", "17:60"):
        settings["hei.end_time"] = odd
        assert HEI.end_hour(settings) is None, odd
    settings["hei.end_time"] = "9.30"
    assert str(HEI.end_hour(settings)) == "09:30:00" and HEI.hour_words(settings, "en") == ", 9:30 AM" and HEI.hour_words(settings, "hi") == ", 09:30"


def test_the_form_of_the_registration_before_and_after_5_pm(monkeypatch):
    app = _portal()
    client = app.test_client()
    _at(monkeypatch, "2026-11-21T16:30:00")
    text, page = _main(client, "/institutions/register?lang=en")
    assert 'name="head_name"' in page and "Last date for institutions: 21 Nov 2026, 5:00 PM" in text
    _at(monkeypatch, "2026-11-21T17:00:00")
    text, page = _main(client, "/institutions/register?lang=en")
    assert 'name="head_name"' not in page and "Applications of institutions closed on 21 Nov 2026, 5:00 PM." in text
    # an application sent after the hour is not taken
    from test_institutions import FORM
    with client.session_transaction() as s:
        token = s["_csrf"]
        s["_captcha"] = "7"
    r = client.post("/institutions/register", data=dict(FORM, _csrf=token, captcha="7"))
    assert r.status_code == 200 and "Applications of institutions closed on" in r.get_data(as_text=True)
    assert _sql(app, "SELECT COUNT(*) FROM institutions") == [(0,)]


def test_the_pages_give_the_hour(monkeypatch):
    app = _portal(**{"reg.open": "0", "launch.on": "0", "hei.start": "2026-10-22"})      # the banner as on the live site
    _at(monkeypatch, "2026-11-21T10:00:00")
    client = app.test_client()
    home, page = _main(client, "/?lang=en")
    assert "Registration Up to 21 Nov 2026, 5:00 PM Last date for the registration of institutions" in home
    assert re.search(r'<li class="kd-blink"><span class="kd-when"><bdi>Up to 21 Nov 2026, 5:00 PM</bdi></span>', page)
    assert re.search(r'<span class="banner-date">Last date: <bdi>(<bdi dir="ltr">)?21 Nov 2026, 5:00 PM', page)
    schedule, _p = _main(client, "/schedule?lang=en")
    assert "Up to 21 Nov 2026, 5:00 PM Last date for the registration of institutions" in schedule
    guide, _p = _main(client, "/how-to-take-part?lang=en")
    assert "Last date for institutions to register 21 Nov 2026, 5:00 PM" in guide and "Register your institution by 21 Nov 2026, 5:00 PM" in guide
    institutions, _p = _main(client, "/institutions?lang=en")
    assert "Last date for institutions: 21 Nov 2026, 5:00 PM" in institutions
    helps, _p = _main(client, "/help?lang=en")
    assert "by 21 Nov 2026, 5:00 PM" in helps
    # in the other languages, as the portal writes days and hours in them
    hindi, page = _main(client, "/?lang=hi")
    assert "21-11-2026, 17:00" in page
    urdu = client.get("/?lang=ur").get_data(as_text=True)
    assert "⁦21-11-2026, 17:00⁩" in urdu
    # the hub of the home page and the State/UT pages
    from kts import finder
    from kts.db import all_settings
    with app.test_request_context():
        assert finder.hub(all_settings(), "en")["words"]["hei_end"] == "21 November 2026, 5:00 PM"
        assert finder.hub(all_settings(), "hi")["words"]["hei_end"].endswith(", 17:00")


def test_the_mail_of_the_nodal_officers():
    from kts import nodal
    from kts.db import query
    from test_nodal_signin import _account
    app = _portal()
    uid = _account(app, "new.kerala@tests.example", ["Kerala"])
    with app.app_context():
        _subject, body = nodal.signin_mail(query("SELECT * FROM users WHERE id = ?", (uid,), one=True))
    assert "register on the portal up to 21 November 2026, 5:00 PM:" in body


def test_the_notice_of_the_extension_takes_the_hour_once():
    from kts.db import EXT21_BODY_1207, EXT21_NOTICE
    assert "from 18 November 2026 to 21 November 2026, 5:00 PM." in EXT21_NOTICE[1]
    assert "• Registration of institutions on kts.cict.in: up to 21 November 2026, 5:00 PM (earlier 18 November)." in EXT21_NOTICE[1]
    assert "5:00 PM" not in EXT21_BODY_1207 and "from 18 November 2026 to 21 November 2026." in EXT21_BODY_1207
    app = make_app(ADMIN_PASSWORD=None)
    # the live database: the notice as 1.2.204 put it
    _sql(app, "UPDATE notices SET body = ? WHERE title = ?", (EXT21_BODY_1207, EXT21_NOTICE[0]))
    _sql(app, "DELETE FROM settings WHERE key = 'migrate.ext21_hour_1121'")
    again = _start(app)
    assert _sql(again, "SELECT body FROM notices WHERE title = ?", (EXT21_NOTICE[0],)) == [(EXT21_NOTICE[1],)]
    # once: as CICT words it afterwards, it stays
    _sql(again, "UPDATE notices SET body = 'In the words of CICT.' WHERE title = ?", (EXT21_NOTICE[0],))
    third = _start(again)
    assert _sql(third, "SELECT body FROM notices WHERE title = ?", (EXT21_NOTICE[0],)) == [("In the words of CICT.",)]

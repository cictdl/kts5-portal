"""
The count of visitors (version 1.2.31): one browser on one day is one visitor, robots and the pages of
the staff are not counted, and nothing of who they were is kept.

    python -m pytest tests -q
"""
import re
from datetime import datetime, timedelta

from conftest import make_app
from test_public_fixes import _staff

FIREFOX = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0"
PHONE = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36"


def _browser(app, agent, ip):
    c = app.test_client()
    c.environ_base.update({"HTTP_USER_AGENT": agent, "REMOTE_ADDR": ip})
    return c


def _rows(app):
    from kts.db import query
    with app.app_context():
        return [dict(r) for r in query("SELECT * FROM visit_days ORDER BY day")]


def _footer(page):
    m = re.search(r'<span class="visitors">Visitors: <b dir="ltr">([\d,]+)</b> · Today: <b dir="ltr">([\d,]+)</b></span>', page)
    return (m.group(1), m.group(2)) if m else None


def test_one_browser_on_one_day_is_one_visitor():
    app = make_app(ADMIN_PASSWORD=None, VISITS_FLUSH_SECONDS=0)
    first, second = _browser(app, FIREFOX, "198.51.100.80"), _browser(app, PHONE, "198.51.100.81")
    for path in ("/", "/programme", "/thirukkural", "/register"):
        assert first.get(path).status_code == 200
    second.get("/")
    second.get("/partners")
    # not counted: robots, a browser that names none, files, the health check, answers in JSON, the console
    _browser(app, "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "66.249.66.1").get("/")
    _browser(app, "WhatsApp/2.23.20.0", "198.51.100.82").get("/programme")
    _browser(app, "", "198.51.100.83").get("/")
    first.get("/static/css/portal.css").close()
    first.get("/healthz")
    first.get("/quiz/api/state")
    staff = _staff(app, "admin@tests.example", "admin")
    staff.environ_base.update({"HTTP_USER_AGENT": FIREFOX, "REMOTE_ADDR": "198.51.100.84"})
    staff.get("/console/")
    rows = _rows(app)
    assert len(rows) == 1 and rows[0]["visitors"] == 2 and rows[0]["views"] == 6
    # only the day and two numbers are kept: no address, no browser, no mark
    assert set(rows[0]) == {"day", "visitors", "views"}


def test_the_footer_shows_the_visitors_and_the_switch_hides_them():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None, VISITS_FLUSH_SECONDS=0)
    for i in range(3):
        _browser(app, FIREFOX, f"198.51.100.{90 + i}").get("/")
    page = _browser(app, PHONE, "198.51.100.99").get("/?lang=en").get_data(as_text=True)
    # the page counts its own visitor after it is made: three before it
    assert _footer(page) == ("3", "3")
    assert _footer(_browser(app, PHONE, "198.51.100.99").get("/?lang=en").get_data(as_text=True)) == ("4", "4")
    from kts.i18n import CATALOG
    tamil = _browser(app, PHONE, "198.51.100.99").get("/?lang=ta").get_data(as_text=True)
    assert f'<span class="visitors">{CATALOG["ta"]["site.visitors"]}: <b dir="ltr">4</b>' in tamil
    with app.app_context():
        set_setting("site.visitors", "0")
    assert 'class="visitors"' not in _browser(app, PHONE, "198.51.100.99").get("/?lang=en").get_data(as_text=True)


def test_a_new_day_begins_a_new_count(monkeypatch):
    from kts import visits
    app = make_app(ADMIN_PASSWORD=None, VISITS_FLUSH_SECONDS=3600)
    real = visits.now_ist()
    browser = _browser(app, FIREFOX, "198.51.100.120")
    browser.get("/")
    browser.get("/programme")
    # the next day: what was held in memory goes to the row of the day before, the same browser is new again
    monkeypatch.setattr(visits, "now_ist", lambda: real + timedelta(days=1))
    browser.get("/")
    with app.app_context():
        visits.visits(app).flush()
    rows = _rows(app)
    assert [(r["visitors"], r["views"]) for r in rows] == [(1, 2), (1, 1)]
    assert rows[1]["day"] == (real + timedelta(days=1)).date().isoformat()


def test_the_dashboard_lists_the_last_thirty_days():
    app = make_app(ADMIN_PASSWORD=None, VISITS_FLUSH_SECONDS=3600)
    _browser(app, FIREFOX, "198.51.100.130").get("/")
    _browser(app, PHONE, "198.51.100.131").get("/")
    admin = _staff(app, "admin@tests.example", "admin")
    page = admin.get("/console/").get_data(as_text=True)
    assert "Visitors · last 30 days" in page and "total 2 visitors, 2 pages" in page
    assert page.count("<tr><td>", page.index('class="table visit-days"')) >= 30

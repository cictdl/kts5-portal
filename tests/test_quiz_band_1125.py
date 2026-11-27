"""
The Quiz on Thirukkural of MyGov, highlighted on the home page (1.2.215). CICT, 25 November 2026: "Kashi Tamil Sangamam 5.0 – Quiz
on Thirukkural on MyGov, 24 November – 12 December 2026 Highlighting link on Home page". A band of its own under the band of the
Academic Orientation - deep green, large bold white letters, a blinking NEW - that opens the quiz on quiz.mygov.in; its words are
the title of the pinned notice (1.2.213), and it is there while that notice is published and the quiz runs (to 12 December 2026,
11:45 PM IST).

    python -m pytest tests/test_quiz_band_1125.py -q
"""
import re
from datetime import datetime

from conftest import ROOT, make_app
from test_timeline import _sql

QUIZ = "https://quiz.mygov.in/quiz/kashi-tamil-sangamam-5-0-quiz-on-thirukkural/"
TITLE = "Kashi Tamil Sangamam 5.0 – Quiz on Thirukkural on MyGov, 24 November – 12 December 2026"


def _at(monkeypatch, moment):
    """The clock of the public pages at that moment (IST)."""
    from kts import public
    when = datetime.fromisoformat(moment + "+05:30")
    monkeypatch.setattr(public, "now_ist", lambda: when)


def _contrast(a, b):
    """The contrast of two colours as WCAG 2 counts it."""
    def lum(h):
        r, g, bl = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(bl)
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _band(page):
    if '<div class="quiz-band"' not in page:
        return None
    return page[page.index('<div class="quiz-band"'):page.index('<nav class="quick-links"')]


def test_the_band_on_the_home_page(monkeypatch):
    _at(monkeypatch, "2026-11-26T10:00:00")
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    page = client.get("/?lang=en").get_data(as_text=True)
    band = _band(page)
    assert band is not None
    # the title of the notice, large and bold, leading to the quiz itself in a new tab
    link = re.search(r'<a class="quiz-link" href="([^"]+)" target="_blank" rel="noopener" lang="en" dir="auto" style="([^"]+)">(.*?)</a>', band, flags=re.S)
    assert link and link.group(1) == QUIZ and TITLE in link.group(3)
    assert "color:#fff;font-weight:800;font-size:1.4rem" in link.group(2)
    # deep green, on which the white of the title and the gold of "Read more" are read with ease (7.1:1 and 4.9:1 at its lightest)
    assert "background:linear-gradient(90deg,#0b5132,#0e6540)" in band and '<span class="new-badge">NEW</span>' in band
    assert _contrast("#ffffff", "#0e6540") > 7 and _contrast("#ffd166", "#0e6540") > 4.5
    # the keyboard sees where it is on the two bands: a white outline, in the style sheet (its version 54)
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    assert ".acad-band a:focus-visible, .quiz-band a:focus-visible { outline: 3px solid #fff; outline-offset: 3px;" in css
    assert '<link rel="stylesheet" href="/static/css/portal.css?v=56">' in page and "<style" not in page
    # ... and to the notice, for what the quiz is
    nid = _sql(app, "SELECT id FROM notices WHERE title = ?", (TITLE,))[0][0]
    assert f'<a class="quiz-notice" href="/notices/{nid}"' in band and "Read more" in band
    # under the band of the Academic Orientation, above the quick links and the hero
    at = [page.index(mark) for mark in ('class="nodal-attention"', 'class="acad-band"', 'class="quiz-band"', 'class="quick-links"', 'class="hero"')]
    assert at == sorted(at)
    # in another language the title stays as the notice has it, in English; the rest in the language
    from kts.i18n import CATALOG
    tamil = _band(client.get("/?lang=ta").get_data(as_text=True))
    assert TITLE in tamil and CATALOG["ta"]["common.read_more"] in tamil and CATALOG["ta"]["circ.new"] in tamil
    # on the home page only
    assert _band(client.get("/programme?lang=en").get_data(as_text=True)) is None


def test_while_the_quiz_runs(monkeypatch):
    from kts.db import MYGOV_QUIZ_UNTIL
    assert MYGOV_QUIZ_UNTIL == "2026-12-12T23:45"
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for moment, shown in (("2026-11-25T09:00:00", True), ("2026-12-12T23:45:00", True), ("2026-12-12T23:46:00", False),
                          ("2026-12-13T08:00:00", False), ("2027-01-01T00:00:00", False)):
        _at(monkeypatch, moment)
        assert (_band(client.get("/?lang=en").get_data(as_text=True)) is not None) is shown, moment


def test_it_follows_the_notice(monkeypatch):
    _at(monkeypatch, "2026-11-26T10:00:00")
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    # in the words of CICT, when CICT rewords the notice in the Console
    _sql(app, "UPDATE notices SET title = 'Play the Thirukkural quiz on MyGov <now>' WHERE title = ?", (TITLE,))
    band = _band(client.get("/?lang=en").get_data(as_text=True))
    assert "Play the Thirukkural quiz on MyGov &lt;now&gt;" in band and TITLE not in band and f'href="{QUIZ}"' in band
    # ... and in the language that the notice has then
    _sql(app, "UPDATE notices SET lang = 'ta' WHERE link = ?", (QUIZ,))
    assert 'rel="noopener" lang="ta" dir="auto"' in _band(client.get("/?lang=en").get_data(as_text=True))
    # taken off the notices, the band goes with it
    _sql(app, "UPDATE notices SET published = 0 WHERE link = ?", (QUIZ,))
    assert _band(client.get("/?lang=en").get_data(as_text=True)) is None
    _sql(app, "UPDATE notices SET published = 1 WHERE link = ?", (QUIZ,))
    assert _band(client.get("/?lang=en").get_data(as_text=True)) is not None
    # a notice set to appear later is not announced before its time
    _sql(app, "UPDATE notices SET publish_at = '2999-01-01T00:00:00+00:00' WHERE link = ?", (QUIZ,))
    assert _band(client.get("/?lang=en").get_data(as_text=True)) is None
    # deleted, no band and no error
    _sql(app, "DELETE FROM notices WHERE link = ?", (QUIZ,))
    r = client.get("/?lang=en")
    assert r.status_code == 200 and _band(r.get_data(as_text=True)) is None

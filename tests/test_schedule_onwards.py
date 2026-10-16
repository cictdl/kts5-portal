"""
The Nationwide Students' Engagement Programme runs from 15 October 2026 onwards, with no last day (version 1.2.81): the
schedule and the home page say "15 Oct 2026 onwards", it stays among the upcoming events, and a database that holds the
days an earlier version put in (15 October – 15 November) gets the new ones at its next start; days set by CICT stay.

    python -m pytest tests -q
"""
from markupsafe import escape

from test_timeline import S, _halves, _on, _page, _portal, _sql, _start, _text


def test_the_programme_has_no_last_day():
    assert S["engage"]["starts"] == "2026-10-15" and S["engage"].get("onwards") is True and "ends" not in S["engage"]


def test_the_schedule_and_the_home_page_say_onwards(monkeypatch):
    app = _portal()
    _on(monkeypatch, "2026-10-16")
    upcoming, _past = _halves(_page(app, "/schedule?lang=en"))
    row = upcoming[upcoming.rindex("<tr>", 0, upcoming.index(_text("timeline.engage"))):upcoming.index(_text("timeline.engage"))]
    assert "15 Oct 2026 onwards" in row and "15 Nov 2026" not in row
    home = _page(app, "/?lang=en")
    item = home[home.index(_text("timeline.engage")):]
    assert '<span class="meta">15 Oct 2026 onwards</span>' in item[:item.index("</li>")]
    # in every language, the words of the phrase around the date
    from kts.i18n import CATALOG
    for code, catalogue in CATALOG.items():
        page = _page(app, f"/schedule?lang={code}")
        before, after = catalogue["schedule.onwards"].split("{date}")
        engage = page.index(_text("timeline.engage", code))
        row = page[page.rindex("<tr>", 0, engage):engage]
        assert str(escape(before)) in row and str(escape(after)) in row, code


def test_the_programme_is_not_over_after_15_november(monkeypatch):
    app = _portal()
    _on(monkeypatch, "2026-11-20")
    upcoming, past = _halves(_page(app, "/schedule?lang=en"))
    assert _text("timeline.engage") in upcoming and _text("timeline.engage") not in past
    # it runs until the Sangamam is over (12 December), and is then among the past events, by its first day
    _on(monkeypatch, "2026-12-12")
    upcoming, past = _halves(_page(app, "/schedule?lang=en"))
    assert _text("timeline.engage") in upcoming
    _on(monkeypatch, "2026-12-13")
    upcoming, past = _halves(_page(app, "/schedule?lang=en"))
    assert _text("timeline.engage") in past and _text("timeline.engage") not in upcoming
    assert "onwards" not in past


def test_the_days_of_an_earlier_version_are_replaced_at_the_next_start():
    title = S["engage"]["title"]
    app = _portal()
    # the days the live database holds since 1.2.43
    _sql(app, "UPDATE events SET starts_at = '2026-10-15T00:00', ends_at = '2026-11-15T00:00' WHERE title = ?", (title,))
    assert _sql(_start(app), "SELECT starts_at, ends_at FROM events WHERE title = ?", (title,)) == [("2026-10-15T00:00", None)]
    # days that CICT has set in the Console are left as they are
    _sql(app, "UPDATE events SET starts_at = '2026-10-16T00:00', ends_at = '2026-11-20T00:00' WHERE title = ?", (title,))
    assert _sql(_start(app), "SELECT starts_at, ends_at FROM events WHERE title = ?", (title,)) == [("2026-10-16T00:00", "2026-11-20T00:00")]

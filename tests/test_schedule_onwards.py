"""
A step of the timeline may run from its first day onwards, with no last day (version 1.2.81): the schedule and the home page
say "<day> onwards" and it stays among the upcoming events until the Sangamam is over. The step that had it, the Nationwide
Students' Engagement Programme from 15 October 2026, left the timeline with the revised D.O. letter (1.2.110), which has the
one-month engagement run from 12 December 2026 to 11 January 2027; the mechanism stays for a step that CICT marks so.

    python -m pytest tests -q
"""
from markupsafe import escape

from test_timeline import S, _halves, _on, _page, _portal, _sql, _start, _text


def _onwards(monkeypatch, key):
    from kts import public
    monkeypatch.setattr(public, "_onwards_titles", lambda: frozenset({S[key]["title"]}))


def test_no_step_of_the_revised_timeline_runs_onwards():
    assert not any(s.get("onwards") for s in S.values()) and "engage" not in S


def test_the_schedule_and_the_home_page_say_onwards(monkeypatch):
    _onwards(monkeypatch, "hei_reg")
    app = _portal()
    _on(monkeypatch, "2026-11-12")
    upcoming, _past = _halves(_page(app, "/schedule?lang=en"))
    title = _text("timeline.hei_reg")
    row = upcoming[upcoming.rindex("<tr>", 0, upcoming.index(title)):upcoming.index(title)]
    assert "10 Nov 2026 onwards" in row
    home = _page(app, "/?lang=en")
    item = home[home.index(title):]
    assert '<span class="meta">10 Nov 2026 onwards</span>' in item[:item.index("</li>")]
    # in every language, the words of the phrase around the date
    from kts.i18n import CATALOG
    for code, catalogue in CATALOG.items():
        page = _page(app, f"/schedule?lang={code}")
        before, after = catalogue["schedule.onwards"].split("{date}")
        at = page.index(_text("timeline.hei_reg", code))
        row = page[page.rindex("<tr>", 0, at):at]
        assert str(escape(before)) in row and str(escape(after)) in row, code


def test_it_is_not_over_until_the_sangamam_is(monkeypatch):
    _onwards(monkeypatch, "hei_reg")
    app = _portal()
    _on(monkeypatch, "2026-12-12")
    upcoming, past = _halves(_page(app, "/schedule?lang=en"))
    assert _text("timeline.hei_reg") in upcoming and _text("timeline.hei_reg") not in past
    _on(monkeypatch, "2026-12-13")
    upcoming, past = _halves(_page(app, "/schedule?lang=en"))
    assert _text("timeline.hei_reg") in past and _text("timeline.hei_reg") not in upcoming
    assert "onwards" not in past


def test_the_step_of_earlier_versions_leaves_the_schedule():
    # the Nationwide Students' Engagement Programme, 15 October 2026 onwards, as 1.2.81 left it: taken off the schedule, once
    title = "Nationwide Students' Engagement Programme in the participating institutions"
    app = _portal()
    _sql(app, "INSERT INTO events(title, kind, starts_at, published, created_at, updated_at) "
              "VALUES(?, 'general', '2026-10-15T00:00', 1, '2026-10-15', '2026-10-15')", (title,))
    _sql(app, "DELETE FROM settings WHERE key = 'migrate.revised_do.events'")
    assert _sql(_start(app), "SELECT published FROM events WHERE title = ?", (title,)) == [(0,)]

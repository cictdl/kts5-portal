"""
The dates of the revised D.O. letter where four things still had the October ones (1.2.126): CICT's nomination form, the
mail inviting an institution identified by the Nodal Institution, poster 1, and the Schedule, which now has CICT's central
online test among the dates kept as settings.

    python -m pytest tests -q
"""
import fitz

from conftest import ROOT
from test_timeline import _halves, _on, _page, _portal, _sql, _text

OLD = ("15–21 Oct", "15 – 21 October", "15 Oct 2026", "21 Oct 2026", "22 October 2026", "24 Oct 2026", "15 November 2026")


def _row(half, key):
    """The row of the schedule with this step: its days and its title."""
    at = half.index(_text(key))
    return half[half.rindex("<tr>", 0, at):half.index("</tr>", at)]


def _pdf_text(path):
    with fitz.open(path) as doc:
        return " ".join(" ".join(page.get_text().split()) for page in doc)


def test_the_nomination_form_has_the_last_day_of_the_revised_letter():
    text = _pdf_text(ROOT / "static" / "KTS5-nomination-form.pdf")
    assert "22 October" not in text and "15 October" not in text
    assert text.count("20 November 2026") == 2
    # the two lines re-set in 1.2.126 read with plain brackets when copied or read aloud
    assert "(nomination on or before 20 November 2026)" in text and "PNG (up to 4 MB)" in text
    assert "https://kts.cict.in/register on or before 20 November 2026" in text


def test_the_invitation_mail_has_the_days_of_the_sangamam():
    app = _portal()
    from kts import heis
    with app.app_context():
        heis.mail_invited({"invite_token": "t0k3n", "coord_email": "coord@example.edu", "head_email": "head@example.edu",
                           "name": "Example College", "state": "Tamil Nadu", "ref": "KTS5-HEI-0001"})
    bodies = [row[0] for row in _sql(app, "SELECT body FROM outbox ORDER BY id")]
    assert len(bodies) == 2
    for body in bodies:
        assert "15 October" not in body and "15 November" not in body
        assert "(the Sangamam at Varanasi: 28 November 2026 – 12 December 2026)" in body
        assert "registers that student on the portal by 20 November 2026" in body
        assert "/institutions/register?invite=t0k3n" in body


def test_poster_1_has_the_dates_of_the_settings():
    source = (ROOT / "tools" / "build_posters.py").read_text(encoding="utf-8")
    # no day written into the poster or the table of dates: they come from the settings
    poster = source[source.index("def poster1("):source.index("\ndef ", source.index("def poster1("))]
    table = source[source.index("DATES = {"):source.index("}", source.index("DATES = {"))]
    assert "2026" not in poster and "2026" not in table
    posters = sorted((ROOT / "static" / "posters").glob("KTS5-poster-1-*.pdf"))
    assert len(posters) == 23
    for path in posters:
        text = _pdf_text(path)
        for old in OLD:
            assert old not in text, (path.name, old)
        assert "22 Oct – 20 Nov 2026" in text and "28 Nov – 12 Dec 2026" in text, path.name
    english = _pdf_text(ROOT / "static" / "posters" / "KTS5-poster-1-en.pdf")
    assert "22 October – 20 November 2026" in english


def test_the_schedule_has_the_central_online_test(monkeypatch):
    app = _portal()
    _on(monkeypatch, "2026-10-01")
    upcoming, past = _halves(_page(app, "/schedule?lang=en"))
    row = _row(upcoming, "timeline.exam")
    assert "10 Nov 2026" in row and "– 20 Nov 2026" in row and _text("tag.examination") in row
    # in the language of the page
    assert _text("timeline.exam", "ta") in _page(app, "/schedule?lang=ta")
    # it stays upcoming until its last day is over
    _on(monkeypatch, "2026-11-20")
    assert _text("timeline.exam") in _halves(_page(app, "/schedule?lang=en"))[0]
    _on(monkeypatch, "2026-11-21")
    upcoming, past = _halves(_page(app, "/schedule?lang=en"))
    assert _text("timeline.exam") in past and _text("timeline.exam") not in upcoming


def test_the_schedule_leaves_out_a_test_switched_off(monkeypatch):
    app = _portal(**{"exam.open": "0"})
    _on(monkeypatch, "2026-10-01")
    assert _text("timeline.exam") not in _page(app, "/schedule?lang=en")
    # a test of one day has no last day
    app = _portal(**{"exam.date_to": ""})
    upcoming, _ = _halves(_page(app, "/schedule?lang=en"))
    row = _row(upcoming, "timeline.exam")
    assert "10 Nov 2026" in row and "– " not in row

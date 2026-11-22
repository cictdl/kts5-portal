"""
The notice of the extension to 27 November 2026, 5:00 PM (1.2.210). CICT, 22 November 2026, after the registration of institutions,
the assessment and the nomination were extended (1.2.209): "add a pinned notice for the extension to 27 November"; asked who the
notice should say extended the last date: "Ministry of Education".

    python -m pytest tests/test_ext_27nov_1122.py -q
"""
from conftest import make_app
from test_timeline import _sql, _start

TITLE = "Registration of institutions extended to 27 November 2026, 5:00 PM by the Ministry of Education"
MARK = "seed.notice.ext_27nov"
OLD = "Registration of institutions extended to 21 November 2026 by the Ministry of Education"


def test_its_days_are_the_days_of_the_portal():
    from kts.db import DEFAULT_SETTINGS, EXT27_NOTICE, RETIRED_DEFAULTS
    assert EXT27_NOTICE[0] == TITLE
    body = EXT27_NOTICE[1]
    for words, key, day, before in (("up to 27 November 2026, 5:00 PM (earlier 21 November)", "hei.end", "2026-11-27", "2026-11-21"),
                                    ("by 27 November 2026 (earlier 23 November)", "camp.to", "2026-11-27", "2026-11-23"),
                                    ("up to 27 November 2026, 5:00 PM (earlier 24 November)", "reg.end", "2026-11-27", "2026-11-24"),
                                    ("28 November", "kts.start", "2026-11-28", None),
                                    ("12 December 2026", "kts.end", "2026-12-12", None)):
        assert words in body and DEFAULT_SETTINGS[key] == day, (words, key)
        if before:   # the day it had, a day the portal has left
            assert before in RETIRED_DEFAULTS[key], key
    # the two hours of the notice are the hours of the portal
    assert DEFAULT_SETTINGS["hei.end_time"] == DEFAULT_SETTINGS["reg.end_time"] == "17:00" and body.count("5:00 PM") == 3
    assert body.startswith("The Ministry of Education, Government of India, has extended the last date for the registration of institutions "
                           "on this portal (kts.cict.in)") and "from 21 November 2026 to 27 November 2026, 5:00 PM." in body
    assert "Every institution that registers is a Participating Institution." in body
    # no day of the selection of institutions, which is no step of the programme since 1.2.201; short
    assert len(body) < 1200 and "reserve" not in body and "selected Participating" not in body and "22 November" not in body


def test_the_notice_is_pinned_first_and_leads_to_the_registration():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    rows = _sql(app, "SELECT title, category, lang, pinned, published, attachment, link FROM notices WHERE title = ?", (TITLE,))
    assert rows == [(TITLE, "circular", "en", 1, 1, "", "/institutions/register")]
    assert _sql(app, "SELECT value FROM settings WHERE key = ?", (MARK,)) == [("1",)]
    page = client.get("/notices?lang=en").get_data(as_text=True)
    assert TITLE in page and "Pinned" in page[page.index(TITLE) - 400:page.index(TITLE)]
    # the notice of the extension to 21 November stays off the notices (1.2.209): one notice of an extension, the present one
    assert OLD not in page and _sql(app, "SELECT published FROM notices WHERE title = ?", (OLD,)) == [(0,)]
    nid = _sql(app, "SELECT id FROM notices WHERE title = ?", (TITLE,))[0][0]
    one = client.get(f"/notices/{nid}?lang=en").get_data(as_text=True)
    assert "The Ministry of Education, Government of India, has extended" in one and 'href="/institutions/register"' in one
    assert "Registration of institutions on kts.cict.in: up to 27 November 2026, 5:00 PM (earlier 21 November)." in one
    assert "Nomination of one student by each Participating Institution on the portal: up to 27 November 2026, 5:00 PM (earlier 24 November)." in one


def test_a_live_database_takes_it_once_and_first():
    from kts.db import AICTE13_NOTICE, DO13_NOTICE
    app = make_app(ADMIN_PASSWORD=None)
    # the live database before this release: no such notice, no mark
    _sql(app, "DELETE FROM notices WHERE title = ?", (TITLE,))
    _sql(app, "DELETE FROM settings WHERE key = ?", (MARK,))
    _sql(app, "UPDATE notices SET created_at = '2026-11-18T06:00:00+00:00'")
    again = _start(app)
    notices = _sql(again, "SELECT title, pinned FROM notices WHERE published = 1 ORDER BY pinned DESC, created_at DESC, id DESC")
    assert notices[0] == (TITLE, 1) and {AICTE13_NOTICE[0], DO13_NOTICE[0]} <= {n[0] for n in notices}
    assert _sql(again, "SELECT value FROM settings WHERE key = ?", (MARK,)) == [("1",)]
    # the newest notice: the home page names it among the latest notices
    assert TITLE in again.test_client().get("/?lang=en").get_data(as_text=True)
    # once: a notice that CICT takes off, or words anew, stays as CICT left it
    _sql(again, "DELETE FROM notices WHERE title = ?", (TITLE,))
    third = _start(again)
    assert _sql(third, "SELECT COUNT(*) FROM notices WHERE title = ?", (TITLE,)) == [(0,)]
    # and none is added where a notice with its title is there already
    _sql(third, "INSERT INTO notices(title, body, category, lang, pinned, published, attachment, link, created_at, updated_at) "
                "VALUES(?, 'In the words of CICT.', 'circular', 'en', 1, 1, '', '', '2026-11-22T00:00:00+00:00', '2026-11-22T00:00:00+00:00')", (TITLE,))
    _sql(third, "DELETE FROM settings WHERE key = ?", (MARK,))
    fourth = _start(third)
    assert _sql(fourth, "SELECT body FROM notices WHERE title = ?", (TITLE,)) == [("In the words of CICT.",)]

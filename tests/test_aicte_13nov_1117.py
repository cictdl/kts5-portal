"""
The circular of AICTE of 13 November 2026 (F. No. AICTE/P&AP/Misc/2026, from the Member Secretary to the Vice-Chancellors of the
Technical Universities and the Principals/Directors of the AICTE-approved institutions: registration and student participation in
KTS 5.0), 1.2.197. CICT, 17 November 2026, with the circular: "pin the letter".

Its days are the days of the portal. The circular encloses the D.O. letter of 31 October with that letter's own days, which the
notice says the Ministry has revised since. The circular is pinned among the notices with the circular itself, once for each
database.

    python -m pytest tests/test_aicte_13nov_1117.py -q
"""
from markupsafe import escape

from conftest import ROOT, make_app
from test_timeline import _settings, _sql, _start

FILE = ROOT / "data" / "notices" / "KTS5-AICTE-circular-13-November-2026.pdf"
TITLE = "Circular of AICTE, 13 November 2026: registration and student participation in Kashi Tamil Sangamam 5.0"


def test_the_days_of_the_circular_are_the_days_of_the_portal():
    from kts.db import AICTE13_NOTICE, DEFAULT_SETTINGS
    body = AICTE13_NOTICE[1]
    for words, key, day in (("the last date of registration, 18 November 2026", "hei.end", "2026-11-18"),
                            ("selection by 19 November", "hei.select_end", "2026-11-19"),
                            ("by 23 November 2026", "camp.to", "2026-11-23"),
                            ("by 24 November 2026", "reg.end", "2026-11-24"),
                            ("28 November – 12 December 2026", "kts.start", "2026-11-28"),
                            ("28 November – 12 December 2026", "kts.end", "2026-12-12"),
                            ("from 15 December 2026 to 14 January 2027", "internship.start", "2026-12-15"),
                            ("from 15 December 2026 to 14 January 2027", "papers.due", "2027-01-14")):
        assert words in body and DEFAULT_SETTINGS[key] == day, (words, key)
    assert "a stipend of Rs. 10,000" in body
    # the letter enclosed gives its own days, and the notice says so
    assert "nomination by 20 November 2026), which the Ministry has revised since" in body


def test_the_circular_is_pinned_among_the_notices_with_its_file():
    from kts.db import AICTE13_NOTICE, AICTE13_NOTICE_FILE, set_setting
    assert AICTE13_NOTICE[0] == TITLE and AICTE13_NOTICE_FILE == "notices/" + FILE.name and FILE.is_file()
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    rows = _sql(app, "SELECT title, category, lang, pinned, published, attachment, link FROM notices WHERE title = ?", (TITLE,))
    assert rows == [(TITLE, "circular", "en", 1, 1, AICTE13_NOTICE_FILE, "/schedule")]
    page = client.get("/notices?lang=en").get_data(as_text=True)
    assert TITLE in page and "Pinned" in page[page.index(TITLE) - 400:page.index(TITLE)]
    nid = _sql(app, "SELECT id FROM notices WHERE title = ?", (TITLE,))[0][0]
    one = client.get(f"/notices/{nid}?lang=en").get_data(as_text=True)
    assert "F. No. AICTE/P&amp;AP/Misc/2026 of 13 November 2026 from the Member Secretary, All India Council for Technical Education" in one
    assert "Vice-Chancellors of the Technical Universities and the Principals/Directors of the AICTE-approved" in one
    assert "register on this portal (kts.cict.in) at the earliest" in one and "registrar@cict.in" in one
    assert "nominates one student on merit through this portal by 24 November 2026" in one
    assert f'href="/files/{AICTE13_NOTICE_FILE}"' in one and 'href="/schedule"' in one
    # the circular itself: a PDF of its 18 pages and nothing else
    r = client.get(f"/files/{AICTE13_NOTICE_FILE}")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data[:5] == b"%PDF-" and 5_000_000 < len(r.data) < 6_000_000
    for word in (b"/JavaScript", b"/OpenAction", b"/Launch", b"/EmbeddedFile", b"/RichMedia", b"/SubmitForm"):
        assert word not in r.data, word
    r.close()
    # where the Console shows the newest circular at the head of the home page, it is this one
    with app.app_context():
        set_setting("home.circular", "1")
    home = client.get("/?lang=en").get_data(as_text=True)
    first = home[home.index('<li class="na-first">'):]
    first = first[:first.index("</li>")]
    assert f'href="/notices/{nid}"' in first and "Circular of AICTE, 13 November 2026" in first


def _as_on_16_november(app):
    """The database of the live site before 1.2.197: no notice of the circular; the others put in on their days."""
    from kts.db import DO13_NOTICE
    _sql(app, "DELETE FROM notices WHERE title = ?", (TITLE,))
    _sql(app, "DELETE FROM settings WHERE key = 'seed.notice.aicte_13nov'")
    _sql(app, "UPDATE notices SET created_at = '2026-10-10T06:00:00+00:00'")
    _sql(app, "UPDATE notices SET created_at = '2026-11-16T06:00:00+00:00' WHERE title = ?", (DO13_NOTICE[0],))


def test_a_live_database_gets_the_notice_once_and_first():
    from kts.db import AICTE13_NOTICE_FILE, DO13_NOTICE
    app = make_app(ADMIN_PASSWORD=None)
    _as_on_16_november(app)
    before = _settings(app)
    again = _start(app)
    notices = _sql(again, "SELECT title, pinned, attachment FROM notices WHERE published = 1 ORDER BY pinned DESC, created_at DESC")
    # first among the notices, above the D.O. letter of 13 November
    assert [n[0] for n in notices[:2]] == [TITLE, DO13_NOTICE[0]] and notices[0][1:] == (1, AICTE13_NOTICE_FILE)
    client = again.test_client()
    page = client.get("/notices?lang=en").get_data(as_text=True)
    assert page.index(TITLE) < page.index(str(escape(DO13_NOTICE[0])))
    home = client.get("/?lang=en").get_data(as_text=True)
    assert home.index("Circular of AICTE, 13 November 2026") < home.index("D.O. letter of the Ministry of Education, 13 November 2026")
    # no setting moves
    after = _settings(again)
    assert {k: after[k] for k in before} == before and after["seed.notice.aicte_13nov"] == "1"
    # once: deleted in the Console, the notice does not come back
    _sql(again, "DELETE FROM notices WHERE title = ?", (TITLE,))
    assert _sql(_start(again), "SELECT COUNT(*) FROM notices WHERE title = ?", (TITLE,)) == [(0,)]


def test_what_cict_wrote_itself_stays():
    # CICT has put the circular in already, under the same title: no second notice
    app = make_app(ADMIN_PASSWORD=None)
    _as_on_16_november(app)
    _sql(app, "INSERT INTO notices(title, body, category, lang, pinned, published, attachment, link, created_at, updated_at) "
              "VALUES(?, 'Put in by CICT.', 'circular', 'en', 0, 1, '', '', '2026-11-17T06:00:00+00:00', '2026-11-17T06:00:00+00:00')", (TITLE,))
    again = _start(app)
    assert _sql(again, "SELECT body, pinned, attachment FROM notices WHERE title = ?", (TITLE,)) == [("Put in by CICT.", 0, "")]
    assert _settings(again)["seed.notice.aicte_13nov"] == "1"

"""
The D.O. letter of the Ministry of Education of 13 November 2026 (No. 16-2/2026-Skt.I (Pt.), to the Secretaries in charge of Higher
Education of the States and Union Territories; its annexure is the revised timeline), 1.2.189. CICT, 16 November 2026, with the
letter: "check the dates and change. Pin the do letter".

The dates were checked on the live site on 16 November, page by page: every day of the annexure is the day the portal has had since
the Ministry's e-mail of 10 November (1.2.171, 1.2.172). This file holds the two against each other, so that neither moves alone.
The letter is pinned among the notices and circulars with the letter itself, once for each database; the notice of the letter of
31 October, which gives that letter's own days, says that the Ministry has revised them since.

    python -m pytest tests/test_do_13nov_1116.py -q
"""
import json

from markupsafe import escape

from conftest import ROOT, make_app
from test_timeline import _settings, _sql, _start

FILE = ROOT / "data" / "notices" / "KTS5-DO-letter-13-November-2026.pdf"
# the annexure of the letter, row by row: the day as the notice writes it, the settings of the portal that hold it, the row of
# the schedule (data/timeline.json) that shows it
ANNEXURE = [
    ("18 November 2026: registration of institutions on kts.cict.in and outreach.", {"hei.end": "2026-11-18"}, ("hei_reg", "2026-11-18", None)),
    ("19 November 2026: scrutiny and selection of the Participating Institutions.", {"hei.select_end": "2026-11-19"}, ("hei_select", "2026-11-19", None)),
    ("23 November 2026: assessment of the interested students.", {"camp.to": "2026-11-23"}, ("assess", "2026-11-23", None)),
    ("24 November 2026: nomination of one student per institution on the CICT portal.", {"reg.end": "2026-11-24"}, None),
    ("28 November 2026: inaugural function of KTS 5.0 (virtual joining).", {"kts.start": "2026-11-28"}, None),
    ("12 December 2026: valedictory function of KTS 5.0 (virtual joining).", {"kts.end": "2026-12-12"}, None),
    ("14 December 2026: academic orientation and access to the study material.", {"orientation.by": "2026-12-14"}, ("live", "2026-12-14", None)),
    ("15 December 2026: commencement of the one-month research and academic engagement.", {"internship.start": "2026-12-15"},
     ("internship", "2026-12-15", None)),
    ("15 December 2026 – 14 January 2027: preparation of the article/research note and the one-hour presentation.", {},
     ("research", "2026-12-15", "2027-01-14")),
    ("14 January 2027: submission of the article/research note, the activity report and the supporting records; stipend (Rs. 10,000) "
     "through DBT after verification.", {"papers.due": "2027-01-14", "present.due": "2027-01-14"}, ("papers", "2027-01-14", None)),
    ("Academic review, compilation and recognition: as notified by CICT.", {}, None),
]


def test_every_day_of_the_annexure_is_the_day_of_the_portal():
    from kts.db import DEFAULT_SETTINGS, DO13_NOTICE, set_setting
    schedule = {r["key"]: (r["starts"], r.get("ends")) for r in json.loads((ROOT / "data" / "timeline.json").read_text(encoding="utf-8"))}
    assert len(ANNEXURE) == 11
    for line, settings, row in ANNEXURE:
        assert "• " + line in DO13_NOTICE[1], line
        for key, day in settings.items():
            assert DEFAULT_SETTINGS[key] == day, (line, key)
        if row:
            assert schedule[row[0]] == (row[1], row[2]), line
    # ... and the pages say them: the schedule, as a new database shows it
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("reg.end", DEFAULT_SETTINGS["reg.end"])      # the tests' own last day of registration (tests/conftest.py)
    page = app.test_client().get("/schedule?lang=en").get_data(as_text=True)
    for day in ("18 Nov 2026", "19 Nov 2026", "23 Nov 2026", "24 Nov 2026", "28 Nov 2026", "12 Dec 2026", "14 Dec 2026", "15 Dec 2026", "14 Jan 2027"):
        assert day in page, day
    main = page[page.index("<main"):page.index("</main>")]      # the foot of the page names the day of the release
    for gone in ("15 Nov 2026", "16 Nov 2026", "17 Nov 2026", "20 Nov 2026"):      # the days of the letter of 31 October
        assert gone not in main, gone


def test_the_letter_is_pinned_among_the_notices_with_its_file():
    from kts.db import DO13_NOTICE, DO13_NOTICE_FILE, DO_NOTICE, set_setting
    assert DO13_NOTICE_FILE == "notices/" + FILE.name and FILE.is_file()
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    rows = _sql(app, "SELECT title, category, lang, pinned, published, attachment, link FROM notices WHERE title = ?", (DO13_NOTICE[0],))
    assert rows == [(DO13_NOTICE[0], "circular", "en", 1, 1, DO13_NOTICE_FILE, "/schedule")]
    title = str(escape(DO13_NOTICE[0]))
    assert title == "D.O. letter of the Ministry of Education, 13 November 2026: Students&#39; Engagement Programme under KTS 5.0 (revised timeline)"
    page = client.get("/notices?lang=en").get_data(as_text=True)
    assert title in page and "Pinned" in page[page.index(title) - 400:page.index(title)]
    nid = _sql(app, "SELECT id FROM notices WHERE title = ?", (DO13_NOTICE[0],))[0][0]
    one = client.get(f"/notices/{nid}?lang=en").get_data(as_text=True)
    assert "D.O. No. 16-2/2026-Skt.I (Pt.) of 13 November 2026" in one and "Secretaries in charge of Higher Education of the States and Union Territories" in one
    assert "register on this portal (kts.cict.in) by 18 November 2026" in one and "MyGov portal (mygov.in)" in one
    assert "24 November 2026: nomination of one student per institution on the CICT portal." in one and "registrar@cict.in" in one
    assert f'href="/files/{DO13_NOTICE_FILE}"' in one and 'href="/schedule"' in one
    # the letter itself: a PDF of its pages and nothing else
    r = client.get(f"/files/{DO13_NOTICE_FILE}")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data[:5] == b"%PDF-" and 1_000_000 < len(r.data) < 2_000_000
    for word in (b"/JavaScript", b"/JS ", b"/OpenAction", b"/Launch", b"/EmbeddedFile", b"/URI", b"/AA "):
        assert word not in r.data, word
    # where the Console shows the newest circular at the head of the home page, it was this letter until the circular of AICTE of
    # the same day was pinned (1.2.197, tests/test_aicte_13nov_1117.py); without that one it is this letter
    _sql(app, "DELETE FROM notices WHERE title LIKE 'Circular of AICTE, 13 November 2026%'")
    with app.app_context():
        set_setting("home.circular", "1")
    home = client.get("/?lang=en").get_data(as_text=True)
    first = home[home.index('<li class="na-first">'):]
    first = first[:first.index("</li>")]
    assert f'href="/notices/{nid}"' in first and "D.O. letter of the Ministry of Education, 13 November 2026" in first
    # the notice of the letter of 31 October keeps the days of that letter, and says that they have been revised since
    old = client.get("/notices/%d?lang=en" % _sql(app, "SELECT id FROM notices WHERE title = ?", (DO_NOTICE[0],))[0][0]).get_data(as_text=True)
    assert "Up to 15 November 2026" in old and "which the Ministry has revised since (registration of institutions up to 18 November 2026" in old
    assert "the D.O. letter of 13 November 2026, among these notices" in old and "Annexure-III, the revised timeline:" not in old


def _as_on_15_november(app):
    """The database of the live site before 1.2.189: no notice of the letter of 13 November; the others put in on their days."""
    from kts.db import DO13_NOTICE, DO_NOTICE, DO_TIMELINE_LINE, DO_TIMELINE_LINE_1189, EXT_NOTICE
    _sql(app, "DELETE FROM notices WHERE title = ?", (DO13_NOTICE[0],))
    _sql(app, "DELETE FROM settings WHERE key = 'seed.notice.do_13nov'")
    _sql(app, "UPDATE notices SET created_at = '2026-10-10T06:00:00+00:00'")
    _sql(app, "UPDATE notices SET created_at = '2026-11-01T06:00:00+00:00', body = ? WHERE title = ?",
         (DO_NOTICE[1].replace(DO_TIMELINE_LINE, DO_TIMELINE_LINE_1189), DO_NOTICE[0]))
    _sql(app, "UPDATE notices SET created_at = '2026-11-11T06:00:00+00:00' WHERE title = ?", (EXT_NOTICE[0],))
    assert "Annexure-III, the revised timeline:" in _sql(app, "SELECT body FROM notices WHERE title = ?", (DO_NOTICE[0],))[0][0]


def test_a_live_database_gets_the_notice_once_and_first():
    from kts.db import DO13_NOTICE, DO13_NOTICE_FILE, DO_NOTICE, DO_TIMELINE_LINE, EXT_NOTICE
    app = make_app(ADMIN_PASSWORD=None)
    _as_on_15_november(app)
    before = _settings(app)
    again = _start(app)
    notices = _sql(again, "SELECT title, pinned, attachment FROM notices WHERE published = 1 ORDER BY pinned DESC, created_at DESC")
    # first among the notices, above the Ministry's revision of 10 November and the letter of 31 October
    assert [n[0] for n in notices[:3]] == [DO13_NOTICE[0], EXT_NOTICE[0], DO_NOTICE[0]] and notices[0][1:] == (1, DO13_NOTICE_FILE)
    client = again.test_client()
    page = client.get("/notices?lang=en").get_data(as_text=True)
    new, ext, old = (page.index(str(escape(t))) for t in (DO13_NOTICE[0], EXT_NOTICE[0], DO_NOTICE[0]))
    assert new < ext < old
    home = client.get("/?lang=en").get_data(as_text=True)
    assert home.index("D.O. letter of the Ministry of Education, 13 November 2026") < home.index("Extension of the registration deadline and revised timeline")
    # the notice of the letter of 31 October takes the word that its days have been revised
    assert DO_TIMELINE_LINE in _sql(again, "SELECT body FROM notices WHERE title = ?", (DO_NOTICE[0],))[0][0]
    # no setting moves: the days were those of the letter already
    after = _settings(again)
    assert {k: after[k] for k in before} == before and after["seed.notice.do_13nov"] == "1"
    # once: deleted in the Console, the notice does not come back
    _sql(again, "DELETE FROM notices WHERE title = ?", (DO13_NOTICE[0],))
    assert _sql(_start(again), "SELECT COUNT(*) FROM notices WHERE title = ?", (DO13_NOTICE[0],)) == [(0,)]


def test_what_cict_wrote_itself_stays():
    from kts.db import DO13_NOTICE, DO_NOTICE
    # CICT has put the letter in already, under the same title: no second notice
    app = make_app(ADMIN_PASSWORD=None)
    _as_on_15_november(app)
    _sql(app, "INSERT INTO notices(title, body, category, lang, pinned, published, attachment, link, created_at, updated_at) "
              "VALUES(?, 'Put in by CICT.', 'circular', 'en', 0, 1, '', '', '2026-11-14T06:00:00+00:00', '2026-11-14T06:00:00+00:00')", (DO13_NOTICE[0],))
    # ... and has rewritten the notice of the letter of 31 October
    _sql(app, "UPDATE notices SET body = 'CICT wrote this.' WHERE title = ?", (DO_NOTICE[0],))
    again = _start(app)
    assert _sql(again, "SELECT body, pinned, attachment FROM notices WHERE title = ?", (DO13_NOTICE[0],)) == [("Put in by CICT.", 0, "")]
    assert _sql(again, "SELECT body FROM notices WHERE title = ?", (DO_NOTICE[0],)) == [("CICT wrote this.",)]
    assert _settings(again)["seed.notice.do_13nov"] == "1"

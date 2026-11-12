"""
The D.O. letter of the Ministry of Education of 31 October 2026 (version 1.2.133): the numbers of Participating Institutions
of nine States/UTs and the days of the timeline. A live database that holds the letter of 26 October takes them once: the
settings, the steps of the schedule where they still hold the old days, and the circular of the Nodal Institutions; what
CICT changed in the Console afterwards stays so.

    python -m pytest tests -q
"""
import json
import sqlite3

from conftest import ROOT, make_app
from test_nodal_notice import TITLE, _notices
from test_timeline import S, SEEDS, _settings, _sql, _start

OLD_SETTINGS = {"hei.end": "2026-11-10", "hei.select_end": "2026-11-15", "camp.to": "2026-11-20", "internship.start": "2026-12-12",
                "papers.due": "2027-01-11", "present.due": "2027-01-11", "remind.test_by": "2026-11-16",
                "remind.select_by": "2026-11-18", "remind.register_by": "2026-11-19", "orientation.by": "2026-12-10"}
OLD_DAYS = {"hei_reg": ("2026-11-10", None), "hei_select": ("2026-11-11", "2026-11-15"), "assess": ("2026-11-20", None),
            "live": ("2026-12-10", None), "internship": ("2026-12-12", None), "research": ("2026-12-12", "2027-01-11"),
            "papers": ("2027-01-11", None)}


def test_the_numbers_and_the_days_of_the_letter():
    from kts.db import DEFAULT_SETTINGS, REVISED_DO2_DATES
    heis = {h["state"]: h["allocation"] for h in json.loads((ROOT / "data" / "nodal_heis.json").read_text(encoding="utf-8"))}
    assert {s: heis[s] for s in ("Andhra Pradesh", "Gujarat", "Karnataka", "Madhya Pradesh", "Maharashtra", "Odisha", "Tamil Nadu",
                                 "Uttar Pradesh", "West Bengal")} == {
        "Andhra Pradesh": 50, "Gujarat": 50, "Karnataka": 49, "Madhya Pradesh": 40, "Maharashtra": 71, "Odisha": 48,
        "Tamil Nadu": 50, "Uttar Pradesh": 300, "West Bengal": 48}
    assert sum(heis.values()) == 1000 and heis["Jammu and Kashmir"] == 11 and heis["Puducherry"] == 5
    assert {k: DEFAULT_SETTINGS[k] for k in OLD_SETTINGS} == {
        "hei.end": "2026-11-18", "hei.select_end": "2026-11-19", "camp.to": "2026-11-23", "internship.start": "2026-12-15",
        "papers.due": "2027-01-14", "present.due": "2027-01-14", "remind.test_by": "2026-11-22", "remind.select_by": "2026-11-23",
        "remind.register_by": "2026-11-24", "orientation.by": "2026-12-14"}   # the Ministry's revision of 10 November (1.2.172)
    assert set(REVISED_DO2_DATES) == set(OLD_SETTINGS)
    # the nomination, the verification and the Sangamam stay
    assert DEFAULT_SETTINGS["reg.end"] == "2026-11-24" and DEFAULT_SETTINGS["verify.end"] == "2026-12-05"   # nomination: 1.2.172
    assert (DEFAULT_SETTINGS["kts.start"], DEFAULT_SETTINGS["kts.end"]) == ("2026-11-28", "2026-12-12")
    assert (S["hei_reg"]["starts"], S["hei_select"]["starts"], S["hei_select"].get("ends"), S["assess"]["starts"]) == (
        "2026-11-18", "2026-11-19", None, "2026-11-23")   # registration up to 18 November since 1.2.171
    assert (S["live"]["starts"], S["internship"]["starts"], S["research"]["starts"], S["research"]["ends"], S["papers"]["starts"]) == (
        "2026-12-14", "2026-12-15", "2026-12-15", "2027-01-14", "2027-01-14")


def test_a_live_database_of_the_letter_of_26_october_takes_the_new_days_once():
    """Version 1.2.132 on the live site: the settings and the steps as the letter of 26 October put them (and a date CICT set in
    the Console); the circular of the Nodal Institutions with its numbers. At the next start the days of the letter of 31
    October replace them, once; a step CICT moved by hand stays; what CICT changes afterwards stays."""
    from kts.db import DEFAULT_SETTINGS
    app = make_app(ADMIN_PASSWORD=None)
    for key, value in dict(OLD_SETTINGS, **{"camp.to": "2026-11-21"}).items():   # camp.to set by CICT in the Console
        _sql(app, "UPDATE settings SET value = ? WHERE key = ?", (value, key))
    _sql(app, "DELETE FROM settings WHERE key LIKE 'migrate.revised_do2%'")
    for key, (starts, ends) in OLD_DAYS.items():
        _sql(app, "UPDATE events SET starts_at = ?, ends_at = ? WHERE title = ?",
             (starts + "T00:00", ends + "T00:00" if ends else None, S[key]["title"]))
    # the orientation moved by CICT in the Console stays where it was put
    _sql(app, "UPDATE events SET starts_at = '2026-12-11T10:00' WHERE title = ?", (S["live"]["title"],))
    old_body = _notices(app)[0]["body"].replace("up to 18 November 2026", "up to 10 November 2026").replace("(50)", "(150)")
    _sql(app, "UPDATE notices SET body = ? WHERE title = ?", (old_body, TITLE))
    again = _start(app)
    settings = _settings(again)
    assert {k: settings[k] for k in OLD_SETTINGS} == {k: DEFAULT_SETTINGS[k] for k in OLD_SETTINGS}
    rows = {t: (s, e) for t, s, e in _sql(again, "SELECT title, starts_at, ends_at FROM events")}
    for key in OLD_DAYS:
        s = S[key]
        if key == "live":
            assert rows[s["title"]] == ("2026-12-11T10:00", None)
        else:
            assert rows[s["title"]] == (s["starts"] + "T00:00", s["ends"] + "T00:00" if s.get("ends") else None), key
    for s in SEEDS:
        assert s["title"] in rows, s["key"]
    body = _notices(again)[0]["body"]
    assert "up to 18 November 2026" in body and "on 19 November 2026" in body and "(150)" not in body
    assert "Central University of Tamil Nadu (50)" in body and "Banaras Hindu University (300)" in body
    # changed in the Console afterwards, they stay so
    _sql(again, "UPDATE settings SET value = '2026-11-18' WHERE key = 'hei.end'")
    _sql(again, "UPDATE notices SET body = 'CICT wrote this.' WHERE title = ?", (TITLE,))
    third = _start(again)
    assert _settings(third)["hei.end"] == "2026-11-18" and _notices(third)[0]["body"] == "CICT wrote this."


def test_the_pages_show_the_days_of_the_letter():
    from kts.db import set_setting, DEFAULT_SETTINGS
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for key in ("reg.start", "reg.end"):
            set_setting(key, DEFAULT_SETTINGS[key])
    client = app.test_client()
    guide = client.get("/how-to-take-part?lang=en").get_data(as_text=True)
    assert "18 Nov 2026" in guide and "19 Nov 2026" in guide and "23 Nov 2026" in guide and "24 Nov 2026" in guide
    main = guide[guide.index("<main"):guide.index("</main>")]   # not the foot, which names the day of the release
    assert "10 Nov 2026" not in main and "11 Nov 2026" not in main
    nodal = client.get("/nodal-institutions?lang=en").get_data(as_text=True)
    # no number to be selected of a State/UT on the public pages (1.2.179): the table has no column of it
    assert ">300<" not in nodal and ">1,000</th>" not in nodal and "Number of Participating HEIs to be selected" not in nodal
    schedule = client.get("/schedule?lang=en").get_data(as_text=True)
    for day in ("18 Nov 2026", "19 Nov 2026", "23 Nov 2026", "25 Nov 2026", "14 Dec 2026", "15 Dec 2026", "– 14 Jan 2027"):
        assert day in schedule, day
    assert "11 Jan 2027" not in schedule and "10 Dec 2026" not in schedule   # the central test still opens on 10 November


def test_the_letter_is_pinned_among_the_notices_with_its_file():
    from kts.db import DO_NOTICE, DO_NOTICE_FILE
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    rows = _sql(app, "SELECT title, category, pinned, published, attachment, link FROM notices WHERE title = ?", (DO_NOTICE[0],))
    assert rows == [(DO_NOTICE[0], "circular", 1, 1, DO_NOTICE_FILE, "/schedule")]
    from markupsafe import escape
    title = str(escape(DO_NOTICE[0]))
    page = client.get("/notices?lang=en").get_data(as_text=True)
    assert title in page and "Pinned" in page[page.index(title) - 400:page.index(title)]   # pinned, as the circular of the Nodal HEIs is
    nid = _sql(app, "SELECT id FROM notices WHERE title = ?", (DO_NOTICE[0],))[0][0]
    one = client.get(f"/notices/{nid}?lang=en").get_data(as_text=True)
    assert "Up to 15 November 2026" in one and "14 January 2027" in one and "registrar@cict.in" in one
    assert f'href="/files/{DO_NOTICE_FILE}"' in one and 'href="/schedule"' in one
    r = client.get(f"/files/{DO_NOTICE_FILE}")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data[:5] == b"%PDF-" and len(r.data) > 4_000_000
    # put in once: deleted in the Console, it does not come back; nor is it added twice where CICT put it in already
    _sql(app, "DELETE FROM notices WHERE title = ?", (DO_NOTICE[0],))
    assert _sql(_start(app), "SELECT COUNT(*) FROM notices WHERE title = ?", (DO_NOTICE[0],)) == [(0,)]
    other = make_app(ADMIN_PASSWORD=None)
    _sql(other, "DELETE FROM settings WHERE key = 'seed.notice.do_31oct'")
    assert _sql(_start(other), "SELECT COUNT(*) FROM notices WHERE title = ?", (DO_NOTICE[0],)) == [(1,)]

"""
The Ministry of Education's revision of the timeline of 10 November 2026 (1.2.172; e-mail "KTS 5.0 Students' Engagement
Programme - Extension of registration deadline and revised timelines"): registration of institutions up to 18 November (1.2.171),
selection by the Nodal Institutions 19 November (was 16-17), assessment by 23 November (was 19), nomination 24 November (was 20);
CICT's consolidation and verification of the nominations 25 November - 5 December (was from 21 November). A live database at the
days of 1.2.171 takes them at the next start; what CICT set in the Console stays. The revision is pinned as a notice, above the
D.O. letter; the circular of the Nodal Institutions and the launch notice take the revised days where their text is unchanged.

Since 1.2.209 (CICT, 22 November 2026: "Extend both to 27 Nov, 5 PM") the registration of institutions, the assessment and the
nomination run up to 27 November 2026, the nomination up to 5:00 PM: the settings the portal comes with, the schedule, a database
started again, poster 1 and the nomination form have those days; the notice of the revision keeps the words of the Ministry.

    python -m pytest tests/test_dates_1111.py -q
"""
import re

import fitz

from conftest import ROOT, make_app
from test_timeline import S, _settings, _sql, _start

# the first two days are those of 1.2.203 (CICT, 18 November 2026: 21 and 22 November; 18 and 19 by the revision of 10 November)
# ... and since 1.2.209 (CICT, 22 November 2026: "Extend both to 27 Nov, 5 PM") the registration of institutions, the assessment and
# the nomination are up to 27 November 2026; the selection and the reminders keep their days
NEW = {"hei.end": "2026-11-27", "hei.select_end": "2026-11-22", "camp.to": "2026-11-27", "reg.end": "2026-11-27",
       "remind.test_by": "2026-11-22", "remind.select_by": "2026-11-23", "remind.register_by": "2026-11-24"}
# the three days of the revision that 1.2.209 moved (21 November: of 1.2.203), days of before now
REVISED = {"hei.end": "2026-11-21", "camp.to": "2026-11-23", "reg.end": "2026-11-24"}
OLD = {"hei.end": "2026-11-18", "hei.select_end": "2026-11-17", "camp.to": "2026-11-19", "reg.end": "2026-11-20",
       "remind.test_by": "2026-11-18", "remind.select_by": "2026-11-19", "remind.register_by": "2026-11-20"}
OLD_DAYS = {"hei_select": ("2026-11-16T00:00", "2026-11-17T00:00"), "assess": ("2026-11-19T00:00", None),
            "selection": ("2026-11-21T00:00", "2026-12-05T00:00")}


def test_the_days():
    from kts.db import DEFAULT_SETTINGS, RETIRED_DEFAULTS
    assert {k: DEFAULT_SETTINGS[k] for k in NEW} == NEW
    # unchanged: the central test, the verification by the Nodal Officers, the Sangamam, the engagement
    assert (DEFAULT_SETTINGS["verify.end"], DEFAULT_SETTINGS["kts.start"], DEFAULT_SETTINGS["kts.end"]) == (
        "2026-12-05", "2026-11-28", "2026-12-12")
    assert (DEFAULT_SETTINGS["orientation.by"], DEFAULT_SETTINGS["internship.start"], DEFAULT_SETTINGS["papers.due"]) == (
        "2026-12-14", "2026-12-15", "2027-01-14")
    for key, old in OLD.items():
        if old != NEW[key]:
            assert old in RETIRED_DEFAULTS[key], key
    # the days of the revision that the extension to 27 November moved are days of before as well (1.2.209)
    for key, old in REVISED.items():
        assert old in RETIRED_DEFAULTS[key] and NEW[key] not in RETIRED_DEFAULTS[key], key
    # the reminders: each key once, with the days of the letters of 26 and 31 October
    assert {"2026-10-20", "2026-11-19"} <= set(RETIRED_DEFAULTS["remind.select_by"])
    assert {"2026-10-21", "2026-11-20"} <= set(RETIRED_DEFAULTS["remind.register_by"])
    # the schedule, in the order of its days
    # ... since 1.2.209 the registration of institutions and the assessment on 27 November (21 and 23 before), and so after the
    # selection (22 November) and the first day of the consolidation and verification (25 November)
    assert (S["hei_reg"]["starts"], S["hei_select"]["starts"], S["hei_select"].get("ends"), S["assess"]["starts"]) == (
        "2026-11-27", "2026-11-22", None, "2026-11-27")
    assert (S["selection"]["starts"], S["selection"]["ends"]) == ("2026-11-25", "2026-12-05")
    keys = [k for k in S]
    assert keys.index("hei_select") < keys.index("selection") < keys.index("hei_reg") < keys.index("assess")


def test_a_live_database_takes_the_revision_once():
    from kts.db import EXT_NOTICE, LAUNCH_BODY_1171, LAUNCH_NOTICE, NODAL_DAYS, NODAL_DAYS_1171
    app = make_app(ADMIN_PASSWORD=None)
    # 1.2.171 on the live site: its settings and days, the circular and the launch notice with the days of 31 October, no notice
    # of the revision; the assessment set by CICT in the Console to 21 November
    for key, value in dict(OLD, **{"camp.to": "2026-11-21"}).items():
        _sql(app, "UPDATE settings SET value = ? WHERE key = ?", (value, key))
    for key, (starts, ends) in OLD_DAYS.items():
        _sql(app, "UPDATE events SET starts_at = ?, ends_at = ? WHERE title = ?", (starts, ends, S[key]["title"]))
    _sql(app, "DELETE FROM notices WHERE title = ?", (EXT_NOTICE[0],))
    _sql(app, "DELETE FROM settings WHERE key = 'seed.notice.ext_10nov'")
    _sql(app, "UPDATE notices SET body = replace(body, ?, ?) WHERE category = 'circular'", (NODAL_DAYS, NODAL_DAYS_1171))
    _sql(app, "UPDATE notices SET body = ? WHERE title = ?", (LAUNCH_BODY_1171, LAUNCH_NOTICE[0]))
    again = _start(app)
    settings = _settings(again)
    assert {k: settings[k] for k in NEW} == dict(NEW, **{"camp.to": "2026-11-21"})   # CICT's own day stays
    rows = {t: (s, e) for t, s, e in _sql(again, "SELECT title, starts_at, ends_at FROM events")}
    assert rows[S["hei_select"]["title"]] == ("2026-11-22T00:00", None)      # 22 November since 1.2.203
    assert rows[S["assess"]["title"]] == ("2026-11-27T00:00", None)          # 27 November since 1.2.209 (23 by the revision)
    assert rows[S["selection"]["title"]] == ("2026-11-25T00:00", "2026-12-05T00:00")
    notices = _sql(again, "SELECT title, body, pinned, link FROM notices WHERE published = 1 ORDER BY pinned DESC, created_at DESC, id DESC")
    assert notices[0][0] == EXT_NOTICE[0] and notices[0][2] == 1 and notices[0][3] == "/schedule"
    bodies = "\n".join(n[1] for n in notices)
    assert NODAL_DAYS in bodies and NODAL_DAYS_1171 not in bodies and LAUNCH_NOTICE[1] in bodies
    # the notice that quotes the D.O. letter of 31 October keeps its days
    assert "Up to 15 November 2026: registration of interested institutions" in bodies
    # once: a notice of the revision deleted by CICT does not come back
    _sql(again, "DELETE FROM notices WHERE title = ?", (EXT_NOTICE[0],))
    third = _start(again)
    assert not _sql(third, "SELECT 1 FROM notices WHERE title = ?", (EXT_NOTICE[0],))


def test_the_pages_and_the_notice():
    from kts import finder
    from kts.db import DEFAULT_SETTINGS, EXT_NOTICE, all_settings, set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():   # the tests' portal keeps the nomination open far ahead; here its day
        for key in ("reg.start", "reg.end"):
            set_setting(key, DEFAULT_SETTINGS[key])
    client = app.test_client()
    page = client.get("/schedule?lang=en").get_data(as_text=True)
    box = re.sub(r"<[^>]+>", "|", page[page.index('<div class="kd-box">'):][:6000])
    # the nomination, set above to the day the portal comes with: 27 November 2026 since 1.2.209 (24 November by the revision).
    # The registration and the assessment are those the tests' portal keeps (conftest: 21 and 23 November, the days of 1.2.208)
    for line in ("|Up to 21 Nov 2026|", "|22 Nov 2026|", "|By 23 Nov 2026|", "|27 Nov 2026|", "|28 Nov 2026|"):
        assert line in box, line
    assert "16 Nov 2026" not in box and "– 19 Nov" not in box and "|24 Nov 2026|" not in box
    with app.test_request_context():
        words = finder.hub(all_settings(), "en")["words"]
    assert (words["hei_end"], words["select"], words["camp_to"], words["reg_end"]) == (
        "21 November 2026", "22 November 2026", "23 November 2026", "27 November 2026")
    notices = client.get("/notices?lang=en").get_data(as_text=True)
    assert EXT_NOTICE[0] in notices
    assert "up to 18 November 2026 (earlier 15 November)" in EXT_NOTICE[1] and "24 November 2026 (earlier 20 November)" in EXT_NOTICE[1]


def test_the_poster_and_the_form():
    # since 1.2.209 the assessment up to 27 November and the nomination by 27 November 2026, 5:00 PM (23 and 24 November by the
    # revision): poster 1 built anew, the two lines of the form set anew. Both days being the 27th now, the day of the nomination
    # is looked for with its hour, which the poster gives with it alone (the words of a line that runs on are put together)
    for lang in ("en", "hi", "ta"):
        text = " ".join(fitz.open(ROOT / "static" / "posters" / f"KTS5-poster-1-{lang}.pdf")[0].get_text().split())
        assert "22 Oct – 27 Nov 2026" in text and "27 Nov 2026, 5:00 PM" in text and "19 Nov" not in text and "20 Nov" not in text, lang
        assert "23 Nov" not in text and "24 Nov" not in text, lang
    form = " ".join(fitz.open(ROOT / "static" / "KTS5-nomination-form.pdf")[0].get_text().split())
    assert form.count("27 November 2026") == 2 and form.count("on or before 27 November 2026, 5:00 PM") == 2
    assert "24 November" not in form and "20 November 2026" not in form

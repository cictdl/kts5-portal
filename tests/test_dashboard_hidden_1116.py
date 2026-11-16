"""
The dashboard by State/UT and the page of the progress as CICT asked for them on 16 November 2026 (1.2.189), one picture after the
other:

  "hide this one"                           the card "Students who took an institution's online test" of the dashboard
  "change the wordings as Participating Institutions registered"
                                            the card "Participating Institutions selected", and the same on /progress
  "hide all the percentage calculations"    the scale 0% ... > 75% under the map of the dashboard
  "hide this portion"                       the table "The figures of each State/UT" of the dashboard
  "hide the percentage graph"               the ring of the Participating Institutions on /progress (the number stays)
  "hide this one"                           the ring "Institutions assessing their students online" of /progress

Three switches of the Console, each off, show again what they hide: figures.assessment (the figures of the institutions' online
assessment), dashboard.table (the table), figures.percent (the percentages). tests/conftest.py switches the three on for the tests
made before; the tests here look at the pages as they are.

    python -m pytest tests/test_dashboard_hidden_1116.py -q
"""
import json
import re

from test_1110 import _app, _get, _main

HIDDEN = {"figures.assessment": "0", "dashboard.table": "0", "figures.percent": "0"}
KEYS = ("dash.inst_sel", "dash.intro_plain", "dash.intro_inst", "pi.states_title_plain", "pg.states_title_plain", "dash.no_inst", "hub.s_count")


def _live(**shown):
    """The portal of tests/test_1110.py (three institutions selected in Tamil Nadu, one in Kerala with one on its reserve list) as the live site is."""
    return _app(**{**HIDDEN, **shown})


def _dashboard(**shown):
    return _main(_get(_live(**shown).test_client(), "/dashboard?lang=en"))


def test_the_three_switches_are_off_and_stand_in_the_console():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS, execute, get_setting, init_db
    assert {key: DEFAULT_SETTINGS[key] for key in HIDDEN} == HIDDEN
    site = {key: kind for key, _label, kind in dict(SETTING_GROUPS)["Site"]}
    assert [site.get(key) for key in HIDDEN] == ["bool"] * 3
    # a database of before 1.2.189 gets the three, off
    app = _app()
    with app.app_context():
        execute("DELETE FROM settings WHERE key IN ('figures.assessment', 'dashboard.table', 'figures.percent')")
    init_db(app)
    with app.app_context():
        assert {key: get_setting(key) for key in HIDDEN} == HIDDEN


def test_the_dashboard_as_cict_asked_for_it():
    page = _dashboard()
    # two cards: no students who took an institution's online test
    kpis = page[page.index('class="grid grid-2 dash-kpis"'):page.index('<section class="card dash-map"')]
    assert re.findall(r'<div class="lbl">([^<]+)</div>', kpis) == ["To be selected", "Participating Institutions registered"]
    assert re.findall(r'<div class="num">([^<]+)</div>', kpis) == ["1,000", "5"]
    assert "Students who took" not in page and "online test" not in page
    assert '<p class="dim" style="max-width:80ch">Where the programme stands in each State/UT: the Participating Institutions registered.</p>' in page
    # the map: its squares and what a paired Union Territory is, without a scale in per cent
    assert '<h2 id="dash-grid-h">Participating Institutions registered</h2>' in page
    legend = page[page.index('<ul class="dash-legend">'):]
    legend = legend[:legend.index("</ul>")]
    assert legend.count("<li>") == 1 and "Union Territory counted with another row of Annexure-I" in legend and "%" not in legend
    assert "≤ 25%" not in page and "&gt; 75%" not in page and "dash-sw b0" not in page
    tn = page[page.index('href="#d-TN"'):]
    tn = tn[:tn.index("</a>")]
    assert '<span class="dash-n" dir="ltr">3</span>' in tn and "Participating Institutions registered: <bdi>3</bdi>" in tn
    # no table "The figures of each State/UT"
    assert "dash-table" not in page and "The figures of each State/UT" not in page and "<thead>" not in page and 'id="st-TN"' not in page
    # each State/UT below as before, with what "Marks recorded" counts, said once
    block = page[page.index('<details class="card dash-state" id="d-TN">'):]
    summary = block[:block.index("</summary>")]
    assert "Participating Institutions registered: 3" in summary and "Marks recorded" in summary
    assert '<h3 class="dash-sub">Participating Institutions registered</h3>' in block
    assert page.count('class="small muted dash-marks-note"') == 1 and page.index("dash-marks-note") > page.index('id="dash-det-h"')
    assert "No Participating Institution registered yet" in page and "Participating Institutions selected" not in page


def test_each_switch_shows_its_part_of_the_dashboard_again():
    # the figures of the online assessment: the card, and the line that names them
    page = _dashboard(**{"figures.assessment": "1"})
    kpis = page[page.index('class="grid grid-3 dash-kpis"'):page.index('<section class="card dash-map"')]
    assert re.findall(r'<div class="lbl">([^<]+)</div>', kpis) == ["To be selected", "Participating Institutions registered",
                                                                     "Students who took an institution&#39;s online test"]
    assert "the Participating Institutions registered and the students who took an institution&#39;s online test." in page
    assert "dash-table" not in page and "≤ 25%" not in page
    # the table, without the column of the students who took the test while that figure is hidden
    page = _dashboard(**{"dashboard.table": "1"})
    head = page[page.index("<thead>"):page.index("</thead>")]
    assert re.findall(r"<th[^>]*>([^<]+)</th>", head) == ["State / UT", "Participating Institutions registered", "Marks recorded"]
    row = page[page.index('<tr id="st-TN">'):]
    assert re.findall(r'<td class="num">([^<]*)</td>', row[:row.index("</tr>")]) == ["3"]
    assert page.count('class="small muted dash-marks-note"') == 1 and page.index("dash-marks-note") < page.index('id="dash-det-h"')
    assert "Students who took" not in page and 'class="grid grid-2 dash-kpis"' in page
    # ... and with it
    page = _dashboard(**{"dashboard.table": "1", "figures.assessment": "1"})
    head = page[page.index("<thead>"):page.index("</thead>")]
    assert head.count("<th ") == 4 and "Students who took an institution&#39;s online test" in head
    row = page[page.index('<tr id="st-TN">'):]
    assert re.findall(r'<td class="num">([^<]*)</td>', row[:row.index("</tr>")]) == ["3", "0"]
    # the scale of the map
    page = _dashboard(**{"figures.percent": "1"})
    legend = page[page.index('<ul class="dash-legend">'):]
    legend = legend[:legend.index("</ul>")]
    assert legend.count("<li>") == 6 and "≤ 25%" in legend and "&gt; 75%" in legend and "dash-table" not in page


def test_the_progress_page_as_cict_asked_for_it():
    client = _live().test_client()
    page = _main(_get(client, "/progress?lang=en"))
    # one card: the Participating Institutions registered, a number and no ring; no institutions assessing their students online
    rings = page[page.index('<div class="prog-rings"'):page.index('<section class="card prog-flow"')]
    assert rings.count('class="card prog-ring') == 1 and 'class="card prog-ring ring-participating"' in rings
    assert "<svg" not in rings and 'class="pct"' not in rings and "%" not in rings
    assert '<div class="num" data-count="5" data-k="participating">5</div>' in rings
    assert '<div class="lbl">Participating Institutions registered</div>' in rings and ">5 of 1,000</bdi>" in rings
    assert "Institutions assessing their students online" not in page and "Participating Institutions selected" not in page
    # the stages without that of the online assessment, and without a percentage
    assert re.findall(r'<li class="stage stage-(\w+)">', page) == ["participating", "selected"] and "st-pct" not in page
    flow = page[page.index('<section class="card prog-flow"'):page.index('<section class="card prog-states"')]
    assert '<span class="st-lbl">Participating Institutions registered</span>' in flow and not re.search(r">\d+%<", flow)
    assert "The rows of Annexure-I with the most Participating Institutions registered" in page
    # the figures its script asks for every minute
    data = json.loads(_get(client, "/progress.json"))
    flat = data["flat"]
    assert not [k for k in flat if "testing" in k or "tested" in k or "signed_up" in k or k.endswith("_pct")], sorted(flat)
    assert data["shares"] == {} and "st_testing" not in data["widths"] and data["widths"]["st_participating"] == 100.0
    assert flat["participating"] == 5 and flat["st_participating"] == 5 and flat["participating_of"] == "5 of 1,000"


def test_each_switch_shows_its_part_of_the_progress_page_again():
    # the percentages: the ring of the one card, the percentage of the stage after the first
    client = _live(**{"figures.percent": "1"}).test_client()
    page = _main(_get(client, "/progress?lang=en"))
    rings = page[page.index('<div class="prog-rings"'):page.index('<section class="card prog-flow"')]
    assert rings.count('class="card prog-ring') == 1 and rings.count("<svg") == 1 and 'data-k="participating_pct">' in rings
    assert re.findall(r'<li class="stage stage-(\w+)">', page) == ["participating", "selected"] and page.count('class="st-pct small muted"') == 1
    data = json.loads(_get(client, "/progress.json"))
    assert "participating_pct" in data["flat"] and list(data["shares"]) == ["participating"] and "testing" not in data["flat"]
    # the institutions assessing their students online: a card and a stage, numbers only
    client = _live(**{"figures.assessment": "1"}).test_client()
    page = _main(_get(client, "/progress?lang=en"))
    rings = page[page.index('<div class="prog-rings"'):page.index('<section class="card prog-flow"')]
    assert rings.count('class="card prog-ring') == 2 and "Institutions assessing their students online" in rings and "<svg" not in rings
    assert "grid-template-columns" not in rings
    assert re.findall(r'<li class="stage stage-(\w+)">', page) == ["participating", "testing", "selected"] and "st-pct" not in page
    data = json.loads(_get(client, "/progress.json"))
    assert data["flat"]["testing"] == 0 and "testing_pct" not in data["flat"] and data["shares"] == {}
    # both: the page as it was before 1.2.189
    client = _live(**{"figures.assessment": "1", "figures.percent": "1"}).test_client()
    page = _main(_get(client, "/progress?lang=en"))
    assert page.count("<svg") >= 2 and page.count('class="st-pct small muted"') == 2
    data = json.loads(_get(client, "/progress.json"))
    assert {"testing", "testing_pct", "tested", "signed_up", "st_testing_pct"} <= set(data["flat"]) and set(data["shares"]) == {"participating", "testing"}


def test_the_wording_in_every_language():
    from kts.i18n import CATALOG
    en = CATALOG["en"]
    assert (en["dash.inst_sel"], en["dash.no_inst"]) == ("Participating Institutions registered", "No Participating Institution registered yet")
    assert en["dash.intro_inst"] == "Where the programme stands in each State/UT: the Participating Institutions registered."
    assert en["pi.states_title_plain"] == "Each row of Annexure-I: the Participating Institutions registered"
    assert en["pg.states_title_plain"] == "The rows of Annexure-I with the most Participating Institutions registered"
    assert en["hub.s_count"] == "Searching the {n} Participating Institutions registered so far"
    assert not [key for key in KEYS if "selected" in en[key]]
    assert len(CATALOG) == 23
    for code, cat in CATALOG.items():
        for key in KEYS:
            assert cat[key] and (code == "en" or cat[key] != en[key]), (code, key)
        # the label stands as it is in the short line of the dashboard and in the heading of the Participating Institutions
        assert cat["dash.inst_sel"] in cat["dash.intro_inst"] and cat["dash.inst_sel"] in cat["pi.states_title_plain"], code
        # ... which is the line with the students who took the test, cut after the label
        assert cat["dash.intro_plain"].startswith(cat["dash.intro_inst"][:-2].rstrip()) or code == "ta", code
        assert cat["hub.s_count"].count("{n}") == 1, code
    assert CATALOG["hi"]["dash.inst_sel"] == "पंजीकृत सहभागी संस्थान" and CATALOG["bn"]["dash.inst_sel"] == "নিবন্ধিত অংশগ্রহণকারী প্রতিষ্ঠান"
    assert CATALOG["ta"]["dash.inst_sel"] == "பதிவு செய்த பங்கேற்கும் கல்வி நிறுவனங்கள்"
    assert CATALOG["ta"]["dash.intro_inst"].endswith(": பதிவு செய்த பங்கேற்கும் கல்வி நிறுவனங்கள்.")
    # the dashboard of every language: the short line, the label, and not the students who took the test
    client = _live().test_client()
    for code, cat in CATALOG.items():
        page = _main(_get(client, f"/dashboard?lang={code}"))
        assert cat["dash.intro_inst"].replace("'", "&#39;") in page and f'<div class="lbl">{cat["dash.inst_sel"]}</div>' in page, code
        assert cat["dash.assessed"].replace("'", "&#39;") not in page and cat["dash.table_title"] not in page, code

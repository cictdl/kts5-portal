"""
The card "From registration to verification" of the page of the progress is hidden (1.2.190). CICT, 16 November 2026, of the page
as 1.2.189 left it: "72 Student selected on merit / 354 Participating Institutions yet to select their student  hide the card".
The switch progress.flow of the Console (off) shows it again; tests/conftest.py switches it on for the tests made before.

    python -m pytest tests/test_progress_flow_1116.py -q
"""
import json
import re

from test_1110 import _app, _get, _main

# the page as the live site has it since 1.2.189 and 1.2.190
LIVE = {"figures.assessment": "0", "dashboard.table": "0", "figures.percent": "0", "progress.flow": "0"}


def test_the_switch_is_off_and_stands_in_the_console():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS, execute, get_setting, init_db
    assert DEFAULT_SETTINGS["progress.flow"] == "0"
    assert {key: kind for key, _label, kind in dict(SETTING_GROUPS)["Site"]}["progress.flow"] == "bool"
    # a database of before 1.2.190 gets it, off
    app = _app()
    with app.app_context():
        execute("DELETE FROM settings WHERE key = 'progress.flow'")
    init_db(app)
    with app.app_context():
        assert get_setting("progress.flow") == "0"


def test_the_progress_page_without_the_card():
    client = _app(**LIVE).test_client()
    page = _main(_get(client, "/progress?lang=en"))
    # no stages, no students selected on merit, no institutions yet to select their student
    assert "prog-flow" not in page and "From registration to verification" not in page and 'class="stage ' not in page
    assert "Student selected on merit" not in page and "yet to select their student" not in page and "prog-behind" not in page
    # what stays: the Participating Institutions registered, the rows of Annexure-I, the milestones
    rings = page[page.index('<div class="prog-rings"'):page.index('<section class="card prog-states"')]
    assert rings.count('class="card prog-ring') == 1 and '<div class="lbl">Participating Institutions registered</div>' in rings
    assert '<div class="num" data-count="5" data-k="participating">5</div>' in rings and ">5 of 1,000</bdi>" in rings
    assert "The rows of Annexure-I with the most Participating Institutions registered" in page and 'class="card prog-miles"' in page
    assert page.index('class="card prog-states"') < page.index('class="card prog-miles"')
    # the figures its script asks for every minute: none of the card
    data = json.loads(_get(client, "/progress.json"))
    flat = data["flat"]
    assert not [k for k in flat if k.startswith("st_") or k in ("selected", "not_selected", "not_registered", "behind", "unregistered")], sorted(flat)
    assert data["widths"] == {} and data["shares"] == {} and flat["participating"] == 5 and flat["participating_of"] == "5 of 1,000"
    assert "as_of_text" in flat
    # in every language
    from kts.i18n import CATALOG
    for code, cat in CATALOG.items():
        page = _main(_get(client, f"/progress?lang={code}"))
        assert cat["pg.flow_title"] not in page and cat["pg.s_selected"] not in page and "prog-flow" not in page, code


def test_the_switch_shows_the_card_again():
    client = _app(**{**LIVE, "progress.flow": "1"}).test_client()
    page = _main(_get(client, "/progress?lang=en"))
    flow = page[page.index('<section class="card prog-flow"'):page.index('<section class="card prog-states"')]
    assert "From registration to verification" in flow and re.findall(r'<li class="stage stage-(\w+)">', flow) == ["participating", "selected"]
    assert "Student selected on merit" in flow and "yet to select their student" in flow and flow.count("</section>") == 1
    # as the other switches leave it: no percentage, no institutions assessing their students online
    assert "st-pct" not in flow and "Institutions assessing their students online" not in page
    data = json.loads(_get(client, "/progress.json"))
    assert {"st_participating", "st_selected", "selected", "not_selected", "behind"} <= set(data["flat"]) and "st_participating" in data["widths"]

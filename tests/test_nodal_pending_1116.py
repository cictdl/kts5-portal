"""
The page of the Nodal Institutions without two things (1.2.195). CICT, 16 November 2026: "hide" - the card "0 / Yet to nominate a
Nodal Officer / 0 of 31" - and "hide" - the button "Download the one-page report (Word)". Two switches of the Console bring them
back; the Console keeps its own link to the report, which is made as before.

    python -m pytest tests/test_nodal_pending_1116.py -q
"""
from test_1107 import _app, _get

PAGE = {"hei.public": "1", "nodal.officers_public": "1"}
HIDDEN = {"nodal.pending": "0", "nodal.report": "0"}
REPORT = "/nodal-institutions/officers-report.docx"
BUTTON = f'href="{REPORT}?lang=en">Download the one-page report (Word)</a>'


def _rings(client):
    page = _get(client, "/nodal-institutions?lang=en")
    return page, page[page.index('class="prog-rings no-rings'):page.index('class="no-steps-h"')]


def test_the_switches_of_the_console():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS["nodal.pending"] == "0" and DEFAULT_SETTINGS["nodal.report"] == "0"
    site = {k: (label, kind) for k, label, kind in dict(SETTING_GROUPS)["Site"]}
    assert site["nodal.pending"] == ("Show the card “Yet to nominate a Nodal Officer” on the page of the Nodal Institutions", "bool")
    assert site["nodal.report"] == ("Show the button “Download the one-page report (Word)” on the page of the Nodal Institutions "
                                    "(the Console's link to the report works either way)", "bool")


def test_the_card_and_the_button_are_hidden_as_the_site_has_them():
    client = _app(**PAGE, **HIDDEN).test_client()
    page, rings = _rings(client)
    assert 'class="prog-rings no-rings n1"' in page and rings.count('class="card prog-ring') == 1
    assert "Nodal Institutions with a Nodal Officer on the portal" in rings
    assert "Yet to nominate a Nodal Officer" not in page
    assert "Download the one-page report (Word)" not in page and REPORT not in page
    # the steps and the key of the table stay
    assert 'class="no-steps"' in page and "Nodal Officer added" in page and "Yet to be nominated" in page
    # the report itself is made as before: the Console links to it
    r = client.get(f"{REPORT}?lang=en")
    assert r.status_code == 200 and r.data[:2] == b"PK"


def test_the_switches_bring_them_back():
    page, rings = _rings(_app(**PAGE, **{"nodal.pending": "1", "nodal.report": "0"}).test_client())
    assert 'class="prog-rings no-rings n2"' in page and rings.count('class="card prog-ring') == 2
    assert "Yet to nominate a Nodal Officer" in rings and "Participating Institutions under a Nodal Officer" not in rings
    assert BUTTON not in page
    page, rings = _rings(_app(**PAGE, **{"nodal.pending": "0", "nodal.report": "1"}).test_client())
    assert rings.count('class="card prog-ring') == 1 and BUTTON in page
    # with the third card of 1.2.164 too: the three, as before
    page, rings = _rings(_app(**PAGE, **{"nodal.pending": "1", "nodal.covered": "1"}).test_client())
    assert 'class="prog-rings no-rings"' in page and rings.count('class="card prog-ring') == 3
    # the third without the second
    page, rings = _rings(_app(**PAGE, **{"nodal.pending": "0", "nodal.covered": "1"}).test_client())
    assert 'class="prog-rings no-rings n2"' in page and rings.count('class="card prog-ring') == 2
    assert "Yet to nominate a Nodal Officer" not in rings and "Participating Institutions under a Nodal Officer" in rings

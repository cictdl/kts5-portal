"""
No ceiling on the institutions selected, for all the States/UTs (1.2.199). CICT, 17 November 2026, with the answer of the Console
"Tamil Nadu and Andaman and Nicobar Islands has 137 accepted institutions: that is the number Annexure-I prescribes for it
(Settings › Participating institutions).": "i cannot select a new institution. No higher ceiling add for all the states".

The ceiling was off since 1.2.178 and had been switched on again in the Settings of the live portal; with the institutions of the
reserve list selected (1.2.198), a State/UT stood above its number and no institution more could be selected. Since 1.2.199 the two
settings of a ceiling (hei.cap_annexure, hei.max_per_state) are no longer among the Settings of the Console, and a database that
holds one switched on has both switched off, once.

    python -m pytest tests/test_no_ceiling_1117.py -q
"""
import json

from conftest import ROOT
from test_nodal_access import _nodal
from test_no_reserve_1117 import _app
from test_public_fixes import _staff
from test_reserve_1111 import _act, _insert, _status
from test_settings_form_1113 import _send, _stored

MARK = "migrate.cap_off_1117"


def test_the_settings_of_a_ceiling_are_not_in_the_console():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS
    keys = [key for _group, items in SETTING_GROUPS for key, _label, _kind in items]
    assert "hei.cap_annexure" not in keys and "hei.max_per_state" not in keys
    assert DEFAULT_SETTINGS["hei.cap_annexure"] == "0" and DEFAULT_SETTINGS["hei.max_per_state"] == "0"
    app = _app()
    admin = _staff(app, "settings.admin@tests.example", "superadmin")
    form = admin.get("/console/settings").get_data(as_text=True)
    assert "hei.cap_annexure" not in form and "hei.max_per_state" not in form and "accepts at most" not in form
    # a page of the Settings of before, sent again with the ceiling ticked, switches nothing on
    page = _send(admin, hei__cap_annexure="1", hei__max_per_state="3", site__banner="The banner of the test")
    assert "Saved 1 setting(s)." in page and _stored(app, "site.banner") == "The banner of the test"
    assert _stored(app, "hei.cap_annexure") == "0" and _stored(app, "hei.max_per_state") == "0"


def test_a_ceiling_that_the_database_holds_is_switched_off_once():
    from kts import heis as HEI
    from kts.db import execute, init_db, set_setting
    app = _app()
    assert _stored(app, MARK) == "1"
    # the live portal as this release finds it: the ceiling of Annexure-I switched on in Settings, and a State/UT above its number
    # with the institutions that came off the reserve list
    with app.app_context():
        set_setting("hei.cap_annexure", "1")
        set_setting("hei.max_per_state", "3")
        execute("DELETE FROM settings WHERE key = ?", (MARK,))
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    for n in range(6):
        _insert(app, f"Selected College {n}", "Puducherry", "Karaikal", "accepted", 80)
    new = _insert(app, "New College", "Puducherry", "Karaikal", "pending", 70)
    answer = _act(officer, new, "accept").get_data(as_text=True)
    assert "Puducherry has 6 accepted institutions: that is the number Annexure-I prescribes for it" in answer and _status(app, new) == "pending"
    # the release: both switched off, and the institution is selected
    init_db(app)
    assert (_stored(app, "hei.cap_annexure"), _stored(app, "hei.max_per_state"), _stored(app, MARK)) == ("0", "0", "1")
    answer = _act(officer, new, "accept").get_data(as_text=True)
    assert "New College: accepted" in answer and "that is the number Annexure-I prescribes" not in answer and _status(app, new) == "accepted"
    # for all the States/UTs: none has a ceiling
    places = json.loads((ROOT / "data" / "states.json").read_text(encoding="utf-8"))
    with app.app_context():
        assert all(HEI.cap_of(place) == 0 for place in places["states"] + places["union_territories"])
        assert HEI.allocation_of("Puducherry") == 5        # the number of Annexure-I stays, as the number the Console shows
    page = officer.get("/console/institutions?state=Puducherry").get_data(as_text=True)
    assert '<td class="num muted">5</td>' in page and '<td class="num"><b>7</b></td>' in page
    # once: the mark stays, and a later start of the portal changes nothing
    init_db(app)
    assert (_stored(app, "hei.cap_annexure"), _stored(app, "hei.max_per_state"), _stored(app, MARK)) == ("0", "0", "1")

"""
The reserve list counted with the Participating Institutions selected on the public pages, and no ceiling on the selection
(1.2.178; CICT, 12 November 2026: "no separate reserve list. add with the selected institutions" - asked, "count together
everywhere"; and "accepted institutions ceiling should not be there").

    python -m pytest tests/test_reserve_counted_1112.py -q
"""
import itertools
import re

from conftest import make_app
from test_nodal_access import _nodal, _token
from test_timeline import _settings, _sql, _start

NUMBERS = itertools.count(1)


def _app():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for key, value in (("hei.end", "2099-12-31"), ("join.on", "1"), ("stats.public", "1"), ("dashboard.public", "1")):
            set_setting(key, value)
    return app


def _insert(app, name, state, status, district="District"):
    from kts.db import execute, utcnow
    with app.app_context():
        return execute("INSERT INTO institutions(ref, name, itype, state, district, inst_key, status, head_name, created_at, updated_at) "
                       "VALUES(?, ?, 'Government college', ?, ?, ?, ?, 'Dr. Head', ?, ?)",
                       (f"KTS5-HEI-7{next(NUMBERS):04d}", name, state, district, f"name:{name.lower()}|{state.lower()}", status, utcnow(),
                        utcnow()))


def _portal():
    app = _app()
    for n in range(3):
        _insert(app, f"Selected Puducherry {n}", "Puducherry", "accepted", "Karaikal")
    for n in range(4):
        _insert(app, f"Reserve Puducherry {n}", "Puducherry", "reserve", "Mahe")
    _insert(app, "Reserve Goa College", "Goa", "reserve", "North Goa")
    _insert(app, "Pending Kerala College", "Kerala", "pending")
    return app


def test_counted_together_on_every_public_page():
    from kts import dashboard as D
    from kts import drive as DRIVE
    from kts import public as P
    app = _portal()
    client = app.test_client()
    with app.app_context():
        by = {r["state"]: r for r in D.figures()["states"]}
        assert (by["Puducherry"]["inst_sel"], by["Goa"]["inst_sel"], by["Kerala"]["inst_sel"]) == (7, 1, 0)
        assert D._pipeline()["counts"]["participating"] == 8
        DRIVE._CACHE["data"] = None
        assert (DRIVE.table()["Puducherry"]["participating"], DRIVE.table()["Goa"]["participating"]) == (7, 1)
    with app.test_request_context():
        rows, total = P._nodal_table()
        assert {r["state"]: r["now"] for r in rows}["Puducherry"] == 7 and total["now"] == 8
    # the dashboard: 7 of the 5 of Annexure-I for Puducherry, no card or column of the reserve list
    page = client.get("/dashboard?lang=en").get_data(as_text=True)
    assert "Reserve list" not in page
    tile = page[page.index('href="#d-PY"'):]
    assert '<span class="dash-n" dir="ltr">7/5</span>' in tile[:tile.index("</a>")]
    # /institutions at a glance and the home page
    page = client.get("/institutions?lang=en").get_data(as_text=True)
    pi = page[page.index('<section class="pi"'):page.index("<p><b>")]
    assert '<div class="num">8</div><div class="lbl">Participating institutions</div>' in pi
    assert '<div class="num">2</div><div class="lbl">States and UTs</div>' in pi and '<div class="num">3</div><div class="lbl">Districts reached</div>' in pi
    home = client.get("/?lang=en").get_data(as_text=True)
    glance = home[home.index("<h2>At a glance</h2>"):]
    cards = re.findall(r'<div class="num">([^<]+)</div><div class="lbl">([^<]+)</div>', glance[:glance.index("</section>")])
    assert [(n.strip(), label) for n, label in cards][:2] == [("8", "Participating institutions"), ("2", "States and UTs")]
    # the State/UT page
    with app.app_context():
        code = DRIVE.code_of("Puducherry")
        DRIVE._CACHE["data"] = None
    assert client.get(f"/join/{code}?lang=en").status_code == 200
    # the reserve list kept off the public pages: the institutions selected only
    from kts.db import set_setting
    with app.app_context():
        set_setting("hei.reserve_public", "0")
        assert {r["state"]: r for r in D.figures()["states"]}["Puducherry"]["inst_sel"] == 3
        assert D._pipeline()["counts"]["participating"] == 3
        DRIVE._CACHE["data"] = None
        assert DRIVE.table()["Puducherry"]["participating"] == 3
    page = client.get("/institutions?lang=en").get_data(as_text=True)
    pi = page[page.index('<section class="pi"'):page.index("<p><b>")]
    assert '<div class="num">3</div><div class="lbl">Participating institutions</div>' in pi and "Reserve Puducherry" not in page


def test_the_console_keeps_them_apart():
    app = _portal()
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    page = officer.get("/console/institutions?state=Puducherry").get_data(as_text=True)
    summary = page[page.index("<tbody>"):page.index("</tbody>")]
    row = summary[summary.index("Puducherry"):]
    numbers = re.sub(r"<[^>]+>", " ", row[:row.index("</tr>")]).split()[1:]
    # Annexure-I, identified, pending, selected, reserve, ...
    assert numbers[:5] == ["5", "0", "0", "3", "4"]


def test_no_ceiling_on_the_selection():
    from kts import heis as HEI
    from kts.db import DEFAULT_SETTINGS, query
    assert DEFAULT_SETTINGS["hei.cap_annexure"] == "0"
    app = _app()
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    ids = [_insert(app, f"Pending Puducherry {n}", "Puducherry", "pending") for n in range(7)]
    with app.app_context():
        assert HEI.cap_of("Puducherry") == 0 and HEI.allocation_of("Puducherry") == 5
    for iid in ids:
        r = officer.post("/console/institutions", data={"_csrf": _token(officer), "id": iid, "action": "accept"}, follow_redirects=True)
        assert "that is the number Annexure-I prescribes" not in r.get_data(as_text=True)
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM institutions WHERE status = 'accepted'", one=True)["n"] == 7   # 7 of the 5


def test_the_live_ceiling_is_switched_off_once():
    # a database of 1.2.177: the ceiling on, as its default was; the update switches it off once, and CICT may switch it on again
    app = _app()
    _sql(app, "UPDATE settings SET value = '1' WHERE key = 'hei.cap_annexure'")
    _sql(app, "DELETE FROM settings WHERE key = 'migrate.cap_off_1112'")
    again = _start(app)
    settings = _settings(again)
    assert settings["hei.cap_annexure"] == "0" and settings["migrate.cap_off_1112"] == "1"
    _sql(again, "UPDATE settings SET value = '1' WHERE key = 'hei.cap_annexure'")
    third = _start(again)
    assert _settings(third)["hei.cap_annexure"] == "1"

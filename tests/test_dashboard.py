"""
KTS 5.0 by State/UT (version 1.2.122): the live public dashboard /dashboard - for each State/UT the number to be selected
(Annexure-I), the institutions registered and selected, the students who took an institution's online test, and the
student delegates registered and verified; a grid of squares (no map), a table with every figure, counts only, never a
name; linked from At a glance and the sitemap; Console > Settings dashboard.public.

    python -m pytest tests -q
"""
import re

from markupsafe import escape

from conftest import add_candidates, make_app
from test_progress import _inst, _student


def _portal():
    """Tamil Nadu: one institution selected with two students tested, one registered; Kerala: one waiting; Goa: one only
    identified by the Nodal Officer (not registered); three student delegates, one verified, one withdrawn."""
    from kts.db import execute
    app = make_app(ADMIN_PASSWORD=None)
    tn = _inst(app, "Presidency College", state="Tamil Nadu")
    _student(app, tn, "Student One", tested=True)
    _student(app, tn, "Student Two", tested=True)
    _student(app, tn, "Student Three")
    _inst(app, "Kerala Waiting College", state="Kerala", status="pending")
    _inst(app, "Goa Identified College", state="Goa", status="identified")
    students = add_candidates(app, 3)
    with app.app_context():
        execute("UPDATE applications SET college_state = 'Tamil Nadu'")
        execute("UPDATE applications SET status = 'verified' WHERE app_no = ?", (students[0]["app_no"],))
        execute("UPDATE applications SET status = 'withdrawn' WHERE app_no = ?", (students[2]["app_no"],))
    return app


def test_the_figures():
    from kts.dashboard import GRID, figures, shade
    app = _portal()
    with app.app_context():
        data = figures()
    by = {r["state"]: r for r in data["states"]}
    # the 36 States/UTs, those of Annexure-I first; each has its square
    assert len(data["states"]) == 36 and len(GRID) == 36 and all(r["grid"] for r in data["states"])
    assert data["states"][0]["state"] == "Andhra Pradesh" and data["states"][-1]["state"] == "Lakshadweep"
    assert len({(r, c) for r, c, _ in GRID.values()}) == 36
    tn = by["Tamil Nadu"]
    assert (tn["to_select"], tn["inst_reg"], tn["inst_sel"], tn["assessed"], tn["registered"], tn["verified"]) == (150, 1, 1, 2, 2, 1)
    assert tn["shade"] == "b1" and tn["share"] == 1
    assert (by["Kerala"]["inst_reg"], by["Kerala"]["inst_sel"], by["Kerala"]["shade"]) == (1, 0, "b0")
    assert by["Goa"]["inst_reg"] == 0 and by["Ladakh"]["to_select"] is None and by["Ladakh"]["shade"] == "nb"
    assert data["total"] == {"to_select": 1000, "inst_reg": 2, "inst_sel": 1, "assessed": 2, "registered": 2, "verified": 1}
    assert [shade(n, 100) for n in (0, 1, 25, 26, 50, 51, 75, 76, 140)] == ["b0", "b1", "b1", "b2", "b2", "b3", "b3", "b4", "b4"]
    assert shade(3, None) == "nb"


def test_the_page():
    app = _portal()
    client = app.test_client()
    page = client.get("/dashboard?lang=en").get_data(as_text=True)
    assert "<h1>KTS 5.0 by State/UT</h1>" in page and "Live figures, as on " in page
    kpis = page[page.index('class="grid grid-3 dash-kpis"'):page.index('class="card dash-map"')]
    assert re.findall(r'<div class="num">([\d,]+)</div>', kpis) == ["1,000", "2", "1", "2", "2", "1"]
    assert "2 of 1,000" in kpis
    # the squares: Tamil Nadu 2 of 150, Ladakh without a number
    assert page.count('class="dash-tile ') == 36
    assert ('<a class="dash-tile b1" href="#st-TN">\n          <b dir="ltr">TN</b>\n          <span class="dash-n" dir="ltr">2/150</span>') in page
    assert '<a class="dash-tile nb" href="#st-LA">' in page and "No number in Annexure-I" in page
    # the table: every figure, with the total; the square's link leads to the row
    table = page[page.index('class="table dash-table"'):]
    assert table.count("<tr id=\"st-") == 36 and '<tr id="st-TN">' in table
    row = table[table.index('<tr id="st-TN">'):table.index("</tr>", table.index('<tr id="st-TN">'))]
    assert re.findall(r'<td class="num">(\d+|–)', row) == ["150", "1", "1", "2", "2", "1"]
    # counts only: no institution, no student, no e-mail
    for name in ("Presidency College", "Kerala Waiting College", "Student One", "Campus Student 1", "@"):
        assert name not in page.split('id="main"')[1].split("</main>")[0], name


def test_in_every_language_and_where_it_is_found():
    from kts.i18n import CATALOG, place
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    for code, catalogue in CATALOG.items():
        page = client.get(f"/dashboard?lang={code}").get_data(as_text=True)
        assert f"<h1>{escape(catalogue['dash.title'])}</h1>" in page, code
        assert f'<th scope="row">{escape(place("Tamil Nadu", code))}</th>' in page, code
        home = client.get(f"/?lang={code}").get_data(as_text=True)
        assert f'<a class="small" href="/dashboard">{escape(catalogue["dash.link"])}' in home, code
    assert "/dashboard</loc>" in client.get("/sitemap.xml").get_data(as_text=True)


def test_the_switch():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("dashboard.public", "0")
    client = app.test_client()
    assert client.get("/dashboard").status_code == 404
    assert 'href="/dashboard"' not in client.get("/?lang=en").get_data(as_text=True)

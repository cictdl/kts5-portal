"""
KTS 5.0 by State/UT (version 1.2.122): the live public dashboard /dashboard - for each State/UT the number to be selected
(Annexure-I), the institutions registered and selected, the students who took an institution's online test, and the
student delegates registered and verified; a grid of squares (no map), a table with every figure; linked from At a glance
and the sitemap; Console > Settings dashboard.public. Since 1.2.124 a block for each State/UT: its Nodal Officers, its
Participating Institutions, and under each its student delegate by name once verified (dashboard.names); never another
detail of a student.

    python -m pytest tests -q
"""
import re

from markupsafe import escape

from conftest import add_candidates, make_app
from test_progress import _inst, _student


def _portal():
    """Tamil Nadu: three institutions selected - Presidency College (two students tested, its student verified), Loyola
    College (its student registered, not yet verified), Madras Christian College (nothing yet); Kerala: one waiting; Goa:
    one only identified by the Nodal Officer (not registered); a third application withdrawn; the Nodal Officer of Tamil
    Nadu."""
    from kts.db import execute, query, utcnow
    app = make_app(ADMIN_PASSWORD=None)
    tn = _inst(app, "Presidency College", state="Tamil Nadu")
    _student(app, tn, "Student One", tested=True)
    _student(app, tn, "Student Two", tested=True)
    _student(app, tn, "Student Three")
    loyola = _inst(app, "Loyola College", state="Tamil Nadu")
    _inst(app, "Madras Christian College", state="Tamil Nadu")
    _inst(app, "Kerala Waiting College", state="Kerala", status="pending")
    _inst(app, "Goa Identified College", state="Goa", status="identified")
    students = add_candidates(app, 3)
    with app.app_context():
        execute("UPDATE applications SET college_state = 'Tamil Nadu'")
        ids = {r["app_no"]: r["id"] for r in query("SELECT id, app_no FROM applications")}
        execute("UPDATE applications SET status = 'verified' WHERE app_no = ?", (students[0]["app_no"],))
        execute("UPDATE applications SET status = 'withdrawn' WHERE app_no = ?", (students[2]["app_no"],))
        execute("UPDATE institutions SET application_id = ? WHERE id = ?", (ids[students[0]["app_no"]], tn))
        execute("UPDATE institutions SET application_id = ? WHERE id = ?", (ids[students[1]["app_no"]], loyola))
        execute("INSERT INTO users(email, name, password_hash, role, active, must_change_password, created_at, designation, phone, states) "
                "VALUES(?,?,?,?,1,0,?,?,?,?)", ("nodal.tn@cutn.example", "Dr. Nodal Officer", "x", "nodal", utcnow(),
                                                "Professor", "9444000001", "Tamil Nadu"))
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
    assert (tn["to_select"], tn["inst_reg"], tn["inst_sel"], tn["assessed"], tn["registered"], tn["verified"]) == (150, 3, 3, 2, 2, 1)
    assert tn["shade"] == "b1" and tn["share"] == 1
    assert (by["Kerala"]["inst_reg"], by["Kerala"]["inst_sel"], by["Kerala"]["shade"]) == (1, 0, "b0")
    assert by["Goa"]["inst_reg"] == 0 and by["Ladakh"]["to_select"] is None and by["Ladakh"]["shade"] == "nb"
    assert data["total"] == {"to_select": 1000, "inst_reg": 4, "inst_sel": 3, "assessed": 2, "registered": 2, "verified": 1}
    assert [shade(n, 100) for n in (0, 1, 25, 26, 50, 51, 75, 76, 140)] == ["b0", "b1", "b1", "b2", "b2", "b3", "b3", "b4", "b4"]
    assert shade(3, None) == "nb"


def test_the_page():
    app = _portal()
    client = app.test_client()
    page = client.get("/dashboard?lang=en").get_data(as_text=True)
    assert "<h1>KTS 5.0 by State/UT</h1>" in page and "Live figures, as on " in page
    kpis = page[page.index('class="grid grid-3 dash-kpis"'):page.index('class="card dash-map"')]
    assert re.findall(r'<div class="num">([\d,]+)</div>', kpis) == ["1,000", "4", "3", "2", "2", "1"]
    assert "2 of 1,000" in kpis
    # the squares: Tamil Nadu 2 of 150, Ladakh without a number; each leads to the block of its State/UT
    assert page.count('class="dash-tile ') == 36
    assert ('<a class="dash-tile b1" href="#d-TN">\n          <b dir="ltr">TN</b>\n          <span class="dash-n" dir="ltr">2/150</span>') in page
    assert '<a class="dash-tile nb" href="#d-LA">' in page and "No number in Annexure-I" in page
    # the table: every figure, with the total
    table = page[page.index('class="table dash-table"'):page.index('class="dash-details"')]
    assert table.count("<tr id=\"st-") == 36 and '<th scope="row"><a href="#d-TN">Tamil Nadu</a></th>' in table
    row = table[table.index('<tr id="st-TN">'):table.index("</tr>", table.index('<tr id="st-TN">'))]
    assert re.findall(r'<td class="num">(\d+|–)', row) == ["150", "3", "3", "2", "2", "1"]


def test_the_block_of_each_state():
    from kts.db import set_setting
    app = _portal()
    client = app.test_client()
    page = client.get("/dashboard?lang=en").get_data(as_text=True)
    main = page.split('id="main"')[1].split("</main>")[0]
    blocks = main[main.index('class="dash-details"'):]
    # the 31 States/UTs of Annexure-I, and none without a number and without institutions
    assert blocks.count('<details class="card dash-state"') == 31 and 'id="d-LA"' not in blocks
    tn = blocks[blocks.index('id="d-TN"'):]
    tn = tn[:tn.index("</details>")]
    assert "Central University of Tamil Nadu" in tn
    assert "<b>Dr. Nodal Officer</b>" in tn and 'href="mailto:nodal.tn@cutn.example"' in tn and 'href="tel:9444000001"' in tn
    # the verified student by name with the institution; the one awaiting verification not named; nothing else of a student
    assert "Presidency College" in tn and "✓ <bdi>Student delegate: Campus Student 1</bdi>" in tn
    assert "Loyola College" in tn and "Student registered, awaiting verification" in tn and "Campus Student 2" not in main
    assert "Madras Christian College" in tn and "No student registered yet" in tn
    for detail in ("campus1@tests.example", "9876500001", "2004-05-06", "Student One", "Kerala Waiting College", "Goa Identified College"):
        assert detail not in main, detail
    # the switches of the Console: names, Nodal Officers, institutions
    with app.app_context():
        set_setting("dashboard.names", "0")
    page = client.get("/dashboard?lang=en").get_data(as_text=True)
    assert "Campus Student 1" not in page and "✓ Verified by the Nodal Officers" in page
    with app.app_context():
        set_setting("nodal.officers_public", "0")
        set_setting("hei.public", "0")
    page = client.get("/dashboard?lang=en").get_data(as_text=True)
    assert "nodal.tn@cutn.example" not in page and "Presidency College" not in page
    assert page.count("No Participating Institution selected yet") == 31


def test_in_every_language_and_where_it_is_found():
    from kts.i18n import CATALOG, place
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    for code, catalogue in CATALOG.items():
        page = client.get(f"/dashboard?lang={code}").get_data(as_text=True)
        assert f"<h1>{escape(catalogue['dash.title'])}</h1>" in page, code
        assert f'<a href="#d-TN">{escape(place("Tamil Nadu", code))}</a>' in page, code
        assert str(escape(catalogue["dash.details_title"])) in page, code
        home = client.get(f"/?lang={code}").get_data(as_text=True)
        # a bold saffron button with an icon beside At a glance (1.2.123)
        assert '<a class="btn saffron dash-cta" href="/dashboard"' in home, code
        assert f'<span aria-hidden="true" style="font-size:1.35rem;line-height:1">📊</span> {escape(catalogue["dash.link"])}' in home, code
    assert "/dashboard</loc>" in client.get("/sitemap.xml").get_data(as_text=True)


def test_the_switch():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("dashboard.public", "0")
    client = app.test_client()
    assert client.get("/dashboard").status_code == 404
    assert 'href="/dashboard"' not in client.get("/?lang=en").get_data(as_text=True)

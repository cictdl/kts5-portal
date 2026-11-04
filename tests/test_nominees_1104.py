"""
The students selected on merit in the Console (1.2.157; the user, 4 November 2026: "Student selected on merit should be seen on the
console of the Portal admin"): every student a Participating Institution has selected on its page, before and after the student
registers, with the institution, the assessment and the registration; the figures, the filters, the scope of a Nodal Officer, the
Excel, the menu and the dashboard's tile.

    python -m pytest tests/test_nominees_1104.py -q
"""
import io

from conftest import add_candidates, make_app
from test_nodal_access import _nodal
from test_progress import _inst, _student
from test_public_fixes import _staff


def _world():
    """Kerala: Alpha College (its student tested online and selected, not registered yet), Beta College (its student entered by the
    coordinator, registered, awaiting verification); Tamil Nadu: Gamma College (its student registered and verified), Delta College
    (no student selected yet); Kerala: a pending institution."""
    from kts.db import execute, query
    app = make_app(ADMIN_PASSWORD=None)
    alpha = _inst(app, "Alpha College", state="Kerala", test_on=1)
    beta = _inst(app, "Beta College", state="Kerala")
    gamma = _inst(app, "Gamma College", state="Tamil Nadu")
    _inst(app, "Delta College", state="Tamil Nadu")
    _inst(app, "Waiting College", state="Kerala", status="pending")
    a = _student(app, alpha, "Anu Student", tested=True)
    b = _student(app, beta, "Balu Student")
    c = _student(app, gamma, "Chitra Student")
    students = add_candidates(app, 2)
    with app.app_context():
        execute("UPDATE campus_students SET course = 'B.A. Tamil', roll_no = '21TA007', source = 'entered' WHERE id = ?", (b,))
        ids = {r["app_no"]: r["id"] for r in query("SELECT id, app_no FROM applications")}
        execute("UPDATE applications SET status = 'submitted' WHERE app_no = ?", (students[0]["app_no"],))
        execute("UPDATE applications SET status = 'verified' WHERE app_no = ?", (students[1]["app_no"],))
        for iid, sid, app_id in ((alpha, a, None), (beta, b, ids[students[0]["app_no"]]), (gamma, c, ids[students[1]["app_no"]])):
            execute("UPDATE institutions SET winner_id = ?, winner_at = '2026-11-04T10:30:00+00:00', application_id = ? WHERE id = ?",
                    (sid, app_id, iid))
    return app, students


def test_the_admin_sees_every_student_selected_on_merit():
    app, students = _world()
    admin = _staff(app, "admin@tests.example", "admin")
    page = admin.get("/console/nominees").get_data(as_text=True)
    assert "<title>Students selected on merit" in page
    for name in ("Anu Student", "Balu Student", "Chitra Student"):
        assert f"<b>{name}</b>" in page, name
    # the figures: three selected, one institution yet to select; one not registered, one awaiting verification, one verified
    for label, n in (("Selected on merit", 3), ("Not registered yet", 1), ("Registered", 1), ("Verified", 1)):
        assert f'<div class="lbl">{label}</div><div class="num">{n}</div>' in page, label
    assert "1 Participating Institution(s) yet to select" in page
    # the row of each: the online test, the institution's own assessment, the registration
    anu = page[page.index("<b>Anu Student</b>"):]
    anu = anu[:anu.index("</tr>")]
    assert "online test: 80.0 marks" in anu and "not registered yet" in anu and "Alpha College" in anu and "Kerala" in anu
    balu = page[page.index("<b>Balu Student</b>"):]
    balu = balu[:balu.index("</tr>")]
    assert "B.A. Tamil · roll no. 21TA007" in balu and "assessed by the institution" in balu
    assert f"<code>{students[0]['app_no']}</code>" in balu and ">submitted</span>" in balu
    assert '<span class="pill green">verified</span>' in page
    assert "Waiting College" not in page and "Delta College" not in page


def test_the_filters():
    app, _students = _world()
    admin = _staff(app, "admin@tests.example", "admin")

    def names(query):
        page = admin.get("/console/nominees?" + query).get_data(as_text=True)
        return [n for n in ("Anu Student", "Balu Student", "Chitra Student") if f"<b>{n}</b>" in page]

    assert names("stage=link") == ["Anu Student"]
    assert names("stage=registered") == ["Balu Student"]
    assert names("stage=verified") == ["Chitra Student"]
    assert names("state=Tamil+Nadu") == ["Chitra Student"]
    assert names("q=21TA007") == ["Balu Student"] and names("q=Gamma") == ["Chitra Student"]
    assert names("stage=nonsense") == ["Anu Student", "Balu Student", "Chitra Student"]


def test_a_nodal_officer_sees_the_students_of_the_officers_states():
    app, _students = _world()
    kerala = _nodal(app, "nodal.kerala@tests.example", ["Kerala"])
    page = kerala.get("/console/nominees").get_data(as_text=True)
    assert "<b>Anu Student</b>" in page and "<b>Balu Student</b>" in page and "<b>Chitra Student</b>" not in page
    assert "You see the institutions of <b>Kerala and Lakshadweep</b>" in page
    assert "<b>Chitra Student</b>" not in kerala.get("/console/nominees?state=Tamil+Nadu").get_data(as_text=True)


def test_the_excel():
    import openpyxl
    app, students = _world()
    admin = _staff(app, "admin@tests.example", "admin")
    r = admin.get("/console/nominees.xlsx")
    assert r.status_code == 200 and "KTS5-students-selected-on-merit.xlsx" in r.headers["Content-Disposition"]
    rows = list(openpyxl.load_workbook(io.BytesIO(r.data)).active.values)
    assert rows[0][:6] == ("S. No.", "State/UT", "Participating Institution", "Reference", "District/City", "Student")
    by = {row[5]: row for row in rows[1:]}
    assert set(by) == {"Anu Student", "Balu Student", "Chitra Student"}
    assert by["Anu Student"][15] == "not registered yet" and by["Anu Student"][12] == 80
    assert by["Balu Student"][7] == "21TA007" and by["Balu Student"][14] == students[0]["app_no"] and by["Balu Student"][15] == "submitted"
    assert by["Chitra Student"][15] == "verified" and by["Chitra Student"][16] == "Coordinator Gamma College"
    # a Nodal Officer's Excel: the officer's States/UTs only
    kerala = _nodal(app, "nodal.kerala@tests.example", ["Kerala"])
    rows = list(openpyxl.load_workbook(io.BytesIO(kerala.get("/console/nominees.xlsx").data)).active.values)
    assert sorted(row[5] for row in rows[1:]) == ["Anu Student", "Balu Student"]


def test_the_menu_and_the_dashboard():
    app, _students = _world()
    admin = _staff(app, "admin@tests.example", "admin")
    home = admin.get("/console/").get_data(as_text=True)
    assert 'href="/console/nominees">🎓 Selected on merit</a>' in home
    tile = home[home.index('<a class="kpi" href="/console/nominees"'):]
    tile = tile[:tile.index("</a>")]
    assert '<div class="lbl">Selected on merit</div><div class="num">3</div>' in tile and "1 not registered yet" in tile
    assert "waitlisted" not in home
    # no Console, no list
    r = app.test_client().get("/console/nominees")
    assert r.status_code == 302 and "/console/login" in r.headers["Location"]

"""
The pairs of Annexure-I of the D.O. letter of 31 October 2026 (version 1.2.135): five Union Territories with a State under one
Nodal Institution and one number - Gujarat and Dadra and Nagar Haveli and Daman and Diu; Kerala and Lakshadweep; Punjab and
Chandigarh; Tamil Nadu and Andaman and Nicobar Islands; Jammu and Kashmir and Ladakh. An institution and a student keep their
own State/UT; the Nodal Institution, the number and the reserve list, the Nodal Officers' scope and the figures State/UT by
State/UT are those of the row of Annexure-I.

    python -m pytest tests -q
"""
import json
import sqlite3

from conftest import ROOT, make_app
from test_institutions import _app, _apply
from test_nodal_access import _nodal, _token
from test_progress import _inst

PAIRS = {"Dadra and Nagar Haveli and Daman and Diu": "Gujarat", "Lakshadweep": "Kerala", "Chandigarh": "Punjab",
         "Andaman and Nicobar Islands": "Tamil Nadu", "Ladakh": "Jammu and Kashmir"}
TITLE = "State/UT-wise list of Nodal Higher Educational Institutions"


def _kerala_full(app):
    """Kerala's 21 Participating Institutions, selected."""
    from kts.db import execute, utcnow
    with app.app_context():
        for n in range(21):
            execute("INSERT INTO institutions(ref, name, itype, state, district, inst_key, status, created_at, updated_at) "
                    "VALUES(?, ?, 'Government college', 'Kerala', 'Thrissur', ?, 'accepted', ?, ?)",
                    (f"KTS5-HEI-8{n:04d}", f"Kerala College {n}", f"name:kerala college {n}|kerala", utcnow(), utcnow()))


def test_the_rows_of_annexure_i():
    heis = json.loads((ROOT / "data" / "nodal_heis.json").read_text(encoding="utf-8"))
    assert {c: h["state"] for h in heis for c in h.get("covers", [])} == PAIRS
    assert [h["state"] for h in heis if h.get("covers")] == ["Gujarat", "Kerala", "Punjab", "Tamil Nadu", "Jammu and Kashmir"]
    assert len(heis) == 31 and sum(h["allocation"] for h in heis) == 1000
    from kts import heis as HEI
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        assert HEI.nodal_state_of("Lakshadweep") == "Kerala" and HEI.nodal_state_of("Kerala") == "Kerala" and HEI.nodal_state_of("Goa") == "Goa"
        assert HEI.nodal_state_of("Atlantis") == "Atlantis" and HEI.row_of("Atlantis") is None and HEI.row_of("Ladakh")["allocation"] == 11
        assert HEI.group_of("Ladakh") == HEI.group_of("Jammu and Kashmir") == ["Jammu and Kashmir", "Ladakh"] and HEI.group_of("Goa") == ["Goa"]
        assert HEI.with_covered(["Kerala", "Goa"]) == ["Kerala", "Lakshadweep", "Goa"] and HEI.with_covered(["Lakshadweep"]) == ["Lakshadweep"]
        assert HEI.with_covered(["Lakshadweep", "Kerala"]) == ["Lakshadweep", "Kerala"]
        assert (HEI.allocation_of("Lakshadweep"), HEI.allocation_of("Chandigarh"), HEI.allocation_of("Ladakh")) == (21, 21, 11)
        assert (HEI.allocation_of("Dadra and Nagar Haveli and Daman and Diu"), HEI.allocation_of("Andaman and Nicobar Islands")) == (50, 50)
        from kts.db import set_setting
        set_setting("hei.cap_annexure", "1")   # the ceiling, off by default since 1.2.178, switched on in the Console
        assert (HEI.cap_of("Lakshadweep"), HEI.cap_of("Ladakh"), HEI.cap_of("Andaman and Nicobar Islands")) == (21, 11, 50)
        assert HEI.label_of("Lakshadweep", "en") == HEI.label_of("Kerala", "en") == "Kerala and Lakshadweep"
        assert HEI.label_of("Gujarat", "en") == "Gujarat and Dadra and Nagar Haveli and Daman and Diu" and HEI.label_of("Goa", "en") == "Goa"
        assert HEI.label_of("Kerala", "ta") == "கேரளா மற்றும் லட்சத்தீவு" and HEI.label_of("Kerala", "hi") == "केरल और लक्षद्वीप"
        assert HEI.label_of("Kerala", "ml") == "കേരളം, ലക്ഷദ്വീപ് എന്നിവ"
        assert HEI.unit_name("Kerala") == "Kerala" and HEI.unit_name("Lakshadweep") == "Kerala and Lakshadweep" and HEI.unit_name("Goa") == "Goa"
    # the three texts, in the 23 languages, with their placeholders
    from kts.i18n import CATALOG
    for code, catalogue in CATALOG.items():
        assert "{a}" in catalogue["nodal.pair"] and "{b}" in catalogue["nodal.pair"] and "{state}" in catalogue["dash.with"], code
        assert catalogue["dash.paired"], code


def test_the_public_pages_name_the_row_as_the_letter_does():
    from kts.db import execute, query, utcnow
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("INSERT INTO institutions(ref, name, itype, state, district, inst_key, status, created_at, updated_at) "
                "VALUES('KTS5-HEI-00001', 'Lakshadweep Arts College', 'Government college', 'Lakshadweep', 'Kavaratti', "
                "'name:x|lakshadweep', 'accepted', ?, ?)", (utcnow(), utcnow()))
    client = app.test_client()
    page = client.get("/nodal-institutions?lang=en").get_data(as_text=True)
    for label in ("Gujarat and Dadra and Nagar Haveli and Daman and Diu", "Kerala and Lakshadweep", "Punjab and Chandigarh",
                  "Tamil Nadu and Andaman and Nicobar Islands", "Jammu and Kashmir and Ladakh"):
        assert f"<td>{label}</td>" in page, label
    assert "<td>Lakshadweep</td>" not in page and "<td>Kerala</td>" not in page and page.count('<td lang="en" dir="ltr">') == 31
    # the Lakshadweep institution counts with Kerala; no column of the number to be selected (1.2.179)
    row = page.split("<td>Kerala and Lakshadweep</td>")[1].split("</tr>")[0]
    assert '<td class="num"><b>21</b></td>' not in row and ("#st-kerala\">1</a></td>" in row or '<td class="num">1</td>' in row)
    assert ">1,000</th>" not in page
    tamil = client.get("/nodal-institutions?lang=ta").get_data(as_text=True)
    assert "<td>கேரளா மற்றும் லட்சத்தீவு</td>" in tamil and "<td>பஞ்சாப் மற்றும் சண்டிகர்</td>" in tamil
    assert "<td>Kerala and Lakshadweep</td>" in client.get("/partners?lang=en").get_data(as_text=True)
    # the list of the participating institutions: under its own Union Territory, with the Nodal Institution of the row
    lst = client.get("/institutions?lang=en").get_data(as_text=True)
    assert 'id="st-lakshadweep"' in lst and "Lakshadweep Arts College" in lst
    assert "Nodal Institution: <span lang=\"en\" dir=\"ltr\">Central University of Kerala</span>" in lst or "Central University of Kerala" in lst
    # the circular
    with app.app_context():
        body = query("SELECT body FROM notices WHERE title = ?", (TITLE,), one=True)["body"]
    assert "\n7. Gujarat and Dadra and Nagar Haveli and Daman and Diu: Central University of Gujarat (50)\n" in body
    assert "\n12. Kerala and Lakshadweep: Central University of Kerala (21)\n" in body
    assert "\n30. Jammu and Kashmir and Ladakh: Central University of Jammu (11)\n" in body and "\n31. Puducherry: Pondicherry University (5)\n" in body
    assert ("Annexure-I pairs Dadra and Nagar Haveli and Daman and Diu with Gujarat; Lakshadweep with Kerala; Chandigarh with Punjab; "
            "Andaman and Nicobar Islands with Tamil Nadu; Ladakh with Jammu and Kashmir. The institutions of these Union Territories "
            "register with their own Union Territory and are selected by the Nodal Institution of the State, within the number "
            "prescribed for the two together.") in body


def test_the_live_circular_takes_the_pairs_once():
    # the live database holds the circular as 1.2.133 wrote it: at the next start it names each row as the letter does, once; a
    # circular CICT rewrites afterwards stays as it is
    from config import Config
    from kts import create_app
    from kts.db import query
    app = make_app(ADMIN_PASSWORD=None)
    old = ("As communicated by the Ministry of Education ...\n\n1. Andhra Pradesh: Central University of Andhra Pradesh (50)\n"
           "7. Gujarat: Central University of Gujarat (50)\n12. Kerala: Central University of Kerala (21)\n\nTotal: 1,000 Participating HEIs.")
    conn = sqlite3.connect(str(app.config["DATABASE"]))
    conn.execute("UPDATE notices SET body = ? WHERE title = ?", (old, TITLE))
    conn.execute("DELETE FROM settings WHERE key = 'migrate.annex1_pairs.notice'")
    conn.commit()
    conn.close()
    names = ("INSTANCE_DIR", "DATABASE", "UPLOAD_DIR")
    again = create_app(type("Again", (Config,), {n: app.config[n] for n in names} | {"ADMIN_PASSWORD": None}))
    with again.app_context():
        body = query("SELECT body FROM notices WHERE title = ?", (TITLE,), one=True)["body"]
        assert query("SELECT value FROM settings WHERE key = 'migrate.annex1_pairs.notice'", one=True)["value"] == "1"
    assert "7. Gujarat and Dadra and Nagar Haveli and Daman and Diu: Central University of Gujarat (50)" in body
    assert "12. Kerala and Lakshadweep: Central University of Kerala (21)" in body and "up to 18 November 2026" in body
    conn = sqlite3.connect(str(app.config["DATABASE"]))
    conn.execute("UPDATE notices SET body = 'CICT wrote this.' WHERE title = ?", (TITLE,))
    conn.execute("DELETE FROM settings WHERE key = 'migrate.annex1_pairs.notice'")
    conn.commit()
    conn.close()
    third = create_app(type("Third", (Config,), {n: app.config[n] for n in names} | {"ADMIN_PASSWORD": None}))
    with third.app_context():
        assert query("SELECT body FROM notices WHERE title = ?", (TITLE,), one=True)["body"] == "CICT wrote this."


def test_a_union_territory_institution_goes_to_the_nodal_institution_of_its_state():
    from kts import nodal as NODAL
    from kts.campus import _names
    from kts.db import query
    from kts.progress import _nodal_line
    app = _app()
    _kerala_full(app)
    # a college of Lakshadweep applies: it keeps its own Union Territory, the Nodal Officer of Kerala hears of it
    officer = _nodal(app, "nodal.kerala9@tests.example", ["Kerala"])
    assert _apply(app.test_client(), name="Kavaratti Arts College", state="Lakshadweep", aishe_code="", head_email="h@lk.example",
                  coord_email="c@lk.example").status_code == 302
    with app.app_context():
        row = query("SELECT * FROM institutions WHERE name = 'Kavaratti Arts College'", one=True)
        mail = query("SELECT body FROM outbox WHERE to_addr = 'c@lk.example' ORDER BY id LIMIT 1", one=True)["body"]
        to_officer = query("SELECT subject, body FROM outbox WHERE to_addr = 'nodal.kerala9@tests.example' ORDER BY id DESC LIMIT 1", one=True)
    assert "State/UT: Lakshadweep" in mail and "The Nodal Institution of Kerala and Lakshadweep scrutinises the registered institutions" in mail
    assert to_officer["subject"] == "KTS 5.0: Kavaratti Arts College applies to participate (Lakshadweep)"
    # the Nodal Officer of Kerala sees it; the number of Annexure-I is the two together
    page = officer.get("/console/institutions").get_data(as_text=True)
    assert "You see the institutions of <b>Kerala and Lakshadweep</b>" in page and "Kavaratti Arts College" in page
    assert 'href="/console/institutions?state=Kerala">Kerala and Lakshadweep</a>' in page and "Lakshadweep</a>" not in page.replace("Kerala and Lakshadweep</a>", "")
    from test_institutions import _marked
    _marked(app)   # selected on its marks of Annexure-V (1.2.174)
    with app.app_context():
        from kts.db import set_setting
        set_setting("hei.cap_annexure", "1")   # the ceiling, off by default since 1.2.178, switched on in the Console
    r = officer.post("/console/institutions", data={"_csrf": _token(officer), "id": row["id"], "action": "accept"}, follow_redirects=True)
    assert "Kerala and Lakshadweep has 21 accepted institutions: that is the number Annexure-I prescribes for it" in r.get_data(as_text=True)
    with app.app_context():
        assert query("SELECT status FROM institutions WHERE id = ?", (row["id"],), one=True)["status"] == "pending"
    # the filter of the Console: Kerala takes in Lakshadweep, Lakshadweep is itself
    assert "Kavaratti Arts College" in officer.get("/console/institutions?state=Kerala").get_data(as_text=True)
    only = officer.get("/console/institutions?state=Lakshadweep").get_data(as_text=True)
    assert "Kavaratti Arts College" in only and "Kerala College 1" not in only
    # the institution's page, the reminders and the morning mail name the row of Annexure-I
    with app.app_context():
        assert _names()["nodal_of"]("Lakshadweep") == "Central University of Kerala" and _names()["nodal_of"]("Atlantis") == ""
        assert _nodal_line({"state": "Lakshadweep"}) == ("The Nodal Institution of Kerala and Lakshadweep, Central University of Kerala, "
                                                        "coordinates the programme in your State/UT.\n\n")
        assert _nodal_line({"state": "Kerala"}).startswith("The Nodal Institution of Kerala, Central University of Kerala, coordinates")
        u = query("SELECT * FROM users WHERE email = 'nodal.kerala9@tests.example'", one=True)
        assert NODAL.states_of(u) == ["Kerala", "Lakshadweep"] and NODAL.own_states(u) == ["Kerala"]
        subject, body = NODAL.officer_mail(u)
        assert NODAL.account_paragraph(["Kerala"]).startswith("As Nodal Officer for Kerala and Lakshadweep, you scrutinise")
    assert subject.endswith("(Kerala and Lakshadweep)") and "1 institution awaits your decision" in subject
    assert "institutions of Kerala and Lakshadweep, on " in body
    assert "Institutions registered and awaiting your selection: 1." in body
    # a Nodal Officer of another State sees nothing of it
    other = _nodal(app, "nodal.goa9@tests.example", ["Goa"])
    assert "Kavaratti Arts College" not in other.get("/console/institutions").get_data(as_text=True)
    assert other.get(f"/console/institutions/{row['id']}/marks").status_code == 404


def test_the_figures_count_the_pair_together():
    from kts import progress
    from kts.dashboard import figures
    app = make_app(ADMIN_PASSWORD=None)
    lk = _inst(app, "Kavaratti College", state="Lakshadweep")
    _inst(app, "Kochi College", state="Kerala")
    _inst(app, "Leh College", state="Ladakh", status="pending")
    # the live dashboard: 31 rows, the Lakshadweep institution in the Kerala row and in its block
    with app.app_context():
        data = figures()
    by = {r["state"]: r for r in data["states"]}
    assert "Lakshadweep" not in by and "Ladakh" not in by and len(data["states"]) == 31
    assert (by["Kerala"]["inst_reg"], by["Kerala"]["inst_sel"], by["Kerala"]["to_select"]) == (2, 2, 21)
    assert (by["Jammu and Kashmir"]["inst_reg"], by["Jammu and Kashmir"]["inst_sel"]) == (1, 0)
    assert data["total"]["inst_reg"] == 3 and data["total"]["to_select"] == 1000
    client = app.test_client()
    page = client.get("/dashboard?lang=en").get_data(as_text=True)
    assert ('<a class="dash-tile cv" href="#d-KL">\n          <b dir="ltr">LD</b>\n          <span class="dash-n" dir="ltr">→ KL</span>\n'
            '          <span class="dash-tip" role="tooltip"><b>Lakshadweep</b>\n'
            '            <span>Counted with Kerala, as paired in Annexure-I</span></span>') in page
    assert page.count('class="dash-tile cv"') == 5 and "Union Territory counted with another row of Annexure-I" in page
    assert '<tr id="st-KL">\n          <th scope="row"><a href="#d-KL">Kerala and Lakshadweep</a></th>' in page
    block = page[page.index('id="d-KL"'):]
    block = block[:block.index("</details>")]
    assert "<b>Kerala and Lakshadweep</b>" in block and "Central University of Kerala" in block
    assert "Kavaratti College" in block and "· Lakshadweep</span>" in block and "Kochi College" in block
    assert block.count("· Lakshadweep</span>") == 1
    tamil = client.get("/dashboard?lang=ta").get_data(as_text=True)
    assert '<a href="#d-KL">கேரளா மற்றும் லட்சத்தீவு</a>' in tamil
    # the board of the Console: one row for the two; a Nodal Officer given Lakshadweep alone sees the Kerala row with its own
    with app.app_context():
        board = progress.board()
        kerala = next(s for s in board["states"] if s["state"] == "Kerala")
        assert (kerala["label"], kerala["allocation"], kerala["participating"]) == ("Kerala and Lakshadweep", 21, 2)
        assert [s["state"] for s in board["states"]].count("Lakshadweep") == 0 and len(board["states"]) == 31
        assert [(s["state"], s["participating"]) for s in progress.board(["Lakshadweep"])["states"]] == [("Kerala", 1)]
        assert [(s["state"], s["participating"]) for s in progress.board(["Kerala", "Lakshadweep"])["states"]] == [("Kerala", 2)]
        assert [r["id"] for r in progress.institutions(None, "Lakshadweep")] == [lk]
        assert len(progress.institutions(None, "Kerala")) == 2
    # the Nodal Officers' page of the Console
    from test_public_fixes import _staff
    admin = _staff(app, "admin9@tests.example", "superadmin")
    page = admin.get("/console/nodal").get_data(as_text=True)
    assert "<b>Kerala and Lakshadweep</b>" in page and "<b>Jammu and Kashmir and Ladakh</b>" in page
    assert "States/UTs without a Nodal Institution" not in page
    row = page.split("<b>Kerala and Lakshadweep</b>")[1].split("</tr>")[0]
    assert '<td class="num">2<span class="small muted">/21</span>' in row
    progress_page = admin.get("/console/progress").get_data(as_text=True)
    assert 'href="/console/progress?state=Kerala">Kerala and Lakshadweep</a>' in progress_page

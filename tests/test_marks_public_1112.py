"""
"Marks recorded: N of M" on the public dashboard KTS 5.0 by State/UT (1.2.175; CICT, 12 November 2026, of the Console's card
"Selected without marks": "I want these information should come on the portal", and, asked what should be public, the counts
State/UT by State/UT).

For each row of Annexure-I: M, the institutions that the Nodal Institution has selected or placed on its reserve list; N, those
of them whose marks of the Evaluation Committee (Annexure-V) are recorded. M less N is the number of the Console's card. Counts
only: no institution is named that the page did not name before. The setting dashboard.marks takes it off the page.

    python -m pytest tests/test_marks_public_1112.py -q
"""
import itertools
import re

from conftest import make_app
from test_nodal_access import _token
from test_public_fixes import _staff

LANGS = ["as", "bn", "brx", "doi", "en", "gu", "hi", "kn", "kok", "ks", "mai", "ml", "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd",
         "ta", "te", "ur"]
NUMBERS = itertools.count(1)
ROWS = [("TN One College", "Tamil Nadu", "accepted", 80), ("TN Two College", "Tamil Nadu", "accepted", None),
        ("TN Reserve College", "Tamil Nadu", "reserve", None), ("Port Blair College", "Andaman and Nicobar Islands", "accepted", None),
        ("Kochi College", "Kerala", "accepted", 70), ("Goa Pending College", "Goa", "pending", 90),
        ("Bihar Identified College", "Bihar", "identified", None), ("Assam Declined College", "Assam", "declined", 60)]


def _portal():
    from kts.db import execute, set_setting, utcnow
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("dashboard.public", "1")
        for name, state, status, total in ROWS:
            execute("INSERT INTO institutions(ref, name, itype, state, district, inst_key, status, head_name, sop_total, created_at, "
                    "updated_at) VALUES(?, ?, 'Government college', ?, 'District', ?, ?, 'Dr. Head', ?, ?, ?)",
                    (f"KTS5-HEI-{next(NUMBERS):05d}", name, state, f"name:{name.lower()}|{state.lower()}", status, total, utcnow(),
                     utcnow()))
    return app


def _row(page, code):
    row = page[page.index(f'<tr id="st-{code}">'):]
    return row[:row.index("</tr>")]


def test_the_figures_of_the_marks():
    from kts.dashboard import figures
    app = _portal()
    with app.app_context():
        data = figures()
    by = {r["state"]: r for r in data["states"]}
    # Tamil Nadu with the Union Territory paired with it: three selected and one on the reserve list, counted together (1.2.178),
    # one of them marked
    assert (by["Tamil Nadu"]["inst_sel"], by["Tamil Nadu"]["inst_dec"], by["Tamil Nadu"]["inst_marked"]) == (4, 4, 1)
    assert (by["Kerala"]["inst_dec"], by["Kerala"]["inst_marked"]) == (1, 1)
    # registered and marked but not yet selected, only identified, declined: none of them counts
    assert [(by[s]["inst_dec"], by[s]["inst_marked"]) for s in ("Goa", "Bihar", "Assam")] == [(0, 0)] * 3
    assert (data["total"]["inst_dec"], data["total"]["inst_marked"]) == (5, 2)


def test_the_dashboard_says_marks_recorded_for_each_state():
    app = _portal()
    page = app.test_client().get("/dashboard?lang=en").get_data(as_text=True)
    head = page[page.index("<thead>"):page.index("</thead>")]
    heads = re.findall(r"<th[^>]*>([^<]+)</th>", head)
    assert heads[heads.index("Participating Institutions selected") + 1] == "Marks recorded"
    assert '<td class="num">4</td>' in _row(page, "TN") and '<td class="num dash-marks"><bdi>1 of 4</bdi></td>' in _row(page, "TN")
    assert '<td class="num dash-marks"><bdi>1 of 1</bdi></td>' in _row(page, "KL")
    for code in ("GA", "BR", "AS"):
        assert '<td class="num dash-marks">–</td>' in _row(page, code), code
    foot = page[page.index("<tfoot>"):page.index("</tfoot>")]
    assert '<td class="num dash-marks"><bdi>2 of 5</bdi></td>' in foot
    assert ("Marks recorded: of the institutions that the Nodal Institution has selected or placed on its reserve list, those whose "
            "marks under the Standard Operating Procedure (Annexure-V) are recorded on the portal.") in page
    # the note of the square and the heading of the State/UT
    tile = page[page.index('href="#d-TN"'):]
    assert "Marks recorded: <bdi>1 of 4</bdi>" in tile[:tile.index("</a>")]
    tile = page[page.index('href="#d-GA"'):]
    assert "Marks recorded" not in tile[:tile.index("</a>")]
    summary = page[page.index('id="d-TN"'):]
    assert "· Marks recorded: <bdi>1 of 4</bdi>" in summary[:summary.index("</summary>")]
    # counts only: the page names no institution that it did not name before (the reserve list with the selected, 1.2.178)
    assert "TN Reserve College" in page
    for name in ("Goa Pending College", "Bihar Identified College", "Assam Declined College"):
        assert name not in page, name
    assert "80" not in _row(page, "TN") and "/100" not in page


def test_the_figure_follows_the_console():
    # what the Console's card "Selected without marks" counts is M less N; a mark recorded there moves the dashboard
    from kts.db import query
    app = _portal()
    admin = _staff(app, "admin@tests.example", "superadmin")
    console = admin.get("/console/institutions").get_data(as_text=True)
    card = console[console.index('id="unmarked"'):console.index("Invite institutions to register (a list)")]
    assert re.search(r"<b>Tamil Nadu and Andaman and Nicobar Islands</b>: <a [^>]+>3 institution\(s\)</a>", card)
    assert "Kerala" not in card
    with app.app_context():
        two = query("SELECT id FROM institutions WHERE name = 'TN Two College'", one=True)["id"]
    marks = dict(zip(("readiness", "outreach", "academic", "geography", "diversity_type", "diversity_disc"), "15 15 15 10 10 5".split()))
    assert admin.post(f"/console/institutions/{two}/marks", data=dict(marks, _csrf=_token(admin), note="")).status_code == 302
    page = app.test_client().get("/dashboard?lang=en").get_data(as_text=True)
    assert '<td class="num dash-marks"><bdi>2 of 4</bdi></td>' in _row(page, "TN")
    assert '<bdi>3 of 5</bdi>' in page[page.index("<tfoot>"):page.index("</tfoot>")]


def test_the_reserve_list_counted_with_the_selected():
    # CICT, 12 November 2026: "The reserve list should also be added to the total" (1.2.175: a card and a column of its own), then
    # "no separate reserve list. add with the selected institutions" (1.2.178: counted with the Participating Institutions)
    from kts.dashboard import figures
    app = _portal()
    with app.app_context():
        data = figures()
    by = {r["state"]: r for r in data["states"]}
    assert (by["Tamil Nadu"]["inst_sel"], by["Kerala"]["inst_sel"], data["total"]["inst_sel"]) == (4, 1, 5)
    page = app.test_client().get("/dashboard?lang=en").get_data(as_text=True)
    kpis = page[page.index('class="grid grid-3 dash-kpis"'):page.index('<section class="card dash-map"')]
    assert re.findall(r'<div class="num">([\d,]+)</div><div class="lbl">([^<]+)</div>', kpis) == [
        ("1,000", "To be selected"), ("5", "Participating Institutions selected"), ("0", "Students who took an institution&#39;s online test")]
    assert "Reserve list" not in page and "dash-res" not in page
    tile = page[page.index('href="#d-TN"'):]
    assert '<span class="dash-n" dir="ltr">4</span>' in tile[:tile.index("</a>")]   # no number of Annexure-I (1.2.179)
    summary = page[page.index('id="d-TN"'):]
    summary = summary[:summary.index("</details>")]
    assert "Participating Institutions selected: 4" in summary and "TN Reserve College" in summary   # its name with the others
    assert '<td class="num">4</td>' in _row(page, "TN") and '<td class="num">5</td>' in page[page.index("<tfoot>"):page.index("</tfoot>")]
    # the reserve list kept off the public pages: only the institutions selected
    from kts.db import set_setting
    with app.app_context():
        set_setting("hei.reserve_public", "0")
        assert {r["state"]: r for r in figures()["states"]}["Tamil Nadu"]["inst_sel"] == 3
    page = app.test_client().get("/dashboard?lang=en").get_data(as_text=True)
    assert "TN Reserve College" not in page and '<td class="num">3</td>' in _row(page, "TN")


def test_the_setting_takes_it_off_the_page():
    from kts.db import DEFAULT_SETTINGS, set_setting
    assert DEFAULT_SETTINGS["dashboard.marks"] == "1"
    app = _portal()
    with app.app_context():
        set_setting("dashboard.marks", "0")
    page = app.test_client().get("/dashboard?lang=en").get_data(as_text=True)
    assert "Marks recorded" not in page and "dash-marks" not in page
    head = page[page.index("<thead>"):page.index("</thead>")]
    assert head.count("<th ") == 3   # no column of the number to be selected (1.2.179)
    assert re.findall(r'<td class="num">([^<]*)</td>', _row(page, "TN")) == ["4", "0"]
    settings = _staff(app, "admin@tests.example", "superadmin").get("/console/settings").get_data(as_text=True)
    assert "Marks recorded: N of M" in settings
    # and the dashboard itself switched off is not there at all
    with app.app_context():
        set_setting("dashboard.public", "0")
    assert app.test_client().get("/dashboard?lang=en").status_code == 404


def _register(app, name, state="Puducherry"):
    from test_institutions import _apply
    from kts.db import query
    slug = re.sub(r"[^a-z]", "", name.lower())
    assert _apply(app.test_client(), name=name, state=state, district="Karaikal", aishe_code="", head_email=f"head@{slug}.example",
                  coord_email=f"coord@{slug}.example").status_code == 302
    with app.app_context():
        return query("SELECT id FROM institutions WHERE name = ?", (name,), one=True)["id"]


def _act(client, iid, action):
    return client.post("/console/institutions", data={"_csrf": _token(client), "id": iid, "action": action}, follow_redirects=True)


def test_the_marks_may_come_later():
    # CICT, 12 November 2026: "marks will be added later stage" - the setting hei.marks_first, off: Select and Reserve list work
    # without marks; the reserve list shows an institution without marks, unnumbered, after the others, in the order of the names
    from io import BytesIO
    from openpyxl import load_workbook
    from kts.db import DEFAULT_SETTINGS, query, set_setting
    from kts.utils import limiter
    from test_nodal_access import _nodal
    assert DEFAULT_SETTINGS["hei.marks_first"] == "0"
    limiter._hits.clear()
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("hei.end", "2099-12-31")
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    ids = {name: _register(app, name) for name in ("Selected College", "Zeta College", "Alpha College", "Marked College")}
    limiter._hits.clear()
    page = officer.get("/console/institutions?state=Puducherry").get_data(as_text=True)
    assert page.count('value="accept"') == 4 and page.count('value="reserve"') == 4
    assert ">Record the marks</a>" not in page and "Select and Reserve list follow the marks" not in page
    assert "the marks may\n  be recorded at a later stage" in page.replace("\r\n", "\n")
    assert "Selected College: accepted" in _act(officer, ids["Selected College"], "accept").get_data(as_text=True)
    for name in ("Zeta College", "Alpha College", "Marked College"):
        assert f"{name}: reserve" in _act(officer, ids[name], "reserve").get_data(as_text=True)
    marks = dict(zip(("readiness", "outreach", "academic", "geography", "diversity_type", "diversity_disc"), "15 15 15 10 10 5".split()))
    officer.post(f"/console/institutions/{ids['Marked College']}/marks", data=dict(marks, _csrf=_token(officer), note=""))
    with app.app_context():
        assert {r["name"]: r["status"] for r in query("SELECT name, status FROM institutions")} == {
            "Selected College": "accepted", "Zeta College": "reserve", "Alpha College": "reserve", "Marked College": "reserve"}
    # the website: all four in the list of Puducherry, by name, with or without marks (1.2.177)
    public = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    assert re.findall(r'<td class="num">([^<]+)</td><td lang="en" dir="ltr">([^<]+)</td>', public) == [
        ("1", "Alpha College"), ("2", "Marked College"), ("3", "Selected College"), ("4", "Zeta College")]
    # the evaluation sheet: a place only for the one with marks
    ws = load_workbook(BytesIO(officer.get("/console/institutions/evaluation.xlsx?state=Puducherry").data)).active
    rows = {v[4]: v[18] for v in [[c.value for c in row] for row in ws.iter_rows()][1:]}
    assert rows == {"Marked College": "reserve list 1", "Alpha College": "reserve list", "Zeta College": "reserve list",
                    "Selected College": "selected"}
    # once all have marks, the evaluation sheet gives each its place, in the order of the marks
    for name, readiness in (("Zeta College", "20"), ("Alpha College", "10")):
        officer.post(f"/console/institutions/{ids[name]}/marks", data=dict(marks, readiness=readiness, _csrf=_token(officer), note=""))
    ws = load_workbook(BytesIO(officer.get("/console/institutions/evaluation.xlsx?state=Puducherry").data)).active
    rows = {v[4]: v[18] for v in [[c.value for c in row] for row in ws.iter_rows()][1:]}
    assert rows == {"Zeta College": "reserve list 1", "Marked College": "reserve list 2", "Alpha College": "reserve list 3",
                    "Selected College": "selected"}
    # the rule of 1.2.174 when CICT switches it on
    with app.app_context():
        set_setting("hei.marks_first", "1")
    late = _register(app, "Late College")
    assert "record the marks of the Evaluation Committee first" in _act(officer, late, "accept").get_data(as_text=True)
    page = officer.get("/console/institutions?state=Puducherry&status=pending").get_data(as_text=True)
    assert ">Record the marks</a>" in page and 'value="accept"' not in page
    assert "An institution is\n  selected, or put on the reserve list, once its marks are recorded here" in officer.get(
        f"/console/institutions/{late}/marks").get_data(as_text=True).replace("\r\n", "\n")
    settings = _staff(app, "admin@tests.example", "superadmin").get("/console/settings").get_data(as_text=True)
    assert "the marks may be recorded at a later stage" in settings


def test_the_two_texts_in_23_languages():
    from kts.i18n import CATALOG
    assert sorted(CATALOG) == sorted(LANGS)
    for code in LANGS:
        c = CATALOG[code]
        for key in ("dash.marks", "dash.marks_note"):
            assert c[key].strip() and "\n" not in c[key], (code, key)
            assert code == "en" or c[key] != CATALOG["en"][key], (code, key)
        assert len(c["dash.marks"]) <= 40, code
        assert c["dash.marks_note"].startswith(c["dash.marks"]), code     # the sentence begins with the heading it explains
    assert CATALOG["en"]["dash.marks"] == "Marks recorded"
    app = _portal()
    for code in ("ta", "hi", "ur", "bn", "sat"):
        page = app.test_client().get(f"/dashboard?lang={code}").get_data(as_text=True)
        assert CATALOG[code]["dash.marks"] in page[page.index("<thead>"):page.index("</thead>")], code
        assert CATALOG[code]["dash.marks_note"] in page, code
        of = CATALOG[code]["dash.of"].replace("{n}", "1").replace("{total}", "4")
        assert f'<td class="num dash-marks"><bdi>{of}</bdi></td>' in _row(page, "TN"), code

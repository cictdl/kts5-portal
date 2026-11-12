"""
Any number of institutions, the marks first, a reserve list without an upper limit and published (1.2.174; CICT, 11 November
2026: "The Reserve list should be notified on the portal. Reserve list upper band should be removed. Any State or UT can apply
any number of institutions. From this, the Nodal HEI can select the stipulated number of institutions after giving marks.").

* An institution is selected, or put on the reserve list, only once the marks of the Evaluation Committee (Annexure-V) are
  recorded for it, by a Nodal Officer or by CICT; the number of Annexure-I stays the limit of the selection.
* The reserve list has no upper limit (ordinarily up to 20 per cent of the number of Annexure-I before), and it is on
  /institutions, one list for each row of Annexure-I in the order of the marks, without the marks (hei.reserve_public).
* Institutions selected before without marks stay as they are; the Console names them for the marks to be recorded.
* The figures of /institutions and of the home page: the States and Union Territories that have a Participating Institution, of
  the 36; a district once, whatever its spelling.

    python -m pytest tests/test_reserve_1111.py -q
"""
import io
import itertools
import json
import re

import pytest

from conftest import ROOT, make_app
from test_institutions import _apply
from test_nodal_access import _nodal, _token
from test_public_fixes import _staff

CRITERIA = ("readiness", "outreach", "academic", "geography", "diversity_type", "diversity_disc")
LANGS = ["as", "bn", "brx", "doi", "en", "gu", "hi", "kn", "kok", "ks", "mai", "ml", "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd",
         "ta", "te", "ur"]
NUMBERS = itertools.count(1)


@pytest.fixture(autouse=True)
def empty_limiter():
    """The registrations here count against the limit of an address per hour; the other tests' count stays as it was."""
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def _app():
    app = make_app(ADMIN_PASSWORD=None)
    from kts.db import set_setting
    with app.app_context():
        set_setting("hei.end", "2099-12-31")
        set_setting("join.on", "1")
        set_setting("hei.marks_first", "1")   # the rule of 1.2.174, off by default since 1.2.175 (tests/test_marks_public_1112.py)
    return app


def _register(app, name, state="Puducherry", district="Karaikal"):
    """An institution registers on the website; gives its id."""
    from kts.db import query
    slug = re.sub(r"[^a-z]", "", name.lower())
    r = _apply(app.test_client(), name=name, state=state, district=district, aishe_code="", head_email=f"head@{slug}.example",
               coord_email=f"coord@{slug}.example")
    assert r.status_code == 302, name
    with app.app_context():
        return query("SELECT id FROM institutions WHERE name = ?", (name,), one=True)["id"]


def _mark(officer, iid, marks):
    return officer.post(f"/console/institutions/{iid}/marks", data=dict(zip(CRITERIA, map(str, marks)), _csrf=_token(officer), note=""))


def _act(officer, iid, action):
    return officer.post("/console/institutions", data={"_csrf": _token(officer), "id": iid, "action": action}, follow_redirects=True)


def _status(app, iid):
    from kts.db import query
    with app.app_context():
        return query("SELECT status FROM institutions WHERE id = ?", (iid,), one=True)["status"]


def _insert(app, name, state, district, status, total=None, created=None, **more):
    """An institution as it was left before 1.2.174: selected, or on the reserve list, with or without marks."""
    from kts.db import execute, utcnow
    values = {"ref": f"KTS5-HEI-9{next(NUMBERS):04d}", "name": name, "itype": "Government college", "state": state, "district": district,
              "inst_key": f"name:{name.lower()}|{state.lower()}", "status": status, "head_name": "Dr. Head", "sop_total": total}
    values.update(more)
    with app.app_context():
        values["created_at"] = values["updated_at"] = created or utcnow()
        return execute(f"INSERT INTO institutions({', '.join(values)}) VALUES({', '.join('?' * len(values))})", list(values.values()))


def test_an_institution_is_selected_once_its_marks_are_recorded():
    from kts.db import query
    app = _app()
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    alpha = _register(app, "Alpha College")
    page = officer.get("/console/institutions?state=Puducherry").get_data(as_text=True)
    assert 'value="accept"' not in page and 'value="reserve"' not in page
    assert ">Record the marks</a>" in page and "Select and Reserve list follow the marks" in page and 'value="decline"' in page
    with app.app_context():
        mails = query("SELECT COUNT(*) AS n FROM outbox", one=True)["n"]
    for action in ("accept", "reserve"):
        answer = _act(officer, alpha, action).get_data(as_text=True)
        assert "Alpha College: record the marks of the Evaluation Committee first (Marks, Annexure-V)" in answer, action
        assert _status(app, alpha) == "pending"
    with app.app_context():   # nobody was told of a decision
        assert query("SELECT COUNT(*) AS n FROM outbox", one=True)["n"] == mails
    # the marks recorded: the Console offers both, and the institution is selected
    assert _mark(officer, alpha, (20, 15, 15, 10, 10, 5)).status_code == 302
    page = officer.get("/console/institutions?state=Puducherry").get_data(as_text=True)
    assert 'value="accept"' in page and 'value="reserve"' in page and "<b>75</b>/100" in page
    assert ">Marks</a>" in page and ">Record the marks</a>" not in page and "Select and Reserve list follow the marks" not in page
    assert "Alpha College: accepted" in _act(officer, alpha, "accept").get_data(as_text=True) and _status(app, alpha) == "accepted"
    # CICT selects on the marks too
    admin = _staff(app, "admin@tests.example", "superadmin")
    beta = _register(app, "Beta College")
    assert "record the marks of the Evaluation Committee first" in _act(admin, beta, "accept").get_data(as_text=True)
    assert _status(app, beta) == "pending"
    # an institution is declined without marks, as before; marks of the criteria of 26 October (cleared in 1.2.155) are none
    assert "Beta College: declined" in _act(officer, beta, "decline").get_data(as_text=True)
    gamma = _register(app, "Gamma College")
    from kts.db import execute
    with app.app_context():
        execute("UPDATE institutions SET sop_scores = ? WHERE id = ?", (json.dumps({"record": 5, "diversity": 5}), gamma))
    assert "record the marks of the Evaluation Committee first" in _act(officer, gamma, "accept").get_data(as_text=True)


def test_the_number_of_annexure_i_and_a_reserve_list_without_an_upper_limit():
    from kts import heis as HEI
    from kts.db import query, set_setting
    from openpyxl import load_workbook
    app = _app()
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    with app.app_context():
        assert HEI.cap_of("Puducherry") == 5
    # ten institutions register: any number may; each marked, 100 down to 55
    marks = [(20, 20, 20, 20, 10, 10), (20, 15, 20, 20, 10, 10), (20, 10, 20, 20, 10, 10), (20, 5, 20, 20, 10, 10), (20, 0, 20, 20, 10, 10),
             (15, 0, 20, 20, 10, 10), (10, 0, 20, 20, 10, 10), (5, 0, 20, 20, 10, 10), (0, 0, 20, 20, 10, 10), (0, 0, 15, 20, 10, 10)]
    ids = {}
    for letter, given in zip("ABCDEFGHIJ", marks):
        ids[letter] = _register(app, f"College {letter}")
        assert _mark(officer, ids[letter], given).status_code == 302
    with app.app_context():
        totals = {r["name"][-1]: r["sop_total"] for r in query("SELECT name, sop_total FROM institutions")}
    assert [totals[c] for c in "ABCDEFGHIJ"] == [100, 95, 90, 85, 80, 75, 70, 65, 60, 55]
    for letter in "ABCDE":
        _act(officer, ids[letter], "accept")
    # the number of Annexure-I is the limit of the selection
    answer = _act(officer, ids["F"], "accept").get_data(as_text=True)
    assert "Puducherry has 5 accepted institutions: that is the number Annexure-I prescribes for it" in answer
    assert "The others may be placed on the reserve list, which has no upper limit." in answer and _status(app, ids["F"]) == "pending"
    # the five others on the reserve list (one, 20 per cent of the five, before 1.2.174), in any order
    for letter in "JHFGI":
        assert f"College {letter}: reserve" in _act(officer, ids[letter], "reserve").get_data(as_text=True)
    assert [_status(app, ids[c]) for c in "FGHIJ"] == ["reserve"] * 5
    with app.app_context():
        mail = query("SELECT body FROM outbox WHERE to_addr = 'coord@collegeh.example' ORDER BY id DESC", one=True)["body"]
    assert "placed your institution in the reserve list" in mail
    assert "Your institution is listed on the portal with the institutions of your State/UT: " in mail
    assert "/institutions\n\nReference: KTS5-HEI-" in mail and "#reserve" not in mail
    # the Console: no share of the number beside the count, in the words above the table or on the page of the marks
    console = officer.get("/console/institutions?state=Puducherry").get_data(as_text=True)
    summary = console[console.index("<tbody>"):console.index("</tbody>")]
    assert '<td class="num"><b>5</b></td>\n    <td class="num">5</td>' in summary and "/1</span>" not in console
    assert "20 per cent" not in console
    assert "which has no upper limit (CICT, 11 November 2026) and is published on the website with the Participating Institutions" in console
    assert "place each of them on it with the button <b>Reserve list</b>" in console
    assert "any number of institutions of a State/UT may register" in console
    page = officer.get(f"/console/institutions/{ids['F']}/marks").get_data(as_text=True)
    assert "form the reserve list, which has no upper limit" in page and "ordinarily up to" not in page
    assert "with <b>Select</b> or <b>Reserve list</b> in the list of the institutions" in page
    # the website: the reserve list in the table of its State/UT with the Participating Institutions, by name, not told apart,
    # without the marks (1.2.177; a list of its own in 1.2.174-1.2.176)
    public = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    table = public[public.index('<h2 id="st-puducherry"'):]
    table = table[:table.index("</table>")]
    assert '<h2 id="st-puducherry" style="margin-top:28px">Puducherry <span class="small muted">(10)</span></h2>' in public
    assert re.findall(r'<tr><td class="num">(\d+)</td><td lang="en" dir="ltr">(College [A-J])</td>', table) == [
        (str(n), f"College {c}") for n, c in enumerate("ABCDEFGHIJ", start=1)]
    assert 'id="reserve' not in public and "Reserve list" not in public and "/100" not in public
    assert not any(str(n) in re.sub(r"<[^>]+>", " ", table) for n in (75, 70, 65, 60, 55))
    # the figures at a glance count the Participating Institutions selected
    pi = public[public.index('<section class="pi"'):public.index('<p><b>')]
    assert '<div class="num">5</div><div class="lbl">Participating institutions</div>' in pi and "10 institutions from 1 States/UTs" in public
    # the evaluation sheet: no column of a reserve list "up to 20%"; each institution of the reserve list with its place
    ws = load_workbook(io.BytesIO(officer.get("/console/institutions/evaluation.xlsx?state=Puducherry").data)).active
    values = [[c.value for c in row] for row in ws.iter_rows()]
    assert not any("20%" in str(h) for h in values[0]) and values[0][18] == "Status"
    assert [(v[3], v[4][-1], v[18]) for v in values[1:]] == (
        [(n + 1, c, "selected") for n, c in enumerate("ABCDE")] + [(n + 6, c, f"reserve list {n + 1}") for n, c in enumerate("FGHIJ")])
    # switched off in Settings: the website has no reserve list, and the mail does not speak of one
    with app.app_context():
        set_setting("hei.reserve_public", "0")
    public = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    assert "College F" not in public and "College A<" in public and "(5)</span></h2>" in public
    _act(officer, ids["J"], "pending")
    _act(officer, ids["J"], "reserve")
    with app.app_context():
        mail = query("SELECT body FROM outbox WHERE to_addr = 'coord@collegej.example' ORDER BY id DESC", one=True)["body"]
    assert "placed your institution in the reserve list" in mail and "published on the portal" not in mail
    console = officer.get("/console/institutions?state=Puducherry").get_data(as_text=True)
    assert "which has no upper limit (CICT, 11 November 2026):" in console and "is published on the website" not in console
    settings = _staff(app, "admin@tests.example", "superadmin").get("/console/settings").get_data(as_text=True)
    assert "List the institutions of the reserve list on the same page, in the table of their State/UT" in settings
    # nor while the page of the Participating Institutions itself is switched off
    with app.app_context():
        set_setting("hei.reserve_public", "1")
        set_setting("hei.public", "0")
    assert app.test_client().get("/institutions?lang=en").status_code == 404
    _act(officer, ids["I"], "pending")
    _act(officer, ids["I"], "reserve")
    with app.app_context():
        mail = query("SELECT body FROM outbox WHERE to_addr = 'coord@collegei.example' ORDER BY id DESC", one=True)["body"]
    assert "placed your institution in the reserve list" in mail and "published on the portal" not in mail
    assert "is published on the website" not in officer.get("/console/institutions?state=Puducherry").get_data(as_text=True)


def test_the_reserve_list_of_a_row_of_annexure_i():
    from kts.i18n import CATALOG
    app = _app()
    officer = _nodal(app, "nodal.kl@tests.example", ["Kerala"])
    kochi = _register(app, "Kochi College", "Kerala", "Ernakulam")
    island = _register(app, "Kavaratti College", "Lakshadweep", "Kavaratti")
    goa = _register(app, "Panaji College", "Goa", "North Goa")
    _mark(officer, kochi, (15, 15, 15, 10, 10, 5))    # 70
    _mark(officer, island, (20, 15, 15, 20, 10, 5))   # 85: the Union Territory is ranked with its State
    admin = _staff(app, "admin@tests.example", "superadmin")
    _mark(admin, goa, (20, 20, 20, 20, 10, 10))
    for iid in (kochi, island):
        _act(officer, iid, "reserve")
    _act(admin, goa, "reserve")
    # on the reserve list without marks: it has no place in the order of the marks, it comes after the others unnumbered (1.2.175)
    old = _insert(app, "Old Reserve College", "Kerala", "Kollam", "reserve")
    public = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    # the institutions of the reserve list are listed before any selection, each in the table of its own State/UT (1.2.177)
    assert "4 institutions from 3 States/UTs" in public and '<p class="alert info">No institution has been accepted yet.</p>' not in public
    assert public.index('id="st-goa"') < public.index('id="st-kerala"') < public.index('id="st-lakshadweep"')
    kerala = public[public.index('id="st-kerala"'):public.index('id="st-lakshadweep"')]
    assert re.findall(r'<td class="num">([^<]+)</td><td lang="en" dir="ltr">([^<]+)</td>', kerala) == [
        ("1", "Kochi College"), ("2", "Old Reserve College")]
    assert "Kavaratti College" in public[public.index('id="st-lakshadweep"'):]
    # the evaluation sheet gives the places of the website, also when it is asked for the Union Territory alone
    from openpyxl import load_workbook
    for asked in ("Kerala", "Lakshadweep"):
        ws = load_workbook(io.BytesIO(officer.get(f"/console/institutions/evaluation.xlsx?state={asked}").data)).active
        rows = [[c.value for c in row] for row in ws.iter_rows()][1:]
        assert [(v[4], v[3], v[18]) for v in rows] == [("Kavaratti College", 1, "reserve list 1"), ("Kochi College", 2, "reserve list 2"),
                                                       ("Old Reserve College", None, "reserve list")], asked
    # its marks recorded, the old one takes its place in the evaluation sheet; the website lists by name, as before
    _mark(officer, old, (10, 15, 15, 10, 10, 5))   # 65
    ws = load_workbook(io.BytesIO(officer.get("/console/institutions/evaluation.xlsx?state=Kerala").data)).active
    assert [[c.value for c in row] for row in ws.iter_rows()][3][18] == "reserve list 3"
    # in the languages of the portal
    for code in ("ta", "hi", "ur", "sat"):
        page = app.test_client().get(f"/institutions?lang={code}").get_data(as_text=True)
        assert CATALOG[code]["hei.any_number"] in page and "Old Reserve College" in page, code
    assert old


def test_institutions_selected_without_marks_stay_and_are_named():
    app = _app()
    _insert(app, "Early College", "Maharashtra", "Pune", "accepted")
    _insert(app, "Waiting College", "Maharashtra", "Nagpur", "reserve")
    _insert(app, "Marked College", "Maharashtra", "Nashik", "accepted", 80)
    _insert(app, "Kochi Early College", "Kerala", "Ernakulam", "accepted")
    officer = _nodal(app, "nodal.mh@tests.example", ["Maharashtra"])
    page = officer.get("/console/institutions").get_data(as_text=True)
    card = page[page.index('id="unmarked"'):page.index("Invite institutions to register (a list)")]
    assert "Selected without marks" in card and "They stay as they are." in card
    assert '<b>Maharashtra</b>: <a href="/console/institutions?state=Maharashtra&amp;unmarked=1">2 institution(s)</a>' in card
    assert "Kerala" not in card    # the officer's own State/UT only
    assert "selected without marks: please record them" in page and "on the reserve list without marks: please record them" in page
    listed = officer.get("/console/institutions?state=Maharashtra&unmarked=1").get_data(as_text=True)
    listed = listed[listed.index('<table class="table institutions">'):]
    assert "Early College" in listed and "Waiting College" in listed and "Marked College" not in listed
    assert "appears in the list of the website once its marks are recorded" in card
    # nothing changes for them: selected, and on the website; the one of the reserve list is in its list, unnumbered (1.2.175)
    public = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    assert "Early College" in public and "Waiting College" in public   # in the list of Maharashtra (1.2.177)
    # CICT sees every State/UT; once the marks are recorded the card is gone
    admin = _staff(app, "admin@tests.example", "superadmin")
    console = admin.get("/console/institutions").get_data(as_text=True)
    assert "<b>Kerala and Lakshadweep</b>: " in console and "<b>Maharashtra</b>: " in console
    from kts.db import query
    with app.app_context():
        ids = [r["id"] for r in query("SELECT id FROM institutions WHERE sop_total IS NULL AND state = 'Maharashtra'")]
    for iid in ids:
        assert _mark(officer, iid, (15, 15, 15, 10, 10, 5)).status_code == 302
    page = officer.get("/console/institutions").get_data(as_text=True)
    assert 'id="unmarked"' not in page and "without marks" not in page
    with app.app_context():
        assert sorted(r["status"] for r in query("SELECT status FROM institutions WHERE state = 'Maharashtra'")) == [
            "accepted", "accepted", "reserve"]
    public = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    assert "Waiting College" in public[public.index('id="st-maharashtra"'):]


def test_institutions_equal_in_everything_have_one_order_everywhere():
    # the institutions of one uploaded list have one day and hour of registration; with equal marks they are in the order of
    # their references on the website, in the Console and on the evaluation sheet
    from openpyxl import load_workbook
    app = _app()
    day = "2026-11-10T06:00:00+00:00"
    names = [("Zeta College", "Kerala"), ("Island College", "Lakshadweep"), ("Alpha College", "Kerala"), ("Mid College", "Kerala")]
    for name, state in names:
        _insert(app, name, state, "Kollam", "reserve", 70, created=day)
    wanted = [name for name, _state in names]
    officer = _nodal(app, "nodal.kl@tests.example", ["Kerala"])
    console = officer.get("/console/institutions?state=Kerala&order=marks").get_data(as_text=True)
    console = console[console.index('<table class="table institutions">'):]
    assert sorted(wanted, key=console.index) == wanted
    for asked in ("", "?state=Kerala", "?state=Lakshadweep"):
        ws = load_workbook(io.BytesIO(officer.get("/console/institutions/evaluation.xlsx" + asked).data)).active
        rows = [[c.value for c in row] for row in ws.iter_rows()][1:]
        assert [(v[4], v[18]) for v in rows] == [(name, f"reserve list {n}") for n, name in enumerate(wanted, 1)], asked


def test_an_institution_of_the_reserve_list_does_not_register_again():
    app = _app()
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    twice = _register(app, "Twice College")
    _mark(officer, twice, (15, 15, 15, 10, 10, 5))
    _act(officer, twice, "reserve")
    again = _apply(app.test_client(), name="Twice College", state="Puducherry", district="Karaikal", aishe_code="",
                   head_email="head2@twice.example", coord_email="coord2@twice.example")
    assert again.status_code == 400 and "already applied" in again.get_data(as_text=True)
    public = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    assert public.count("Twice College") == 1
    # declined, it may apply again, as before
    _act(officer, twice, "decline")
    assert _apply(app.test_client(), name="Twice College", state="Puducherry", district="Karaikal", aishe_code="",
                  head_email="head2@twice.example", coord_email="coord2@twice.example").status_code == 302


def test_an_institution_that_never_registered_is_not_selected_by_way_of_a_decline():
    # the gap of 1.2.173: identified, declined, and then selected without ever registering
    app = _app()
    officer = _nodal(app, "nodal.mh@tests.example", ["Maharashtra"])
    never = _insert(app, "Never College", "Maharashtra", "Pune", "identified", head_name="", invited_by=1, invite_token="tok-never",
                    coord_email="coord@never.example")
    assert "has not completed its registration yet" in _act(officer, never, "accept").get_data(as_text=True)
    _act(officer, never, "decline")
    assert _status(app, never) == "declined"
    assert _mark(officer, never, (20, 20, 20, 20, 10, 10)).status_code == 302
    page = officer.get("/console/institutions?state=Maharashtra").get_data(as_text=True)
    assert 'value="accept"' not in page and 'value="reserve"' not in page and 'value="reinvite"' in page
    assert ">Record the marks</a>" not in page and "Select and Reserve list follow the marks" not in page
    for action in ("accept", "reserve"):
        answer = _act(officer, never, action).get_data(as_text=True)
        assert "Never College has not completed its registration yet" in answer and "↩ Back to invited mails the link once more" in answer
        assert _status(app, never) == "declined"
    # one selected before it registered that has switched its assessment on stays as 1.2.173 left it: it can still be moved
    busy = _insert(app, "Busy College", "Maharashtra", "Nagpur", "accepted", 70, head_name="", invited_by=1, test_on=1,
                   coord_email="coord@busy.example")
    page = officer.get("/console/institutions?state=Maharashtra&status=accepted").get_data(as_text=True)
    assert 'value="reserve"' in page
    _act(officer, busy, "reserve")
    assert _status(app, busy) == "reserve"
    # Undo leaves a row that never registered pending: it goes back to invited from there too
    stray = _insert(app, "Stray College", "Maharashtra", "Nashik", "pending", head_name="", invited_by=1, coord_email="coord@stray.example")
    page = officer.get("/console/institutions?state=Maharashtra&status=pending").get_data(as_text=True)
    assert 'value="reinvite"' in page and 'value="accept"' not in page
    assert "back to identified · invited" in _act(officer, stray, "reinvite").get_data(as_text=True)
    assert _status(app, stray) == "identified"


def test_a_district_counts_once_whatever_its_spelling():
    from kts import heis as HEI
    count = HEI.districts_reached

    def of(state, *districts):
        return count([(state, d) for d in districts])
    assert of("Gujarat", "Kachchh", "KUTCH", "Kachchh Bhuj", "Kachchh (Bhuj)", "Vadodara", "Vadodra", "Baroda") == 2
    assert of("Karnataka", "Bangalore", "Bengaluru", "BANGALORE URBAN", "Gulbarga/Kalaburagi", "Kalaburagi") == 2
    assert of("Karnataka", "Bengaluru", "Bengaluru Rural") == 2            # two districts
    assert of("Tamil Nadu", "Kanchipuram", "Kancheepuram", "Chengalpet", "Chengalpattu", "Villupuram", "Vilupuram", "Kallakurichi",
              "Kallakkurichi", "Thiruvallur", "Tiruvallur") == 5
    assert of("Tamil Nadu", "Thiruvallur", "Thiruvarur", "Tiruppur", "Tirupathur", "Tiruvannamalai") == 5   # five districts
    assert of("Puducherry", "Pondicherry", "Puducherry", "Karaikal", "Karikal", "Puducherry District") == 2
    assert of("Uttar Pradesh", "Siddharth Nagar", "Siddharthnagar", "Kanpur Nagar", "Kanpur", "Gautam Buddha Nagar",
              "Gautambuddh Nagar") == 3
    assert of("Uttar Pradesh", "Kanpur", "Kanpur Dehat", "Rae Bareli", "Raebareli", "Bareilly") == 4
    assert of("Maharashtra", "Mumbai", "Mumbai City", "Mumbai Suburban", "PUNE", "Pune District") == 3
    assert of("Telangana", "Ranga Reddy", "Rangareddy", "Rangareddy916") == 1
    assert of("Punjab", "Sri Muktsar Sahib", "Muktsar") == 1 and of("Haryana", "Jhajjar", "Jajhar") == 1
    assert of("West Bengal", "North 24 Parganas", "South 24 Parganas", "Kolkata", "Calcutta") == 3
    assert of("Goa", "", None, "  ") == 0
    # a name of two States/UTs is two districts
    assert count([("Chhattisgarh", "Bilaspur"), ("Himachal Pradesh", "Bilaspur")]) == 2
    # two districts stay two: by the letters of the first words, a word in brackets that tells them apart, a name of its own
    assert of("Chhattisgarh", "Balod", "Baloda Bazar", "Baloda Bazar-Bhatapara", "Balodabazar") == 2
    assert of("Assam", "Kamrup", "Kamrup (Metro)", "Kamrup Metropolitan", "Kamrup Metro") == 2
    assert of("West Bengal", "24 Parganas (North)", "24 Parganas (South)") == 2
    assert of("Karnataka", "Bengaluru Urban", "Bengaluru (Rural)") == 2 and of("Rajasthan", "Jaipur", "Jaipur (Rural)") == 2
    assert of("Maharashtra", "Mumbai", "Mumbai (Suburban)", "Mumbai Suburb") == 2
    assert of("Punjab", "SAS Nagar", "Mohali", "SAS Nagar (Mohali)", "Sangrur") == 2
    assert of("Uttar Pradesh", "Bareilly", "Rae Bareilly") == 2 and of("Uttar Pradesh", "Kanpur Nagar", "Kanpur (Dehat)") == 2
    # and one district stays one
    assert of("Bihar", "Gaya", "Gaya Ji", "Gayaji") == 1 and of("Himachal Pradesh", "Lahaul and Spiti", "Lahaul & Spiti") == 1
    assert of("Andhra Pradesh", "Anantapuramu", "Anantapur") == 1 and of("West Bengal", "North 24 pargana", "North 24 Parganas") == 1
    assert of("Gujarat", "Kachchh (Bhuj)", "Kutch") == 1 and of("Karnataka", "Bengaluru (Urban)", "Bangalore") == 1


def test_the_states_and_uts_and_the_districts_of_the_pages():
    app = _app()
    for name, state, district, status in (("Bhuj College", "Gujarat", "Kutch", "accepted"), ("Mandvi College", "Gujarat", "Kachchh", "accepted"),
                                          ("Daman College", "Dadra and Nagar Haveli and Daman and Diu", "Daman", "accepted"),
                                          ("Kochi College", "Kerala", "Ernakulam", "accepted"),
                                          ("Kavaratti College", "Lakshadweep", "Kavaratti", "accepted"),
                                          ("Panaji College", "Goa", "North Goa", "pending"),
                                          ("Karaikal College", "Puducherry", "Karaikal", "reserve")):
        _insert(app, name, state, district, status, 70)
    page = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    pi = page[page.index('<section class="pi"'):page.index('class="table-wrap"')]
    # four States and Union Territories of the 36 (two rows of Annexure-I); four districts (Kachchh once)
    assert '<div class="num">4</div><div class="lbl">States and UTs</div>' in pi and "<bdi>4 of 36</bdi>" in pi
    assert '<div class="num">4</div><div class="lbl">Districts reached</div>' in pi
    # the list holds the institution of the reserve list of Puducherry too (1.2.177); the figures above count only the selected
    assert "6 institutions from 5 States/UTs" in page
    states = json.loads((ROOT / "data" / "states.json").read_text(encoding="utf-8"))
    assert (len(states["states"]), len(states["union_territories"])) == (28, 8)
    # the home page counts the same States/UTs: not Goa, where an institution has only registered
    home = app.test_client().get("/?lang=en").get_data(as_text=True)
    glance = home[home.index("<h2>At a glance</h2>"):]
    cards = re.findall(r'<div class="num">([^<]+)</div><div class="lbl">([^<]+)</div>', glance[:glance.index("</section>")])
    assert [(n.strip(), label) for n, label in cards][:2] == [("5", "Participating institutions"), ("4", "States and UTs")]


def test_the_texts_in_23_languages():
    from kts import drive as DRIVE
    from kts.i18n import CATALOG
    old = "with a reserve list of ordinarily up to 20 per cent of that number"
    assert sorted(CATALOG) == sorted(LANGS)
    for code in LANGS:
        c = CATALOG[code]
        assert "20" not in c["ng.rank"] and "২০" not in c["ng.rank"] and "२०" not in c["ng.rank"] and "۲۰" not in c["ng.rank"], code
        for key in ("ng.rank", "hei.any_number", "hei.reserve_h", "hei.reserve_intro"):
            assert c[key].strip() and "\n" not in c[key], (code, key)
            assert code == "en" or c[key] != CATALOG["en"][key], (code, key)
        assert len(c["hei.reserve_h"]) < 60, code
    en = CATALOG["en"]
    # the Guidelines give the key points of the Ministry's letter: without its 20 per cent, and without a sentence of CICT's own
    assert old not in en["ng.rank"] and "limit" not in en["ng.rank"]
    assert en["ng.rank"].endswith("the other eligible institutions, in the order of their marks, form the reserve list.")
    assert en["hei.any_number"].startswith("Any number of institutions of a State/UT may register.")
    assert en["hei.reserve_h"] == "Reserve list"
    app = _app()
    client = app.test_client()
    guide = client.get("/nodal-guidelines?lang=en")
    if guide.status_code == 404:
        from flask import url_for
        with app.test_request_context():
            guide = client.get(url_for("public.nodal_guidelines", lang="en"))
    text = guide.get_data(as_text=True)
    assert en["ng.rank"] in text and "20 per cent" not in text
    assert en["hei.any_number"] in client.get("/institutions/register?lang=en").get_data(as_text=True)
    with app.app_context():
        code = DRIVE.code_of("Puducherry")
    assert en["hei.any_number"] in client.get(f"/join/{code}?lang=en").get_data(as_text=True)
    for lang in ("ta", "hi", "bn", "ks"):
        assert CATALOG[lang]["hei.any_number"] in client.get(f"/institutions/register?lang={lang}").get_data(as_text=True), lang
        with app.test_request_context():
            from flask import url_for
            path = url_for("public.nodal_guidelines", lang=lang)
        assert CATALOG[lang]["ng.rank"] in client.get(path).get_data(as_text=True), lang

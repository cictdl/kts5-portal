"""
The Participating Institutions in two sections (1.2.229). CICT, 26 November 2026: "one major update needed. I want two section.
Participating Institutions registered (verified) and Nodal Officer given list of selected institutions. Update very carefully";
then, with the 31 workbooks of Annexure-II of the Console (one for each row of Annexure-I, 1,373 institutions): "Make these lists as
Participating registered Insitutions. dont send any emails". Asked of the institutions of those lists that are declined now: "Show
only"; of the institutions accepted since: "Yes, show them"; of the number at a glance: "Registered total everywhere"; of an
institution that registers after the list of its State/UT: "Under Selected".

The page lists the Participating Institutions registered - those that take part and, with them, the institutions of the 31 lists
that are declined now - and then the lists of the selected institutions given by the Nodal Officers, the 19 States/UTs whose list
has come. The number of the Participating Institutions registered follows wherever it is public. Nothing is written: a declined
institution stays declined at the sign-in, in the Console and for the nominations; no mail.

    python -m pytest tests/test_two_sections_1126.py -q
"""
import json
import re
from html import unescape

import pytest

from conftest import ROOT, make_app
from test_reserve_1111 import LANGS, _insert

# the 19 States/UTs whose Nodal Officer had given the list by 26 November 2026
LISTED = ("Andhra Pradesh", "Arunachal Pradesh", "Assam", "Chhattisgarh", "Goa", "Gujarat", "Himachal Pradesh", "Jharkhand",
          "Madhya Pradesh", "Maharashtra", "Odisha", "Rajasthan", "Sikkim", "Telangana", "Tripura",
          "Dadra and Nagar Haveli and Daman and Diu", "Jammu and Kashmir", "Ladakh", "Puducherry")
SELECTED = "List of selected institutions given by the Nodal Officers"
REGISTERED = "Participating Institutions registered (verified)"
LISTS = json.loads((ROOT / "data" / "registered_lists.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def fresh_figures():
    """The figures of /progress and of the pages /join are kept for some seconds: not from one test to the next."""
    from kts import dashboard, drive
    from kts.utils import limiter
    dashboard._PIPE["data"] = None
    drive.clear()
    limiter._hits.clear()
    yield
    dashboard._PIPE["data"] = None
    drive.clear()
    limiter._hits.clear()


def _page(app, path="/institutions?lang=en"):
    r = app.test_client().get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def _main(app, lang="en"):
    page = _page(app, f"/institutions?lang={lang}")
    return page[page.index("<main"):page.index("</main>")]


def _sections(main):
    """{key: the HTML of the section} in the order of the page."""
    marks = [(m.group(1), m.start()) for m in re.finditer(r'<section class="hei-sec" aria-labelledby="hei-([a-z]+)">', main)]
    return {key: main[at:(marks[i + 1][1] if i + 1 < len(marks) else len(main))] for i, (key, at) in enumerate(marks)}


def _names(part):
    return [unescape(n) for n in re.findall(r'<td class="num">\d+</td><td lang="en" dir="ltr">([^<]+)</td>', part)]


def _registered(app):
    from kts import heis as HEI
    with app.app_context():
        return [(r["name"], r["state"], r["status"]) for r in HEI.registered_rows()]


def test_the_31_lists():
    states = json.loads((ROOT / "data" / "states.json").read_text(encoding="utf-8"))
    every = states["states"] + states["union_territories"]
    # of the 1,373 rows of the workbooks, without the ten that carry the name of a person in place of an institution
    assert len(LISTS["lists"]) == 31 and LISTS["total"] == 1363 == sum(len(one["institutions"]) for one in LISTS["lists"])
    assert "the ten that carry the name of a person in place of an institution are left out" in LISTS["about"]
    assert sorted(s for one in LISTS["lists"] for s in one["states"]) == sorted(every) and len(every) == 36
    nodal = json.loads((ROOT / "data" / "nodal_heis.json").read_text(encoding="utf-8"))
    assert sorted([h["state"], *h.get("covers", [])] for h in nodal) == sorted(one["states"] for one in LISTS["lists"])
    # of an institution: its name, its district and its type - what the public page shows; nothing of a person
    assert set(LISTS) == {"about", "total", "lists"} and all(set(one) == {"states", "nodal", "institutions"} for one in LISTS["lists"])
    for one in LISTS["lists"]:
        for row in one["institutions"]:
            assert len(row) == 3 and row[0] == row[0].strip() and row[0] and row[2] in states["college_types"], row
    flat = json.dumps(LISTS, ensure_ascii=False)
    assert "@" not in flat and not re.search(r"(?<!\d)\d{10}(?!\d)", flat)
    size = {one["states"][0]: len(one["institutions"]) for one in LISTS["lists"]}
    assert (size["Puducherry"], size["Maharashtra"], size["Jammu and Kashmir"], size["Tamil Nadu"], size["Nagaland"]) == (16, 192, 71, 182, 1)


def test_the_states_whose_list_has_been_given():
    from kts import heis as HEI
    from kts.db import NODAL_LISTS_1126
    states = json.loads((ROOT / "data" / "states.json").read_text(encoding="utf-8"))
    every = states["states"] + states["union_territories"]
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        given = HEI.listed_states()
        assert given == frozenset(LISTED) and len(given) == 19 and given <= set(every)
        assert {nodal_list["state"] for nodal_list in NODAL_LISTS_1126} <= given
        # a Union Territory that Annexure-I pairs with a State is with it: Ladakh, Dadra and Nagar Haveli and Daman and Diu
        assert all(set(HEI.group_of(state)) <= given for state in given)
        assert not any(set(HEI.group_of(state)) & given for state in every if state not in given)


def test_the_institutions_registered():
    """Those that take part, and those of the 31 lists that are declined now - by name, among the States/UTs of their list."""
    app = make_app(ADMIN_PASSWORD=None)
    _insert(app, "Pondicherry University", "Puducherry", "Pondicherry", "accepted")
    _insert(app, "Tagore Government Arts and science College", "Puducherry", "Pondicherry", "declined")      # of the list of Puducherry
    _insert(app, "SCHOOL of   physiotherapy", "Puducherry", "Pondicherry", "declined")                    # the same name, written otherwise
    _insert(app, "Never Listed College", "Puducherry", "Mahe", "declined")
    _insert(app, "New College since the lists", "Puducherry", "Yanam", "accepted")
    _insert(app, "PSMO COLLEGE", "Kerala", "Malappuram", "declined")                                         # of Kerala and Lakshadweep
    _insert(app, "Government College of Arts and Science, Kadmat", "Lakshadweep", "Lakshadweep", "declined")   # the Union Territory of that list
    _insert(app, "PSMO COLLEGE", "Tamil Nadu", "Chennai", "declined")                                        # the name of another list: not here
    _insert(app, "Sree Sankara College Kalady", "Kerala", "Ernakulam", "pending")                            # of the list, not decided again yet
    _insert(app, "Pending and never listed", "Kerala", "Kollam", "pending")
    _insert(app, "Kannur University", "Kerala", "Kannur", "identified", head_name="", invited_by=1, invite_token="t-kannur")
    rows = _registered(app)
    assert sorted(rows) == sorted([
        ("Pondicherry University", "Puducherry", "accepted"), ("Tagore Government Arts and science College", "Puducherry", "declined"),
        ("SCHOOL of   physiotherapy", "Puducherry", "declined"), ("New College since the lists", "Puducherry", "accepted"),
        ("PSMO COLLEGE", "Kerala", "declined"), ("Government College of Arts and Science, Kadmat", "Lakshadweep", "declined"),
        ("Sree Sankara College Kalady", "Kerala", "pending")])
    # in the order of the names, as the list was before
    assert [r[0].casefold() for r in rows] == sorted(r[0].casefold() for r in rows)


def test_a_name_as_many_times_as_its_list_has_it():
    from kts.db import NODAL_LISTS_1126
    telangana = next(one for one in LISTS["lists"] if one["states"] == ["Telangana"])
    assert sum(1 for row in telangana["institutions"] if row[0].casefold() == "avinash college of commerce") == 3
    assert sum(1 for row in telangana["institutions"] if row[0] == "University of Hyderabad") == 1
    note = next(nodal_list["note"] for nodal_list in NODAL_LISTS_1126 if nodal_list["key"] == "tg")
    app = make_app(ADMIN_PASSWORD=None)
    first = _insert(app, "Avinash college of commerce", "Telangana", "Rangareddy", "declined")
    taking = _insert(app, "Avinash College of Commerce", "Telangana", "Hyderabad", "accepted")
    same = _insert(app, "Avinash college of  commerce", "Telangana", "HYDERABAD", "declined")      # as the one that takes part stands
    later = _insert(app, "Avinash college of commerce", "Telangana", "Medchal", "declined")
    for_the_list = _insert(app, "AVINASH COLLEGE OF COMMERCE", "Telangana", "Secunderabad", "declined", decision_note=note)
    # the list has the name three times: the one that takes part, the one declined for the list of the Nodal Institution, then the
    # earliest; a declined one that would stand on the page exactly as one already there (name, district, type) is not repeated
    from kts import heis as HEI
    with app.app_context():
        ids = sorted(r["id"] for r in HEI.registered_rows())
    assert ids == sorted([first, taking, for_the_list]) and same not in ids and later not in ids
    # two declined that stand alike: one of them
    app = make_app(ADMIN_PASSWORD=None)
    one = _insert(app, "Avinash college of commerce", "Telangana", "Hyderabad", "declined")
    _insert(app, "Avinash College of Commerce", "Telangana", "hyderabad", "declined")
    other = _insert(app, "Avinash college of commerce", "Telangana", "Rangareddy", "declined")
    with app.app_context():
        assert sorted(r["id"] for r in HEI.registered_rows()) == sorted([one, other])
    app = make_app(ADMIN_PASSWORD=None)
    # once in its list and taking part: a declined one of the same name is not a second
    again = _insert(app, "University of Hyderabad", "Telangana", "Hyderabad", "declined")
    _insert(app, "University of Hyderabad", "Telangana", "Hyderabad", "accepted")
    with app.app_context():
        assert again not in [r["id"] for r in HEI.registered_rows()]
        assert sum(1 for r in HEI.registered_rows() if r["name"] == "University of Hyderabad") == 1


def _both_kinds():
    app = make_app(ADMIN_PASSWORD=None)
    ids = {
        "pu": _insert(app, "Pondicherry University", "Puducherry", "Pondicherry", "accepted",
                      coord_email="coord@pu.example", coord_mobile="9876500002", reg_token="tok-pu"),
        "late": _insert(app, "Late College", "Puducherry", "Mahe", "accepted", created="2026-11-27T06:00:00+00:00"),
        "tagore": _insert(app, "Tagore Government Arts and science College", "Puducherry", "Pondicherry", "declined",
                          coord_email="coord@tagore.example", coord_mobile="9876500001", reg_token="tok-tagore"),
        "never": _insert(app, "Never Listed College", "Puducherry", "Mahe", "declined"),
        "goa": _insert(app, "Panaji College", "Goa", "North Goa", "accepted"),
        "leh": _insert(app, "Leh College", "Ladakh", "Leh", "accepted"),
        "kochi": _insert(app, "Kochi College", "Kerala", "Ernakulam", "accepted"),
        "psmo": _insert(app, "PSMO COLLEGE", "Kerala", "Malappuram", "declined"),
        "kadmat": _insert(app, "Government College of Arts and Science, Kadmat", "Lakshadweep", "Lakshadweep", "declined"),
        "madurai": _insert(app, "Madurai College", "Tamil Nadu", "Madurai", "accepted"),
    }
    return app, ids


def test_the_two_sections_of_the_page():
    app, _ids = _both_kinds()
    main = _main(app)
    index = main[main.index('<ul class="hei-secs"'):main.index("</ul>", main.index('<ul class="hei-secs"'))]
    assert re.findall(r'<a href="#hei-([a-z]+)"><b>([^<]+)</b></a>', index) == [("registered", REGISTERED), ("selected", SELECTED)]
    assert "9 institutions from 6 States/UTs" in index and "4 institutions from 3 States/UTs" in index
    assert re.findall(r'<h2 id="hei-([a-z]+)"[^>]*>([^<]+)</h2>', main) == [("registered", REGISTERED), ("selected", SELECTED)]
    sections = _sections(main)
    assert list(sections) == ["registered", "selected"]
    registered, selected = sections["registered"], sections["selected"]
    assert "<p><b>9 institutions from 6 States/UTs</b></p>" in registered and "<p><b>4 institutions from 3 States/UTs</b></p>" in selected
    # the institutions registered: every State/UT, the States and then the Union Territories, with the anchors of before
    assert re.findall(r'<h3 id="([a-z-]+)"', registered) == ["st-goa", "st-kerala", "st-tamil-nadu", "st-ladakh", "st-lakshadweep", "st-puducherry"]
    assert re.findall(r'<a href="#([a-z-]+)">', registered) == ["st-goa", "st-kerala", "st-tamil-nadu", "st-ladakh", "st-lakshadweep", "st-puducherry"]
    assert _names(registered) == ["Panaji College", "Kochi College", "PSMO COLLEGE", "Madurai College", "Leh College",
                                  "Government College of Arts and Science, Kadmat", "Late College", "Pondicherry University",
                                  "Tagore Government Arts and science College"]
    assert '<h3 id="st-puducherry" style="margin-top:28px;font-size:1.3rem">Puducherry <span class="small muted">(3)</span></h3>' in registered
    # the lists of the Nodal Officers: the States/UTs whose list has come, with the institutions that take part there now
    assert re.findall(r'<h3 id="([a-z-]+)"', selected) == ["sel-goa", "sel-ladakh", "sel-puducherry"]
    assert re.findall(r'<a href="#([a-z-]+)">', selected) == ["sel-goa", "sel-ladakh", "sel-puducherry"]
    assert _names(selected) == ["Panaji College", "Leh College", "Late College", "Pondicherry University"]
    assert '<h3 id="sel-puducherry" style="margin-top:28px;font-size:1.3rem">Puducherry <span class="small muted">(2)</span></h3>' in selected
    # declined and of no list: nowhere; declined and of a list: registered, not selected
    assert "Never Listed College" not in main and "Tagore Government Arts and science College" not in selected
    # the anchors are one each; the sections are closed; the headings in order
    anchors = re.findall(r' id="([^"]+)"', main)
    assert len(anchors) == len(set(anchors)) and '<h2 id="st-' not in main and main.count("<h1") == 1
    assert main.count("</section>") == main.count("<section")
    assert main.index('id="pi-h"') < main.index('id="hei-registered"') < main.index('id="st-goa"') < main.index('id="hei-selected"') < main.index('id="sel-goa"')


def test_the_number_everywhere():
    """CICT: "Registered total everywhere" - nine institutions registered (six take part, three of the lists are declined now)."""
    from kts.db import set_setting
    app, _ids = _both_kinds()
    with app.app_context():
        set_setting("dashboard.public", "1")
    # /institutions at a glance: the number, the States/UTs, the districts, the types and the bars of the rows of Annexure-I
    page = _page(app)
    pi = page[page.index('<section class="pi"'):page.index('<ul class="hei-secs"')]
    assert '<div class="num">9</div><div class="lbl">Participating Institutions registered</div>' in pi
    assert '<div class="num">6</div><div class="lbl">' in pi                                    # States and UTs
    bars = dict(re.findall(r'<span class="pi-name">([^<]+)</span>.*?<bdi dir="ltr"><b>(\d+)</b></bdi>', pi, flags=re.S))
    assert (bars["Puducherry"], bars["Kerala and Lakshadweep"], bars["Goa"], bars["Jammu and Kashmir and Ladakh"]) == ("3", "3", "1", "1")
    assert bars["Tamil Nadu and Andaman and Nicobar Islands"] == "1" and sum(int(n) for n in bars.values()) == 9
    assert sum(int(n) for n in re.findall(r"</span><b>(\d+)</b>", re.findall(r'<ul class="pi-legend">(.*?)</ul>', pi, flags=re.S)[0])) == 9
    # the home page
    home = _page(app, "/?lang=en")
    assert '<div class="num">9</div><div class="lbl">Participating Institutions registered</div>' in home
    # /progress and its figures
    progress = app.test_client().get("/progress.json?lang=en").get_json()
    assert progress["flat"]["participating"] == 9 and progress["flat"]["st_participating"] == 9
    assert progress["flat"]["testing_of"] == "0 of 6"      # the institutions that assess online: of those that take part, as before
    # the Nodal Institutions, the page of a State/UT, the dashboard
    from kts import heis as HEI
    with app.test_request_context("/nodal-institutions?lang=en"):
        from kts.public import _nodal_table
        rows, total = _nodal_table()
        now = {r["state"]: r["now"] for r in rows}
        assert (now["Puducherry"], now["Kerala"], now["Goa"], now["Jammu and Kashmir"], now["Tamil Nadu"], total["now"]) == (3, 3, 1, 1, 1, 9)
        from kts import dashboard as D
        fig = D.figures()
        assert fig["total"]["inst_sel"] == 9 and {r["state"]: r["inst_sel"] for r in fig["states"] if r["inst_sel"]} == {
            "Puducherry": 3, "Kerala": 3, "Goa": 1, "Jammu and Kashmir": 1, "Tamil Nadu": 1}
        assert len(HEI.registered_rows()) == 9
    # the page of a State/UT: while the institutions assess, of those that take part; after the last day, the number registered
    from kts import drive
    assert "0 of 2 Participating Institutions of Puducherry have opened the online test" in re.sub(r"<[^>]+>", "", _page(app, "/join/py?lang=en"))
    with app.app_context():
        assert drive.table()["Puducherry"]["participating"] == 2 and drive.table()["Puducherry"]["listed"] == 3
        assert drive.table()["Kerala"]["participating"] == 1 and drive.table()["Kerala"]["listed"] == 3
        set_setting("hei.end", "2026-11-01")
        set_setting("reg.end", "2026-11-02")
    drive.clear()
    assert "Participating Institutions registered: 3" in re.sub(r"<[^>]+>", "", _page(app, "/join/py?lang=en"))
    dash = _page(app, "/dashboard?lang=en")
    block = dash[dash.index('id="d-PY"'):]
    block = block[:block.index("</details>")]
    assert "Participating Institutions registered: 3" in re.sub(r"<[^>]+>", "", block)
    assert re.findall(r'<li><span lang="en" dir="ltr">([^<]+)</span>', block) == ["Late College", "Pondicherry University",
                                                                                 "Tagore Government Arts and science College"]


def test_nothing_is_written_and_a_declined_institution_stays_declined():
    from kts import campus as CAMP
    from kts import heis as HEI
    from kts.db import query, set_setting
    app, ids = _both_kinds()
    with app.app_context():
        before = {r["id"]: (r["status"], r["updated_at"]) for r in query("SELECT id, status, updated_at FROM institutions")}
        count = {t: query(f"SELECT COUNT(*) AS n FROM {t}", one=True)["n"] for t in ("outbox", "audit_log", "settings")}
    for path in ("/institutions?lang=en", "/?lang=en", "/progress?lang=en", "/nodal-institutions?lang=en", "/join/py?lang=en"):
        _page(app, path)
    with app.app_context():
        assert {r["id"]: (r["status"], r["updated_at"]) for r in query("SELECT id, status, updated_at FROM institutions")} == before
        assert {t: query(f"SELECT COUNT(*) AS n FROM {t}", one=True)["n"] for t in ("outbox", "audit_log", "settings")} == count
        # the declined institution of a list: shown, and nothing else - no sign-in, not among those a student can choose
        assert CAMP.institutions_of("coord@tagore.example") == []
        taking = [r["id"] for _state, items in HEI.accepted_by_state(["Puducherry"], reserve=True) for r in items]
        assert ids["tagore"] not in taking and sorted(taking) == sorted([ids["pu"], ids["late"]])
        # the link of the nomination: of an institution that takes part only
        assert CAMP.registration_token("tok-tagore") is None and CAMP.registration_token("tok-pu")["id"] == ids["pu"]
        set_setting("inst.code_mail", "0")      # as on the portal since 1.2.216: the e-mail address and the mobile number, no code

    def sign_in(email, mobile):
        client = app.test_client()
        client.get("/institution/login")
        with client.session_transaction() as s:
            token = s["_csrf"]
        return client, client.post("/institution/login", data={"_csrf": token, "email": email, "mobile": mobile})

    client, refused = sign_in("coord@tagore.example", "9876500001")
    assert refused.status_code == 400 and not refused.headers.get("Location")
    assert client.get("/institution").headers["Location"].endswith("/institution/login")
    client, opened = sign_in("coord@pu.example", "9876500002")      # the control: an institution that takes part signs in
    assert opened.status_code == 302 and opened.headers["Location"].endswith("/institution")


def test_one_section_alone():
    # no State/UT with a list has an institution that takes part: the institutions registered alone, no index of the two
    app = make_app(ADMIN_PASSWORD=None)
    _insert(app, "Kochi College", "Kerala", "Ernakulam", "accepted")
    _insert(app, "Tagore Government Arts and science College", "Puducherry", "Pondicherry", "declined")
    main = _main(app)
    assert list(_sections(main)) == ["registered"] and 'class="hei-secs"' not in main and SELECTED not in main
    assert f">{REGISTERED}</h2>" in main and main.count("2 institutions from 2 States/UTs") == 1
    assert _names(main) == ["Kochi College", "Tagore Government Arts and science College"]
    # no institution: no section
    main = _main(make_app(ADMIN_PASSWORD=None))
    assert _sections(main) == {} and "No institution has been accepted yet." in main and SELECTED not in main and REGISTERED not in main


def test_the_two_headings_in_23_languages():
    from kts.i18n import CATALOG
    en = CATALOG["en"]
    assert en["hei.sec_selected"] == SELECTED and en["hei.sec_registered"] == REGISTERED and len(en) == 1553
    assert sorted(CATALOG) == sorted(LANGS) and len(LANGS) == 23
    app = make_app(ADMIN_PASSWORD=None)
    _insert(app, "Panaji College", "Goa", "North Goa", "accepted")
    _insert(app, "Kochi College", "Kerala", "Ernakulam", "accepted")
    seen = set()
    for code in LANGS:
        c = CATALOG[code]
        assert list(c)[list(c).index("hei.count") + 1:][:2] == ["hei.sec_registered", "hei.sec_selected"], code
        for key in ("hei.sec_selected", "hei.sec_registered"):
            text = c[key]
            assert text and text.strip() == text and "\n" not in text and "  " not in text and "{" not in text, (code, key)
            assert text[-1] not in ".।॥؟۔!:;,", (code, key)                    # a heading
            assert code == "en" or text not in (SELECTED, REGISTERED), (code, key)
            assert (code, text) not in seen
            seen.add((code, text))
        assert c["hei.sec_selected"] != c["hei.sec_registered"], code
        assert c["hei.sec_registered"].endswith(")") and "(" in c["hei.sec_registered"], code      # "(verified)"
        main = _main(app, code)
        assert [(key, unescape(text)) for key, text in re.findall(r'<h2 id="hei-([a-z]+)"[^>]*>([^<]+)</h2>', main)] == [
            ("registered", c["hei.sec_registered"]), ("selected", c["hei.sec_selected"])], code
        sections = _sections(main)
        assert _names(sections["registered"]) == ["Panaji College", "Kochi College"] and _names(sections["selected"]) == ["Panaji College"], code

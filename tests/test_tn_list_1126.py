"""
The list of the Nodal Institution of Tamil Nadu and the Andaman and Nicobar Islands (1.2.230). CICT, 26 November 2026, with the file
"KTS5-evaluation-sheet-Annexure-II - selection and reserve list - 23.11.2026 - send to CICT" of the Central University of Tamil Nadu
(50 selected: 49 of Tamil Nadu, 1 of the Andaman and Nicobar Islands; 10 on the reserve list): "Tamil Nadu and Andaman and Nicobar
Island list from Nodal Officer selected list". Asked of the others: "Yes, decline the others"; of the reserve list: "Keep the 10";
of an institution not on the list that has submitted a nomination: "Decline and withdraw". No mail.

    python -m pytest tests/test_tn_list_1126.py -q
"""
import json
import re

from conftest import make_app
from test_reserve_1111 import _insert
from test_strict_sk_rj_1126 import _application

BEFORE = "2026-11-20T06:00:00+00:00"
AFTER = "2026-11-26T15:00:00+00:00"
MARKS = ("migrate.tn_list_1126", "migrate.an_list_1126", "migrate.tn_strict_1126", "migrate.an_strict_1126")
OLAKKUR = "SARASWATHY COLLEGE OF ARTS AND SCIENCE OLAKKUR TINDIVANAM TALUK VILLUPURAM DIST 604 305"
TWICE = "Dhanalakshmi Srinivasan agricultural College"


def _entry(key):
    from kts.db import NODAL_LISTS_1126
    return next(nodal_list for nodal_list in NODAL_LISTS_1126 if nodal_list["key"] == key)


def test_the_two_lists():
    from kts.db import NODAL_LISTS_1126
    tn, an = _entry("tn"), _entry("an")
    names = [r[0] for r in tn["listed"]]
    assert tn["state"] == "Tamil Nadu" and len(names) == 59 and len({" ".join(n.lower().split()) for n in names}) == 59
    assert names[0] == OLAKKUR and "Central University of Tamil Nadu" in names                 # as the portal writes the first
    assert names[49:] == ["Dhanalakshmi Srinivasan university", "KONGUNADU INTEGRATED COLLEGE OF EDUCATION",
                          "WAVOO WAJEEHA WOMEN'S COLLEGE OF ARTS AND SCIENCE", "VLB JANAKIAMMAL  COLLEGE OF ARTS AND SCIENCE", "PARK'S COLLEGE",
                          "St.Peter's Institute of Higher Education and Research", "Aksheyaa college of arts and science",
                          "Government College of Education, Muthambal sathiram", TWICE, "Alagappa University"]      # the reserve list: kept
    assert tn["match"] == {TWICE: {"aishe_code": "C-60420", "first": True}}
    assert tn["release"] == an["release"] == "release 1.2.230" and tn["until"] == an["until"] == "2026-11-26T14:00:00+00:00"
    assert tn["note"] == ("Not among the 59 institutions of the list of the Nodal Institution of Tamil Nadu (Central University of Tamil Nadu), "
                          "26 November 2026")
    assert an["state"] == "Andaman and Nicobar Islands" and [r[0] for r in an["listed"]] == ["Jawaharlal Nehru Rajkeeya Mahavidyala"]
    assert an["note"] == ("Not among the 1 institution of the list of the Nodal Institution of Andaman and Nicobar Islands (Central University of "
                          "Tamil Nadu), 26 November 2026")
    assert all(tuple(r[1:]) == ("", "", "") for r in tn["listed"] + an["listed"])              # no e-mail address or number is changed
    assert [nodal_list["key"] for nodal_list in NODAL_LISTS_1126][-2:] == ["an", "tn"] and len(NODAL_LISTS_1126) == 13
    # every list is a tuple of rows of four, the list of one institution too
    assert all(isinstance(row, tuple) and len(row) == 4 for nodal_list in NODAL_LISTS_1126 for row in nodal_list["listed"])


def _status(app, table, iid):
    from kts.db import query
    with app.app_context():
        return dict(query(f"SELECT * FROM {table} WHERE id = ?", (iid,), one=True))


def test_the_others_are_declined_and_their_nominations_withdrawn():
    from kts.db import execute, init_db, query
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute(f"DELETE FROM settings WHERE key IN ({','.join('?' * len(MARKS))})", MARKS)
    names = [r[0] for r in _entry("tn")["listed"]]
    # the agricultural college is registered twice: the one of the list has the AISHE code of the list
    copy = _insert(app, TWICE, "Tamil Nadu", "District", "accepted", created=BEFORE, ref="KTS5-HEI-04900", aishe_code="")
    ids = {n: _insert(app, n, "Tamil Nadu", "District", "accepted", created=BEFORE, ref=f"KTS5-HEI-04{i:03d}",
                      aishe_code="C-60420" if n == TWICE else f"C-{i}") for i, n in enumerate(names)}
    other = _insert(app, "JAMAL MOHAMED COLLEGE", "Tamil Nadu", "Tiruchirappalli", "accepted", created=BEFORE, ref="KTS5-HEI-04901")
    nominated = _insert(app, "Nominated College", "Tamil Nadu", "Madurai", "accepted", created=BEFORE, ref="KTS5-HEI-04902")
    nomination = _application(app, nominated, 31, "Tamil Nadu")
    listed_nomination = _application(app, ids["Alagappa University"], 32, "Tamil Nadu")
    # another registration of a college that is on the list, under which its nomination was submitted: left as it is
    second = _insert(app, "Kongunadu Arts and Science College", "Tamil Nadu", "Coimbatore", "accepted", created=BEFORE, ref="KTS5-HEI-04907",
                     aishe_code="41106")
    second_nomination = _application(app, second, 33, "Tamil Nadu")
    # and one without a nomination: declined with the others
    campus = _insert(app, "Shanmugha Arts, Science, Technology & Reserch Academy (SASTRA CHENNAI CAMPUS)", "Tamil Nadu", "CHENNAI", "accepted",
                     created=BEFORE, ref="KTS5-HEI-04908")
    late = _insert(app, "Late College", "Tamil Nadu", "Salem", "accepted", created=AFTER, ref="KTS5-HEI-04903")
    island = _insert(app, "Jawaharlal Nehru Rajkeeya Mahavidyala", "Andaman and Nicobar Islands", "South Andaman", "accepted", created=BEFORE,
                     ref="KTS5-HEI-04904")
    island_other = _insert(app, "Port Blair College", "Andaman and Nicobar Islands", "South Andaman", "accepted", created=BEFORE, ref="KTS5-HEI-04905")
    kerala = _insert(app, "Kochi College", "Kerala", "Ernakulam", "accepted", created=BEFORE, ref="KTS5-HEI-04906")
    with app.app_context():
        mails = query("SELECT COUNT(*) AS n FROM outbox", one=True)["n"]
    init_db(app)
    # the 59 of the list - the 49 selected and the 10 of the reserve list - stay, with the one registered after the list
    assert all(_status(app, "institutions", i)["status"] == "accepted" for i in ids.values())
    assert _status(app, "institutions", late)["status"] == "accepted" and _status(app, "institutions", island)["status"] == "accepted"
    assert _status(app, "institutions", kerala)["status"] == "accepted"
    # the others are declined: the copy, the one not on the list, the one of the Union Territory, and the one that had nominated
    assert _status(app, "institutions", second)["status"] == "accepted" and _status(app, "applications", second_nomination)["status"] == "submitted"
    for iid in (copy, other, island_other, nominated, campus):
        row = _status(app, "institutions", iid)
        assert row["status"] == "declined" and row["decision_note"].startswith("Not among the "), row["name"]
    assert _status(app, "institutions", other)["decision_note"] == _entry("tn")["note"]
    assert _status(app, "institutions", island_other)["decision_note"] == _entry("an")["note"]
    # its nomination is withdrawn, not deleted; the nomination of an institution of the list is as it was
    withdrawn = _status(app, "applications", nomination)
    assert withdrawn["status"] == "withdrawn" and withdrawn["remarks"].startswith(
        "Withdrawn: the institution is not on the list of the Nodal Institution of Tamil Nadu")
    assert _status(app, "applications", listed_nomination)["status"] == "submitted"
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM outbox", one=True)["n"] == mails                      # no mail
        marks = {k: json.loads(query("SELECT value FROM settings WHERE key = ?", (k,), one=True)["value"]) for k in MARKS}
        lines = [(r["action"], r["entity_id"]) for r in query("SELECT action, entity_id FROM audit_log WHERE actor = 'release 1.2.230'")]
    assert len(marks["migrate.tn_list_1126"]["listed"]) == 59
    assert sorted(marks["migrate.tn_list_1126"]["declined"]) == ["KTS5-HEI-04900", "KTS5-HEI-04901", "KTS5-HEI-04908"]
    assert sorted(marks["migrate.tn_list_1126"]["kept_nominated"]) == ["KTS5-HEI-04902", "KTS5-HEI-04907"]
    assert marks["migrate.tn_strict_1126"]["declined"] == ["KTS5-HEI-04902"] and marks["migrate.tn_strict_1126"]["spared"] == ["KTS5-HEI-04907"]
    assert marks["migrate.tn_strict_1126"]["applications_withdrawn"] == ["KTS5-SKRJ-0031"]
    assert marks["migrate.an_list_1126"]["declined"] == ["KTS5-HEI-04905"] and marks["migrate.an_strict_1126"]["declined"] == []
    assert "spared" not in marks["migrate.an_strict_1126"]
    assert sorted(lines) == sorted([("institution_declined", copy), ("institution_declined", other), ("institution_declined", island_other),
                                    ("institution_declined", nominated), ("institution_declined", campus), ("application_withdrawn", nomination)])
    # once: a second start changes nothing, and CICT may accept one again
    with app.app_context():
        execute("UPDATE institutions SET status = 'accepted' WHERE id = ?", (other,))
    init_db(app)
    assert _status(app, "institutions", other)["status"] == "accepted"
    with app.app_context():
        execute("UPDATE institutions SET status = 'declined' WHERE id = ?", (other,))
    # the page: Tamil Nadu and the Union Territory are now among the lists of the Nodal Officers, with those that take part; the one
    # declined that was on the public list on 26 November (JAMAL MOHAMED COLLEGE: registered after the 31 lists) is shown still under
    # the institutions registered, and one of no list is not
    page = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    registered = page[page.index('<h2 id="hei-registered"'):page.index('<h2 id="hei-selected"')]
    selected = page[page.index('<h2 id="hei-selected"'):]
    assert re.findall(r'<h3 id="(sel-[a-z-]+)"', selected) == ["sel-tamil-nadu", "sel-andaman-and-nicobar-islands"]
    tamil_nadu = selected[selected.index('id="sel-tamil-nadu"'):selected.index('id="sel-andaman-and-nicobar-islands"')]
    assert '<span class="small muted">(61)</span>' in tamil_nadu and "Late College" in tamil_nadu and "Alagappa University" in tamil_nadu
    assert "Kongunadu Arts and Science College" in tamil_nadu          # the second registration that holds the nomination: for CICT to see
    assert "JAMAL MOHAMED COLLEGE" not in selected and "Nominated College" not in selected and "Port Blair College" not in selected
    assert "JAMAL MOHAMED COLLEGE" in registered and "Alagappa University" in registered
    assert "Nominated College" not in page and "Port Blair College" not in page
    assert registered.count(">" + TWICE + "<") == 1                                                # the declined copy stands as the other: once

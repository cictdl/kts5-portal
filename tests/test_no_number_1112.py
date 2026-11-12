"""
No number "to be selected" for a State/UT on the public pages; the total of 1,000 stays (1.2.179; CICT, 12 November 2026: "To be
selected top ceiling should not be there", asked where: "everywhere public", and "Total 1,000. but any state and UT can have any
no").

    python -m pytest tests/test_no_number_1112.py -q
"""
import itertools
import re

from conftest import make_app

NUMBERS = itertools.count(1)
KEYS = ["dash.intro_plain", "dash.grid_note_plain", "pi.states_title_plain", "pg.states_title_plain", "join.title_plain",
        "join.share_msg_nonum", "join.board_note_nonum"]
LANGS = ["as", "bn", "brx", "doi", "en", "gu", "hi", "kn", "kok", "ks", "mai", "ml", "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd",
         "ta", "te", "ur"]


def _portal():
    from kts.db import execute, set_setting, utcnow
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for key, value in (("hei.end", "2099-12-31"), ("join.on", "1"), ("dashboard.public", "1"), ("hei.public", "1"),
                           ("stats.public", "1")):
            set_setting(key, value)
        # Puducherry (5 in Annexure-I): 7 selected; Tamil Nadu (50): 2
        for state, n in (("Puducherry", 7), ("Tamil Nadu", 2)):
            for i in range(n):
                name = f"{state} College {i}"
                execute("INSERT INTO institutions(ref, name, itype, state, district, inst_key, status, head_name, created_at, updated_at) "
                        "VALUES(?, ?, 'Government college', ?, 'District', ?, 'accepted', 'Dr. Head', ?, ?)",
                        (f"KTS5-HEI-6{next(NUMBERS):04d}", name, state, f"name:{name.lower()}|{state.lower()}", utcnow(), utcnow()))
    return app


def test_the_dashboard():
    app = _portal()
    page = app.test_client().get("/dashboard?lang=en").get_data(as_text=True)
    # the total stays
    kpis = page[page.index("dash-kpis"):page.index('<section class="card dash-map"')]
    assert '<div class="num">1,000</div><div class="lbl">To be selected</div>' in kpis
    # no number of a State/UT: the squares, their notes, the table, the blocks
    assert "Where the programme stands in each State/UT: the Participating Institutions selected and the students who took an institution&#39;s online test." in page
    assert "against the number" not in page and "No number in Annexure-I" not in page
    assert '<h2 id="dash-grid-h">Participating Institutions selected</h2>' in page
    assert "the darker the square, the more Participating Institutions it has" in page
    # shaded by the count against the State/UT with the most: Puducherry 7 the darkest, Tamil Nadu 2 of 7 lighter
    assert '<a class="dash-tile b4" href="#d-PY">' in page and '<a class="dash-tile b2" href="#d-TN">' in page
    py = page[page.index('href="#d-PY"'):]
    py = py[:py.index("</a>")]
    assert '<span class="dash-n" dir="ltr">7</span>' in py and "Participating Institutions selected: <bdi>7</bdi>" in py
    tn = page[page.index('href="#d-TN"'):]
    assert '<span class="dash-n" dir="ltr">2</span>' in tn[:tn.index("</a>")]
    head = page[page.index("<thead>"):page.index("</thead>")]
    assert "To be selected" not in head
    row = page[page.index('<tr id="st-PY">'):]
    row = row[:row.index("</tr>")]
    assert re.findall(r'<td class="num">([^<]*)</td>', row) == ["7", "0"]
    summary = page[page.index('id="d-PY"'):]
    assert "To be selected" not in summary[:summary.index("</summary>")]


def test_institutions_progress_and_the_state_pages():
    from kts import dashboard as D
    from kts import drive as DRIVE
    app = _portal()
    client = app.test_client()
    page = client.get("/institutions?lang=en").get_data(as_text=True)
    pi = page[page.index('<section class="pi"'):page.index("<p><b>")]
    assert "<bdi>9 of 1,000</bdi>" in pi                                   # the total stays
    assert '<h3 id="pi-states-h">Each row of Annexure-I: the Participating Institutions selected</h3>' in pi
    rows = re.findall(r'<span class="pi-name">([^<]+)</span>\s*<span class="pi-bar" aria-hidden="true"><span class="pi-sel" style="width:(\d+)%"></span></span>\s*'
                      r'<span class="pi-n"><bdi dir="ltr"><b>(\d+)</b></bdi>', pi)
    assert rows[:2] == [("Puducherry", "100", "7"), ("Tamil Nadu and Andaman and Nicobar Islands", "29", "2")]
    assert "/5</bdi>" not in pi and "/50</bdi>" not in pi
    with app.app_context():
        p = D._pipeline()
        assert [(s["state"], s["inst_sel"], s["share"]) for s in p["states"][:2]] == [("Puducherry", 7, 100), ("Tamil Nadu", 2, 29)]
        code = DRIVE.code_of("Puducherry")
        DRIVE._CACHE["data"] = None
    D._PIPE["data"] = None
    prog = client.get("/progress?lang=en").get_data(as_text=True)
    assert "The rows of Annexure-I with the most Participating Institutions selected" in prog and "7/5" not in prog
    state = client.get(f"/join/{code}?lang=en").get_data(as_text=True)
    assert "<h1>Puducherry: register your college or university for KTS 5.0</h1>" in state.replace("\n", "") or \
        "Puducherry: register your college or university for KTS 5.0" in state
    assert "colleges and universities of Puducherry may register, in any number. Register yours by" in state
    assert "5 colleges and universities" not in state and "to be selected" not in state
    board = client.get("/join?lang=en").get_data(as_text=True)
    assert "Each row of Annexure-I. Open a State/UT for its page, its link and its poster." in board
    assert re.findall(r'<span class="jb-n"><bdi dir="ltr">([\d,]+)</bdi></span>', board) == ["1,000"]   # the total only
    for path in ("/nodal-institutions?lang=en", "/partners?lang=en"):
        page = client.get(path).get_data(as_text=True)
        assert "Number of Participating HEIs to be selected" not in page and "The figures above indicate" not in page, path


def test_the_texts_in_23_languages():
    from kts.i18n import CATALOG
    assert sorted(CATALOG) == sorted(LANGS)
    for code in LANGS:
        c = CATALOG[code]
        for key in KEYS:
            assert c[key].strip() and "\n" not in c[key] and "{n}" not in c[key], (code, key)
            assert code == "en" or c[key] != CATALOG["en"][key], (code, key)
        assert "{state}" in c["join.title_plain"] and all(p in c["join.share_msg_nonum"] for p in ("{state}", "{date}", "{link}")), code
    app = _portal()
    for code in ("ta", "hi", "ur"):
        page = app.test_client().get(f"/dashboard?lang={code}").get_data(as_text=True)
        assert CATALOG[code]["dash.intro_plain"].replace("'", "&#39;") in page and CATALOG[code]["dash.grid_note_plain"] in page, code

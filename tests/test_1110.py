"""
The number of institutions registered on no public page (1.2.168; CICT, 10 November 2026: "hide institutions registered" on the
Progress page and, asked where else, "Everywhere public"), under the Console switch institutions.registered (off): the Progress
page and its JSON, the Participating Institutions, the dashboard by State/UT, the State/UT pages of the registration drive and
"Find your next step". The switch brings every one of them back.

    python -m pytest tests/test_1110.py -q
"""
import json
import re

from conftest import make_app

# seven registered (never the one only identified): four accepted, one pending, one on the reserve list, one declined
ROWS = [("Presidency College", "Tamil Nadu", "Chennai", "accepted"), ("Loyola College", "Tamil Nadu", "Chennai", "accepted"),
        ("PSG College", "Tamil Nadu", "Coimbatore", "accepted"), ("Maharaja's College", "Kerala", "Ernakulam", "accepted"),
        ("Pending College", "Kerala", "Kollam", "pending"), ("Reserve College", "Kerala", "Kannur", "reserve"),
        ("Declined College", "Goa", "North Goa", "declined"), ("Only Identified", "Bihar", "Patna", "identified")]
LIVE = {"reg.open": "0", "launch.on": "0", "hei.open": "1", "hei.start": "2026-10-22", "hei.end": "2099-11-15", "reg.end": "2099-11-20",
        "camp.to": "2099-11-19", "hei.public": "1", "join.on": "1", "dashboard.public": "1"}
WORDS = ("Institutions registered", "institutions registered", "have registered so far", "has registered yet", "have registered than")


def _app(**values):
    from kts import dashboard, drive
    from kts.db import execute, set_setting, utcnow
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for n, (name, state, district, status) in enumerate(ROWS, 1):
            execute("INSERT INTO institutions(ref, name, itype, state, district, inst_key, status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (f"KTS5-HEI-{n:05d}", name, "Government college", state, district, f"name:{name.lower()}|{state.lower()}", status, utcnow(), utcnow()))
        for key, value in {**LIVE, **values}.items():
            set_setting(key, value)
    # the figures are kept for some seconds: each portal of these tests starts afresh
    dashboard._PIPE["data"] = None
    drive.clear()
    return app


def _get(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def _main(page):
    return page[page.index('<main'):page.index("</main>")]


def test_no_public_page_gives_the_number():
    client = _app().test_client()
    for path in ("/", "/progress", "/institutions", "/dashboard", "/join", "/join/tn", "/join/kl", "/my-college"):
        page = _get(client, path + "?lang=en")
        for words in WORDS:
            assert words not in page, (path, words)
    # nor the description of a State/UT page for the search engines and the previews of a shared link
    assert 'name="description" content="Institutions registered' not in _get(client, "/join/tn?lang=en")


def test_the_progress_page():
    client = _app().test_client()
    page = _main(_get(client, "/progress?lang=en"))
    stages = re.findall(r'<li class="stage stage-(\w+)">', page)
    assert stages == ["participating", "testing", "selected"]
    # the first stage shown fills its bar and names no percentage; no line of the registrations day by day
    first = page[page.index('<li class="stage stage-participating">'):page.index('<li class="stage stage-testing">')]
    # four selected and one on the reserve list, counted together (1.2.178)
    assert 'data-k="st_participating">5</span>' in first and "st-pct" not in first and 'style="--w:100.0%"' in first
    assert "prog-momentum" not in page and "spark-inst" not in page and "Last 7 days" not in page
    data = json.loads(_get(client, "/progress.json"))
    flat = data["flat"]
    assert not {"registered", "pending", "reserve", "st_registered", "st_participating_pct", "inst_today", "inst_week"} & set(flat)
    assert flat["participating"] == 5 and flat["st_participating"] == 5
    assert "st_registered" not in data["widths"] and data["widths"]["st_participating"] == 100.0 and "inst" not in data["series"]
    # nothing in the JSON adds up to the seven registered
    assert 7 not in [v for v in flat.values() if isinstance(v, int)]


def test_the_participating_institutions():
    page = _get(_app().test_client(), "/institutions?lang=en")
    pi = page[page.index('<section class="pi"'):page.index('class="table-wrap"')]
    assert 'class="pi-two one"' in pi and "pi-trend" not in pi and "pi-regn" not in pi and 'class="pi-reg"' not in pi
    assert '<h3 id="pi-states-h">Each row of Annexure-I: the Participating Institutions selected</h3>' in pi   # no number (1.2.179)
    assert pi.count('class="pi-sw sel"') == 1 and 'class="pi-sw reg"' not in pi
    # the Participating Institutions selected stay: Tamil Nadu 3 (without its 50, 1.2.179)
    assert re.search(r'<b>3</b></bdi>', pi) and "/50</bdi>" not in pi


def test_the_dashboard_counts_the_participating_institutions():
    page = _main(_get(_app().test_client(), "/dashboard?lang=en"))
    assert "Where the programme stands in each State/UT: the Participating Institutions selected and the students who took" in page
    # three cards: the reserve list counts with the Participating Institutions, no card of its own (1.2.178)
    kpis = page[page.index('class="grid grid-3 dash-kpis"'):page.index('<section class="card dash-map"')]
    assert re.findall(r'<div class="lbl">([^<]+)</div>', kpis) == ["To be selected", "Participating Institutions selected",
                                                                     "Students who took an institution&#39;s online test"]
    assert '<h2 id="dash-grid-h">Participating Institutions selected</h2>' in page   # no number of a State/UT (1.2.179)
    tn = page[page.index('href="#d-TN"'):]
    tn = tn[:tn.index("</a>")]
    assert '<span class="dash-n" dir="ltr">3</span>' in tn and "Participating Institutions selected: <bdi>3</bdi>" in tn
    assert tn.count("Participating Institutions selected") == 1
    head = page[page.index("<thead>"):page.index("</thead>")]
    # with "Marks recorded" (1.2.175); the reserve list counted with the Participating Institutions (1.2.178); no column of the
    # number to be selected (1.2.179)
    assert head.count("<th ") == 4 and "Participating Institutions selected" in head
    row = page[page.index('<tr id="st-TN">'):]
    assert re.findall(r'<td class="num">([^<]*)</td>', row[:row.index("</tr>")]) == ["3", "0"]   # no column of the number (1.2.179)


def test_the_state_pages_of_the_drive():
    client = _app().test_client()
    board = _main(_get(client, "/join?lang=en"))
    assert "Each row of Annexure-I. Open a State/UT for its page, its link and its poster." in board   # no number (1.2.179)
    assert "jb-bar" not in board and " of " not in board[board.index('<ul class="jb">'):]
    names = re.findall(r'<span class="jb-name">([^<]+)</span>', board)
    assert names[:-1] == sorted(names[:-1]) and names[-1] == "All States/UTs" and len(names) == 32
    assert '<span class="jb-n"><bdi dir="ltr">1,000</bdi></span></li>' in board
    page = _get(client, "/join/tn?lang=en")
    main = _main(page)
    assert "join-count" not in main and "jm-sq" not in main and "jm-bar" not in main and "join-first" not in main and "join-over" not in main
    assert ">Register your institution</a>" in main and "Have this ready before you start" in main
    # the message to forward: neither the number to be selected (1.2.179) nor the number registered
    msg = main[main.index('id="join-msg">'):main.index("</blockquote>")]
    assert ("colleges and universities of Tamil Nadu and Andaman and Nicobar Islands may register, in any number. Register yours by"
            in msg and "registered" not in msg and "50" not in msg)
    assert "%7Breg%7D" not in main and "{reg}" not in main


def test_the_console_switch_brings_every_one_back():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS["institutions.registered"] == "0"
    label = {k: text for k, text, _kind in dict(SETTING_GROUPS)["Site"]}["institutions.registered"]
    assert "the Progress page" in label and "the dashboard by State/UT" in label
    client = _app(**{"institutions.registered": "1"}).test_client()
    progress = _main(_get(client, "/progress?lang=en"))
    assert re.findall(r'<li class="stage stage-(\w+)">', progress)[0] == "registered" and "spark-inst" in progress
    assert 'data-k="st_registered">7</span>' in progress
    flat = json.loads(_get(client, "/progress.json"))["flat"]
    assert flat["registered"] == 7 and flat["st_registered"] == 7
    assert "pi-trend" in _get(client, "/institutions?lang=en")
    dash = _main(_get(client, "/dashboard?lang=en"))
    assert '<h2 id="dash-grid-h">Institutions registered</h2>' in dash and "the institutions registered and selected" in dash
    assert "3 of 50" in _main(_get(client, "/join?lang=en"))
    tn = _main(_get(client, "/join/tn?lang=en"))
    # the message to forward has no number since 1.2.179, the figure of the page shows the institutions registered
    assert "Institutions registered: 3 of 50" in tn and "may register, in any number" in tn


def test_the_new_texts_in_every_language():
    from kts.i18n import CATALOG
    pairs = {"pi.states_title_sel": "pi.states_title", "join.board_note_plain": "join.board_note",
             "join.share_msg_plain": "join.share_msg", "dash.intro_sel": "dash.intro"}
    for code, cat in CATALOG.items():
        for new, base in pairs.items():
            assert cat[new] and cat[new] != cat[base], (code, new)
            if code != "en":
                assert cat[new] != CATALOG["en"][new], (code, new)
        assert sorted(re.findall(r"\{[a-z_]+\}", cat["join.share_msg_plain"])) == ["{date}", "{link}", "{n}", "{state}"], code

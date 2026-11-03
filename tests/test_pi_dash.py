"""
The Participating Institutions at a glance (version 1.2.149; the user: "Participating Institutions dashboard should be
informative and infographic filled one"): over the list of /institutions, the figures of the dashboard as an infographic - a
ring against the 1,000 of Annexure-I, the institutions registered, the rows and districts reached, the types of institution,
the registrations day by day, every row of Annexure-I as a bar leading to its institutions; no name but those of the list.

    python -m pytest tests -q
"""
import re

from conftest import make_app


def _portal():
    from kts.db import execute, set_setting, utcnow
    app = make_app(ADMIN_PASSWORD=None)
    rows = [("Presidency College", "Tamil Nadu", "Chennai", "Government college", "accepted"),
            ("Loyola College", "Tamil Nadu", "Chennai", "Autonomous college", "accepted"),
            ("PSG College", "Tamil Nadu", "Coimbatore", "Government-aided college", "accepted"),
            ("Kavaratti College", "Lakshadweep", "Kavaratti", "Government college", "accepted"),
            ("Maharaja's College", "Kerala", "Ernakulam", "Government college", "pending"),
            ("Declined College", "Goa", "North Goa", "Private / self-financing college", "declined"),
            ("Only Identified", "Bihar", "Patna", "Government college", "identified")]
    with app.app_context():
        for n, (name, state, district, itype, status) in enumerate(rows, 1):
            execute("INSERT INTO institutions(ref, name, itype, state, district, inst_key, status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (f"KTS5-HEI-{n:05d}", name, itype, state, district, f"name:{name.lower()}|{state.lower()}", status, utcnow(), utcnow()))
        set_setting("hei.public", "1")
        set_setting("join.on", "1")
    return app


def _pi(page):
    start = page.index('<section class="pi"')
    return page[start:page.index("</section>\n\n", start) if "</section>\n\n" in page[start:] else page.index("<p><b>", start)]


def test_the_figures():
    page = _portal().test_client().get("/institutions?lang=en").get_data(as_text=True)
    pi = page[page.index('<section class="pi"'):page.index('class="table-wrap"')]
    assert '<h2 id="pi-h">At a glance</h2>' in pi and "Live figures, as on" in pi
    # 4 Participating Institutions (Lakshadweep counts with Kerala) of the 1,000; 6 registered (not the one only identified)
    assert '<div class="num">4</div><div class="lbl">Participating institutions</div>' in pi and "<bdi>4 of 1,000</bdi>" in pi
    assert '<text x="60" y="67" text-anchor="middle" class="pct">0%</text>' in pi
    assert '<div class="num">6</div><div class="lbl">Institutions registered</div>' in pi
    # the rows reached: Tamil Nadu and Kerala-and-Lakshadweep of the 31; three districts (Chennai once, Coimbatore, Kavaratti)
    assert '<div class="num">2</div><div class="lbl">States and UTs</div>' in pi and "<bdi>2 of 31</bdi>" in pi
    assert '<div class="num">3</div><div class="lbl">Districts reached</div>' in pi
    # the types: Government college 2 (50%), then the others by count
    legend = re.findall(r"<li><i class=\"pi-sw c\d\" aria-hidden=\"true\"></i><span>([^<]+)</span><b>(\d+)</b><span class=\"muted small\">(\d+)%</span></li>", pi)
    assert legend[0] == ("Government college", "2", "50") and sorted(legend[1:]) == [("Autonomous college", "1", "25"), ("Government-aided college", "1", "25")]
    assert pi.count('class="pi-seg') == 3
    # the registrations day by day
    assert 'class="line" points="' in pi and "The last three weeks, day by day" in pi


def test_the_rows_of_annexure_i():
    page = _portal().test_client().get("/institutions?lang=en").get_data(as_text=True)
    pi = page[page.index('<section class="pi"'):page.index('class="table-wrap"')]
    assert pi.count('<li><a class="pi-row"') + pi.count('<li><span class="pi-row">') == 31
    rows = re.findall(r'<li><a class="pi-row" href="([^"]+)">\s*<span class="pi-name">([^<]+)</span>', pi)
    # the furthest ahead first: Tamil Nadu (3 of its number), then Kerala and Lakshadweep (1 of 21)
    assert rows[0][1].startswith("Tamil Nadu") and rows[0][0] == "#st-tamil-nadu"
    assert rows[1] == ("#st-lakshadweep", "Kerala and Lakshadweep")   # a paired row: its Union Territory's institutions
    # a row with none yet leads to its State/UT page
    assert any(href == "/join/up" for href, _name in rows)
    tn = pi[pi.index('<span class="pi-name">Tamil Nadu'):]
    tn = tn[:tn.index("</li>")]
    assert '<bdi dir="ltr"><b>3</b>/50</bdi>' in tn and 'class="pi-sel" style="width:6%"' in tn
    # no institution named in the infographic
    for name in ("Presidency", "Loyola", "Declined", "Only Identified"):
        assert name not in pi


def test_every_language_and_no_institution_yet():
    from kts.i18n import CATALOG
    client = _portal().test_client()
    for code, catalogue in CATALOG.items():
        page = client.get(f"/institutions?lang={code}").get_data(as_text=True)
        assert catalogue["pi.districts"] in page and catalogue["pi.states_title"].split()[0] in page, code
    empty = make_app(ADMIN_PASSWORD=None)
    with empty.app_context():
        from kts.db import set_setting
        set_setting("hei.public", "1")
    page = empty.test_client().get("/institutions?lang=en").get_data(as_text=True)
    assert '<div class="num">0</div><div class="lbl">Participating institutions</div>' in page and "No institution has been accepted yet." in page

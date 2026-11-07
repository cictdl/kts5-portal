"""
"Institutions registered" hidden on the home page too (1.2.165; CICT, 7 November 2026: "at home page hide 258 Institutions
registered"), with the Console switch institutions.registered of 1.2.164.

    python -m pytest tests/test_1107b.py -q
"""
import re

from conftest import make_app


def _glance(app, lang="en"):
    page = app.test_client().get(f"/?lang={lang}").get_data(as_text=True)
    start = page.index('<div class="card stat indigo">')
    head = page.rindex('<div class="grid ', 0, start)
    return page[head:page.index("</section>", start)]


def _app(**values):
    from kts.db import execute, set_setting, utcnow
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for n, (name, status) in enumerate((("Presidency College", "accepted"), ("Loyola College", "pending")), 1):
            execute("INSERT INTO institutions(ref, name, itype, state, district, inst_key, status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (f"KTS5-HEI-{n:05d}", name, "Government college", "Tamil Nadu", "Chennai", f"name:{name.lower()}|tamil nadu", status, utcnow(), utcnow()))
        for key, value in values.items():
            set_setting(key, value)
    return app


def test_the_card_leaves_the_home_page():
    glance = _glance(_app())
    assert glance.startswith('<div class="grid grid-3">')
    labels = re.findall(r'<div class="lbl">([^<]+)</div>', glance)
    assert labels == ["Participating institutions", "States and UTs", "Languages of the Thirukkural"]
    assert "Institutions registered" not in glance


def test_the_switch_brings_it_back():
    glance = _glance(_app(**{"institutions.registered": "1"}))
    assert glance.startswith('<div class="grid grid-4">')
    assert re.findall(r'<div class="num">([^<]+)</div><div class="lbl">Institutions registered</div>', glance) == ["2"]


def test_the_students_figures_keep_their_four_cards():
    glance = _glance(_app(**{"reg.public": "1"}))
    assert glance.startswith('<div class="grid grid-4">') and glance.count('<div class="card stat ') == 4

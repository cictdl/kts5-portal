"""
The students' registration hidden (version 1.2.147; the user: "hide any Student registration ... We try to select students from
Institutions directly", "dont delete student registration only hide"): setting reg.public, '0' by default; every way into the
students' registration and the application status, the dates of its window and every count of student delegates off the
public pages; /register, /status and the candidate portal working; '1' shows it all again.

    python -m pytest tests -q
"""
import json

from conftest import make_app


def _get(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def _app(shown="0"):
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for key, value in (("hei.open", "1"), ("hei.end", "2099-12-31"), ("dashboard.public", "1"), ("stats.public", "1"), ("reg.public", shown)):
            set_setting(key, value)
    return app


def test_the_setting():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS["reg.public"] == "0"
    assert [k for k, _label, kind in dict(SETTING_GROUPS)["Site"] if k == "reg.public" and kind == "bool"] == ["reg.public"]


def test_hidden_on_the_public_pages():
    client = _app().test_client()
    home = _get(client, "/?lang=en")
    menu = home.split('id="primary-menu"')[1].split('class="has-sub"')[1].split("</ul></li>")[0]
    assert menu.startswith('><a href="/institutions/register"') and "Student registration" not in menu
    footer = home[home.index("<footer"):]
    assert '<a href="/institutions/register">Register your institution</a>' in footer
    for page in (home, _get(client, "/about?lang=en"), _get(client, "/programme?lang=en"), _get(client, "/schedule?lang=en"),
                 _get(client, "/how-to-take-part?lang=en"), _get(client, "/contact?lang=en"), _get(client, "/stipend?lang=en"),
                 _get(client, "/sitemap?lang=en")):
        assert 'href="/register"' not in page and 'href="/status"' not in page
        assert "Registration window" not in page and "Student registration" not in page
    assert "Check application status" not in home and "Student delegates registered" not in home
    xml = _get(client, "/sitemap.xml")
    assert "8905/register</loc>" not in xml and "8905/status</loc>" not in xml and "8905/institutions/register</loc>" in xml
    # the dashboard counts the institutions; the progress page has no ring, stage or line of the student delegates
    dash = _get(client, "/dashboard?lang=en")
    assert "Student delegates registered" not in dash and "Verified by the Nodal Officers" not in dash
    assert '<h2 id="dash-grid-h">Participating Institutions selected</h2>' in dash   # since 1.2.168; no number since 1.2.179
    prog = _get(client, "/progress?lang=en")
    assert "Student delegates registered" not in prog and 'data-k="unregistered"' not in prog and 'data-line="app"' not in prog
    data = json.loads(_get(client, "/progress.json?lang=en"))
    assert not [k for k in data["flat"] if "delegates" in k or "verified" in k or k.startswith("app_")] and "app" not in data["series"]
    # nothing deleted: the pages themselves still answer
    for path in ("/register?lang=en", "/status?lang=en", "/candidate/login?lang=en"):
        assert client.get(path).status_code == 200, path


def test_shown_again():
    client = _app("1").test_client()
    home = _get(client, "/?lang=en")
    menu = home.split('id="primary-menu"')[1].split('class="has-sub"')[1].split("</ul></li>")[0]
    assert menu.startswith('><a href="/register"') and '<a href="/register">Nomination of the selected student</a>' in menu   # 1.2.182
    assert 'href="/status"' in home and "Registration window" in home
    assert "Student delegates registered" in _get(client, "/dashboard?lang=en") and "Student delegates registered" in _get(client, "/progress?lang=en")
    assert "8905/register</loc>" in _get(client, "/sitemap.xml")


def test_at_a_glance_counts_the_institutions():
    # 3 Nov 2026 (1.2.148), the user: "at the home page At a glance should be Participating Institutions not Student delegates
    # registered" - accepted, registered (not those only identified by a Nodal Officer), their States/UTs; the languages
    from kts.db import execute, utcnow
    app = _app()
    rows = [("Presidency College", "Tamil Nadu", "accepted"), ("Loyola College", "Tamil Nadu", "pending"),
            ("Maharaja's College", "Kerala", "accepted"), ("Declined College", "Goa", "declined"), ("Only Identified", "Bihar", "identified")]
    with app.app_context():
        for n, (name, state, status) in enumerate(rows, 1):
            execute("INSERT INTO institutions(ref, name, itype, state, district, inst_key, status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (f"KTS5-HEI-{n:05d}", name, "Government college", state, "District", f"name:{name.lower()}|{state.lower()}", status, utcnow(), utcnow()))
    home = _get(app.test_client(), "/?lang=en")
    glance = home[home.index("<h2>At a glance</h2>"):]
    glance = glance[:glance.index("</section>")]
    cards = [(n.strip(), l) for n, l in __import__("re").findall(r'<div class="num">([^<]+)</div><div class="lbl">([^<]+)</div>', glance)]
    # "Institutions registered" hidden since 1.2.165 (tests/test_1107b.py)
    # the States/UTs: those of the Participating Institutions, Tamil Nadu and Kerala (1.2.174; those of a registration before)
    assert cards == [("2", "Participating institutions"), ("2", "States and UTs"), ("22", "Languages of the Thirukkural")]
    assert "Student delegates registered" not in glance and "Colleges represented" not in glance
    # in every language, the portal's own words
    from kts.i18n import CATALOG
    for code in ("ta", "hi", "ur"):
        page = _get(app.test_client(), f"/?lang={code}")
        assert __import__("markupsafe").escape(CATALOG[code]["nav.institutions"]) in page, code
    # the students' registration shown: the students' figures as before
    with app.app_context():
        from kts.db import set_setting
        set_setting("reg.public", "1")
    home = _get(app.test_client(), "/?lang=en")
    assert "Student delegates registered" in home and "Institutions registered</div>" not in home


def test_the_tiles_of_the_assessment_page():
    # 3 Nov 2026 (1.2.150), the user: "remove 📅 Institution-level assessments 19 Nov 2026" - and the students' registration's
    # tile hidden with it (reg.public)
    page = _get(_app().test_client(), "/examination?lang=en")
    tiles = page[page.index('<div class="grid grid-2"'):]
    tiles = tiles[:tiles.index("</div>\n        </div>") if "</div>\n        </div>" in tiles else 1500]
    assert "📅" not in page and "Institution-level assessments</div>" not in tiles
    assert "📝" not in page and "Last date for nomination" not in tiles
    assert "💻" in tiles and "⏳" in tiles
    shown = _get(_app("1").test_client(), "/examination?lang=en")
    assert "📝 Last date for nomination" in shown and "📅" not in shown

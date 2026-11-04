"""
The menu of 4 November 2026 (1.2.156), as the user asked: "Online orientation programme name should be changed as Educational Videos,
Hide - Institution-level assessment menu items (ratain what is good for the portal) Next, Make a new Menu named, Academic Orientation.
In this we will provide content later. Next change the menu name Thirukkural name as Other Resources."

    python -m pytest tests/test_menu_1104.py -q
"""
import re

from markupsafe import escape

from conftest import make_app


def _app(**values):
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for key, value in values.items():
            set_setting(key, value)
    return app


def _get(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def _menu(page):
    return page[page.index('<ul id="primary-menu">'):page.index("</nav>")]


def _top(menu):
    """The labels of the items of the menu itself, in their order."""
    return re.findall(r'^      <li(?: class="has-sub")?><a href="[^"]*"[^>]*>([^<]+)</a>', menu, re.M)


def _sub(menu, label):
    """The links of the submenu of an item: [(href, label)]."""
    part = menu[menu.index(f">{label}</a>"):]
    part = part[:part.index("</ul></li>")]
    return re.findall(r'<li><a href="([^"]+)">([^<]+)</a></li>', part)


def _urls(app, *endpoints):
    from flask import url_for
    with app.test_request_context():
        return [url_for(e) for e in endpoints]


def test_the_menu_in_its_order():
    page = _get(_app().test_client(), "/?lang=en")
    assert _top(_menu(page)) == ["Home", "About KTS", "Programme", "Register", "Academic Orientation", "Educational Videos", "Resources",
                                 "Other Resources", "Notices", "Schedule", "Partners", "Gallery", "Contact"]


def test_the_assessment_leaves_the_menu_and_its_page_stays():
    from kts.admin import SETTING_GROUPS
    from kts.db import set_setting
    app = _app()
    client = app.test_client()
    home = _get(client, "/?lang=en")
    footer = home[home.index('<footer class="site">'):]
    assert "/examination" not in _menu(home) and "/examination" not in footer
    # the page itself, and the links to it from the pages that need it
    assert "<h1>Institution-level assessment</h1>" in _get(client, "/examination?lang=en")
    assert 'href="/examination"' in _get(client, "/how-to-take-part?lang=en")
    # the Console's switch brings both back, the menu's item before the Academic Orientation
    assert [k for _title, items in SETTING_GROUPS for k, *_ in items].count("menu.assessment") == 1
    with app.app_context():
        set_setting("menu.assessment", "1")
    home = _get(client, "/?lang=en")
    assert '<a href="/examination" class="">Institution-level assessment</a>' in _menu(home)
    assert '<li><a href="/examination">Institution-level assessment</a></li>' in home[home.index('<footer class="site">'):]
    assert _top(_menu(home))[3:6] == ["Register", "Institution-level assessment", "Academic Orientation"]
    assert 'class="active">Institution-level assessment</a>' in _menu(_get(client, "/examination?lang=en"))


def test_what_was_good_on_the_assessment_page_stays_in_the_menu():
    from kts.db import set_setting
    app = _app()
    client = app.test_client()
    menu = _menu(_get(client, "/?lang=en"))
    # the classroom quiz and the practice test under Other Resources, with the Thirukkural pages
    kural, companion, daily, quiz, practice, syllabus, merit = _urls(app, "public.kural_browser", "public.companion", "public.daily_kural",
                                                                     "quiz.join", "practice.home", "public.syllabus", "public.merit")
    assert _sub(menu, "Other Resources") == [(kural, "Thirukkural in 22 languages"), (companion, "Thirukkural study companion"),
                                             (daily, "Daily Kural"), (quiz, "Classroom quiz"), (practice, "Practice test")]
    # the study material stays under Resources
    assert (syllabus, "Study material for the institution-level assessment") in _sub(menu, "Resources")
    # the list of the selected students under Register, once published
    assert "Selected students" not in menu
    with app.app_context():
        set_setting("merit.published", "1")
        set_setting("quiz.on", "0")
        set_setting("practice.on", "0")
    menu = _menu(_get(client, "/?lang=en"))
    assert (merit, "Selected students") in _sub(menu, "Register")
    assert "Classroom quiz" not in menu and "Practice test" not in menu
    assert 'class="active" aria-haspopup="true">Register</a>' in _menu(_get(client, f"{merit}?lang=en"))


def test_the_practice_test_marks_other_resources():
    app = _app()
    (practice,) = _urls(app, "practice.home")
    assert 'class="active" aria-haspopup="true">Other Resources</a>' in _menu(_get(app.test_client(), f"{practice}?lang=en"))


def test_the_academic_orientation():
    app = _app()
    client = app.test_client()
    page = _get(client, "/academic-orientation?lang=en")
    assert "<h1>Academic Orientation</h1>" in page and 'class="active">Academic Orientation</a>' in _menu(page)
    assert "Academic orientation by CICT, with access to the study material and educational videos · <b><bdi>By 14 " in page
    assert "The content of the academic orientation will be published here." in page
    assert 'href="/orientation">▶ Educational Videos</a>' in page and 'href="/syllabus">📘 Study material: the study book</a>' in page
    # in the sitemap, for the search engines and on its page
    assert "/academic-orientation</loc>" in _get(client, "/sitemap.xml")
    from kts.i18n import CATALOG
    for code, catalogue in CATALOG.items():
        page = _get(client, f"/academic-orientation?lang={code}")
        assert f"<h1>{escape(catalogue['nav.acad'])}</h1>" in page, code
        assert escape(catalogue["acad.soon"]) in page, code
        top = _top(_menu(page))
        assert top[4:8] == [escape(catalogue["nav.acad"]), escape(catalogue["nav.orientation"]), escape(catalogue["nav.resources"]),
                            escape(catalogue["nav.other_res"])], code


def test_the_educational_videos():
    app = _app()
    client = app.test_client()
    page = _get(client, "/orientation?lang=en")
    assert "<h1>Educational Videos</h1>" in page and "Online orientation programme" not in page
    assert 'class="active">Educational Videos</a>' in _menu(page)
    (resources,) = _urls(app, "public.resources")
    assert "<h3>Educational Videos</h3>" in _get(client, f"{resources}?lang=en")


def test_the_texts_in_every_language():
    from kts.i18n import CATALOG
    assert len(CATALOG) == 23
    for code, catalogue in CATALOG.items():
        assert catalogue["nav.orientation"] == catalogue["res.orient_title"], code
        assert catalogue["nav.other_res"] != catalogue["nav.resources"] and catalogue["nav.acad"] and catalogue["acad.soon"], code
        if code != "en":
            for key in ("nav.acad", "acad.soon", "nav.other_res", "nav.orientation"):
                assert catalogue[key] != CATALOG["en"][key], (code, key)

"""
The new order of the main menu (1.2.161), as CICT gave it on 5 November 2026 ("the new order of the menus. do it very carefully"):

    Home · About KTS · Programme · Register · Students' Engagement Programme (Multilingual Study Materials, Educational Videos,
    Academic Orientation) · Additional Resources · Notices · Schedule · Partners · Gallery · Contact

"Additional Resources" is the item called "Other Resources" since 1.2.156; it also takes the digital repository (and CICT's seminars
and workshops, when shown), which had an item of their own, "Resources", whose study book moved to the Students' Engagement
Programme. Nothing that was in the menu leaves it.

    python -m pytest tests/test_menu_1105.py -q
"""
import re

from markupsafe import escape

from conftest import make_app

SEP = "Students&#39; Engagement Programme"
ADD = "Additional Resources"


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
    return re.findall(r'^      <li(?: class="has-sub")?><a href="[^"]*"[^>]*>([^<]+)</a>', menu, re.M)


def _sub(menu, label):
    part = menu[menu.index(f">{label}</a>"):]
    part = part[:part.index("</ul></li>")]
    return re.findall(r'<li><a href="([^"]+)">([^<]+)</a></li>', part)


def _urls(app, *endpoints):
    from flask import url_for
    with app.test_request_context():
        return [url_for(e) for e in endpoints]


def test_the_menu_in_the_new_order():
    page = _get(_app().test_client(), "/?lang=en")
    assert _top(_menu(page)) == ["Home", "About KTS", "Programme", "Register", SEP, ADD, "Notices", "Schedule", "Partners", "Gallery",
                                 "Contact"]


def test_the_students_engagement_programme():
    app = _app()
    client = app.test_client()
    syllabus, videos, acad = _urls(app, "public.syllabus", "public.orientation", "public.academic_orientation")
    menu = _menu(_get(client, "/?lang=en"))
    assert _sub(menu, SEP) == [(syllabus, "Multilingual Study Materials"), (videos, "Educational Videos"), (acad, "Academic Orientation")]
    # a drop-down item, which opens the first of its pages
    assert f'<li class="has-sub"><a href="{syllabus}" class="" aria-haspopup="true">{SEP}</a>' in menu
    # each of the three pages marks it as the one open
    for path in (syllabus, videos, acad):
        assert f'class="active" aria-haspopup="true">{SEP}</a>' in _menu(_get(client, f"{path}?lang=en")), path
    # no longer items of the menu itself
    assert not re.search(r'^      <li><a href="(/orientation|/academic-orientation)"', menu, re.M)


def test_the_additional_resources():
    app = _app()
    client = app.test_client()
    kural, companion, daily, quiz, practice, repository = _urls(app, "public.kural_browser", "public.companion", "public.daily_kural",
                                                                "quiz.join", "practice.home", "public.resources")
    menu = _menu(_get(client, "/?lang=en"))
    assert _sub(menu, ADD) == [(kural, "Thirukkural in 22 languages"), (companion, "Thirukkural study companion"), (daily, "Daily Kural"),
                               (quiz, "Classroom quiz"), (practice, "Practice test"), (repository, "Digital repository")]
    assert "Other Resources" not in menu and ">Resources</a>" not in menu
    for path in (kural, daily, practice, repository):
        assert f'class="active" aria-haspopup="true">{ADD}</a>' in _menu(_get(client, f"{path}?lang=en")), path
    # CICT's seminars and workshops, when shown (Console: events.public)
    assert "/seminars-workshops" not in menu
    app2 = _app(**{"events.public": "1"})
    (events,) = _urls(app2, "public.cict_events_page")
    menu = _menu(_get(app2.test_client(), "/?lang=en"))
    assert _sub(menu, ADD)[-2:] == [(repository, "Digital repository"), (events, "Seminars and workshops of CICT")]
    assert f'class="active" aria-haspopup="true">{ADD}</a>' in _menu(_get(app2.test_client(), f"{events}?lang=en"))


def test_nothing_leaves_the_menu():
    app = _app(**{"events.public": "1"})
    menu = _menu(_get(app.test_client(), "/?lang=en"))
    links = set(re.findall(r'<a href="([^"]+)"', menu))
    for endpoint in ("public.home", "public.about", "public.programme", "public.guide", "public.hei_register", "public.institutions",
                     "public.nodal_institutions", "public.nodal_guidelines", "public.submit_guide", "campus.login", "public.syllabus",
                     "public.orientation", "public.academic_orientation", "public.kural_browser", "public.companion", "public.daily_kural",
                     "quiz.join", "practice.home", "public.resources", "public.cict_events_page", "public.notices", "public.news",
                     "public.schedule", "public.partners", "public.gallery", "public.contact"):
        (url,) = _urls(app, endpoint)
        assert url in links, endpoint


def test_the_items_have_room_for_one_line_on_a_computer():
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    assert "@media (min-width: 900px) { .nav li a { padding-inline: 8px; } }" in css
    # the items of a submenu keep their own room (a rule of more weight)
    assert ".nav li .sub a { padding: 9px 16px;" in css


def test_the_menu_in_every_language():
    from kts.i18n import CATALOG
    client = _app().test_client()
    assert len(CATALOG) == 23
    for code, catalogue in CATALOG.items():
        menu = _menu(_get(client, f"/?lang={code}"))
        top = _top(menu)
        assert top[3:7] == [escape(catalogue["nav.register"]), escape(catalogue["nav.sep"]), escape(catalogue["nav.other_res"]),
                            escape(catalogue["nav.notices"])], code
        assert [label for _href, label in _sub(menu, escape(catalogue["nav.sep"]))] == \
            [escape(catalogue[k]) for k in ("nav.study_ml", "nav.orientation", "nav.acad")], code
        if code != "en":
            for key in ("nav.sep", "nav.study_ml", "nav.other_res"):
                assert catalogue[key] != CATALOG["en"][key], (code, key)
        assert catalogue["nav.other_res"] != catalogue["nav.resources"], code

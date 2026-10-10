"""
The website policies, the help page and the sitemap that the Guidelines for Indian Government Websites
(GIGW 3.0) ask for, and the line "Last updated" (version 1.2.34).

    python -m pytest tests -q
"""
import re

import pytest

from conftest import make_app

PAGES = {"terms": "/terms-of-use", "privacy": "/privacy-policy", "copyright": "/copyright-policy",
         "hyperlinking": "/hyperlinking-policy", "accessibility": "/accessibility-statement", "help": "/help",
         "sitemap": "/sitemap"}


@pytest.fixture(scope="module")
def app():
    return make_app(ADMIN_PASSWORD=None)


def _text(key, lang="en"):
    from markupsafe import escape
    from kts.i18n import CATALOG
    return str(escape(CATALOG[lang][key]))


@pytest.mark.parametrize("page", list(PAGES))
def test_every_page_answers_in_english_hindi_and_tamil(app, page):
    for lang in ("en", "hi", "ta"):
        r = app.test_client().get(f"{PAGES[page]}?lang={lang}")
        assert r.status_code == 200, (page, lang)
        html = r.get_data(as_text=True)
        assert f"<h1>{_text('pol.' + page, lang)}</h1>" in html
        # the text is in the language of the page: no note that it is not
        assert _text("pol.body_note", lang) not in html


def test_other_languages_show_the_english_text_with_a_note(app):
    html = app.test_client().get("/privacy-policy?lang=bn").get_data(as_text=True)
    assert f"<h1>{_text('pol.privacy', 'bn')}</h1>" in html and _text("pol.body_note", "bn") in html
    assert '<div class="card prose policy-text" lang="en" dir="ltr">' in html and "two cookies" in html


def test_the_privacy_policy_says_what_the_portal_does(app):
    html = app.test_client().get("/privacy-policy?lang=en").get_data(as_text=True)
    for fact in ("<b>session</b>", "<b>lang</b>", "Bank account numbers and Aadhaar numbers are stored encrypted",
                 "deleted with their answers after 30 days", "Who visited is not stored", "not sold"):
        assert fact in html, fact
    # the address of the helpdesk is the setting of the day
    from kts.db import get_setting
    with app.app_context():
        email = get_setting("contact.email")
    assert f'href="mailto:{email}"' in html


def test_the_help_page_gives_the_dates_of_the_settings(app):
    from kts.db import all_settings
    from kts.utils import fmt_date
    with app.app_context():
        settings = all_settings()
    html = app.test_client().get("/help?lang=en").get_data(as_text=True)
    # the dates of the D.O. letter of 9 October 2026 (1.2.53): the institutions register, assess, and their students register
    for key in ("hei.end", "camp.from", "camp.to", "reg.end"):
        assert f"<bdi>{fmt_date(settings[key], False)}</bdi>" in html, key
    # no test of CICT at a fixed hour any more
    assert f"<bdi>{settings['exam.start_time']}</bdi>" not in html and "IST</bdi>" not in html
    assert 'href="/static/KTS5-nomination-form.pdf"' in html


def test_the_sitemap_lists_the_public_pages(app):
    html = app.test_client().get("/sitemap?lang=en").get_data(as_text=True)
    for href in ("/", "/register", "/examination", "/resources", "/quiz/", "/privacy-policy", "/help"):
        assert f'<a href="{href}">' in html, href
    assert "/console" not in html.split("<main")[1].split("</main>")[0]
    xml = app.test_client().get("/sitemap.xml")
    assert xml.status_code == 200 and xml.mimetype == "application/xml"
    body = xml.get_data(as_text=True)
    base = app.config["BASE_URL"].rstrip("/")
    assert body.startswith('<?xml version="1.0" encoding="UTF-8"?>') and f"<loc>{base}/register</loc>" in body
    assert body.count("<url>") == len(set(re.findall(r"<loc>(.*?)</loc>", body))) >= 25


def test_every_page_has_the_links_and_the_day_of_the_last_change(app):
    from kts.version import RELEASED
    html = app.test_client().get("/?lang=en").get_data(as_text=True)
    for page, path in PAGES.items():
        assert f'<a href="{path}">{_text("pol." + page)}</a>' in html, page
    m = re.search(r'<span class="lbl updated">Last updated: <bdi>(\d\d \w{3} \d{4})</bdi></span>', html)
    assert m, "no line Last updated"
    from datetime import datetime
    assert datetime.strptime(m.group(1), "%d %b %Y").strftime("%Y-%m-%d") >= RELEASED

"""
How to take part (version 1.2.53): the steps of the students, the participating institutions and the
Nodal Officers, with the dates of the settings; the guide of the institutions to print; the Help page
as the D.O. letter of 9 October 2026 has it (no test of CICT, no admit card).

    python -m pytest tests -q
"""
import json
import re

import pytest
from markupsafe import escape

from conftest import ROOT, make_app

CODES = sorted(p.stem for p in (ROOT / "data" / "i18n").glob("*.json"))
PLACEHOLDERS = ("{hei_end}", "{camp_from}", "{camp_to}", "{reg_end}", "{verify_end}", "{questions}", "{minutes}", "{email}", "{phone}")


@pytest.fixture(scope="module")
def site():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("reg.end", "2026-10-22")
    return app.test_client()


def _page(client, path, lang="en"):
    r = client.get(f"{path}{'&' if '?' in path else '?'}lang={lang}")
    assert r.status_code == 200, (path, lang)
    return r.get_data(as_text=True)


def test_the_three_parts_with_their_dates_and_links(site):
    page = _page(site, "/how-to-take-part")
    for heading in ("How to take part", "For students", "For participating institutions", "For Nodal Officers of the States/UTs"):
        assert heading in page
    # the dates of the settings in the steps
    assert "ask the Head of your institution to register it by 21 Oct 2026." in page and "<b>Register by 22 Oct 2026</b>" in page
    assert "Between 15 Oct 2026 and 21 Oct 2026, your institution assesses" in page
    assert "50 questions in 30 minutes" in page
    assert "<b>Verify the registered students by 24 Oct 2026</b>" in page
    assert not any(p in page for p in PLACEHOLDERS)
    for href in ('href="/institutions"', 'href="/institutions/register"', 'href="/institution/login"', 'href="/register"',
                 'href="/status"', 'href="/nodal-institutions"', 'href="/console/login"', 'href="/how-to-take-part/institutions"',
                 "KTS5-nomination-form.pdf"):
        assert href in page, href
    assert 'href="#students"' in page and 'id="institutions"' in page and 'id="nodal"' in page


@pytest.mark.parametrize("code", CODES)
def test_every_language_keeps_the_dates(site, code):
    catalog = json.loads((ROOT / "data" / "i18n" / f"{code}.json").read_text(encoding="utf-8"))
    en = json.loads((ROOT / "data" / "i18n" / "en.json").read_text(encoding="utf-8"))
    for key, source in en.items():
        if key.startswith("guide."):
            assert sorted(re.findall(r"\{\w+\}", catalog[key])) == sorted(re.findall(r"\{\w+\}", source)), (code, key)
    for path in ("/how-to-take-part", "/how-to-take-part/institutions"):
        page = _page(site, path, code)
        assert not any(p in page for p in PLACEHOLDERS), (code, path)
        assert str(escape(catalog["guide.i1_t"].split("{")[0].strip()[:12])) in page, (code, path)


def test_the_guide_of_the_institutions_to_print(site):
    page = _page(site, "/how-to-take-part/institutions")
    assert "<h1>Guide for participating institutions</h1>" in page and "data-print" in page
    assert "Sign in to the institution&#39;s page" in page and "Select one student on merit" in page
    assert "For students" not in page and "Check that your institution takes part" not in page
    assert "Verify the registered students" not in page
    assert "/how-to-take-part</bdi>" in page


def test_the_help_page_follows_the_letter_of_the_ministry(site):
    for lang, words in (("en", ("How to take part", "For participating institutions", "personal registration link")),
                        ("hi", ("भाग कैसे लें", "सहभागी संस्थानों के लिए", "व्यक्तिगत पंजीकरण लिंक")),
                        ("ta", ("பங்கேற்கும் முறை", "பங்கேற்கும் கல்வி நிறுவனங்களுக்கு", "தனிப்பட்ட பதிவு இணைப்பு"))):
        page = _page(site, "/help", lang)
        for w in words:
            assert w in page, (lang, w)
        for gone in ("11:30", "12:00 IST", "admit card", "प्रवेश-पत्र", "அனுமதிச் சீட்டு"):
            assert gone not in page, (lang, gone)
        assert 'href="/how-to-take-part"' in page and 'href="/institution/login"' in page and 'href="/how-to-take-part/institutions"' in page


def test_the_guide_is_found_from_the_menu_the_home_page_and_the_sitemap(site):
    home = _page(site, "/")
    assert home.count('href="/how-to-take-part"') >= 2   # the menu and the button of the hero
    assert 'href="/how-to-take-part"' in _page(site, "/examination")
    assert 'href="/how-to-take-part#students"' in _page(site, "/register")
    assert 'href="/how-to-take-part"' in _page(site, "/sitemap")
    assert "/how-to-take-part" in site.get("/sitemap.xml").get_data(as_text=True)


def test_the_closed_registration_page_leads_to_the_guide():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("reg.start", "2099-01-01")
    page = app.test_client().get("/register?lang=en").get_data(as_text=True)
    assert "Registration opens on" in page and 'class="btn" href="/how-to-take-part"' in page

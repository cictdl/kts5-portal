"""
The theme line under the name of the programme: Tamil, its transliteration with the Hindi one, Hindi,
and the English meaning.

    python -m pytest tests -q
"""
import re

import pytest

from conftest import make_app

PARTS = ["திருக்குறள் பயில்வோம்", "Thirukkural Payilvom – Thirukkural Abhyas Karen", "तिरुक्कुरल अभ्यास करें", "Let's Learn Thirukkural"]


def _line(page, opener):
    start = page.index(opener)
    return re.sub(r"<[^>]+>", "", page[start:page.index("</div>", start)]).replace("&#39;", "'").replace("&#x27;", "'")


@pytest.mark.parametrize("lang", ["en", "ta", "hi", "ur", "sat"])
def test_the_masthead_carries_the_four_parts_in_order(lang):
    page = make_app(ADMIN_PASSWORD=None).test_client().get(f"/register?lang={lang}").get_data(as_text=True)
    line = _line(page, '<div class="theme" dir="ltr">')
    assert [p for p in PARTS if p in line] == PARTS
    assert " · ".join(PARTS) == " ".join(line.split())


def test_the_home_page_and_the_about_page_say_the_same():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    home = client.get("/?lang=en").get_data(as_text=True)
    hero = _line(home, '<div class="theme-lines" dir="ltr">')
    assert all(p in hero for p in PARTS)
    about = client.get("/about?lang=en").get_data(as_text=True).replace("&#39;", "'")
    assert all(p in about for p in PARTS)

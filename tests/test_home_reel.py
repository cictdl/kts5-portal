"""
The reel of the official Kashi Tamil Sangamam account on the home page (data/home_reel.json, version 1.2.79): a card
that opens it on Instagram, with the opening line and the hashtags of its post, in every language; no player, script or
frame of Instagram on the portal.

    python -m pytest tests -q
"""
import json
from pathlib import Path

from markupsafe import escape

from conftest import make_app

ROOT = Path(__file__).resolve().parents[1]
REEL = json.loads((ROOT / "data" / "home_reel.json").read_text(encoding="utf-8"))


def test_the_reel():
    assert REEL["url"] == "https://www.instagram.com/reel/Deg6QD_A4F3/" and "?" not in REEL["url"]
    assert REEL["account"] == "ktsangamam" and REEL["date"] == "2026-10-15"
    assert REEL["tags"] == ["KashiTamilSangamam5", "KTS5", "VanakkamKashi", "UnityInDiversity", "EkBharatShreshthaBharat"]


def test_the_home_page_links_to_the_reel_in_every_language():
    from kts.i18n import CATALOG
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    for code, catalogue in CATALOG.items():
        page = client.get(f"/?lang={code}").get_data(as_text=True)
        card = page[page.index('<a class="reel-card"'):]
        card = card[:card.index("</a>\n")]
        assert '<a class="reel-card" href="https://www.instagram.com/reel/Deg6QD_A4F3/" target="_blank" rel="noopener">' in card
        assert f'<span class="reel-title" id="home-reel-title">{escape(catalogue["home.reel_title"])}</span>' in card, code
        assert str(escape(catalogue["home.reel_watch"])) in card, code
        assert '<span class="reel-from"><span lang="en" dir="ltr">Instagram · @ktsangamam</span> · <bdi>' in card
        assert "#KashiTamilSangamam5 #KTS5 #VanakkamKashi #UnityInDiversity #EkBharatShreshthaBharat" in card
        assert str(escape("“India’s diversity is best experienced through its people, languages and traditions.”")) in card
        # a link only: nothing of Instagram is loaded by the page
        assert "<iframe" not in page and "instagram.com/embed" not in page and "cdninstagram" not in page
    # the reel comes after the hero and before the section for the institutions
    page = client.get("/?lang=en").get_data(as_text=True)
    assert "Instagram · @ktsangamam</span> · <bdi>15 Oct 2026</bdi>" in page
    assert page.index('<section class="hero">') < page.index('class="section home-reel"') < page.index("For Higher Educational Institutions")

"""
The reel of the official Kashi Tamil Sangamam accounts on the home page (data/home_reel.json): a card that opens it on
Instagram (version 1.2.79) or on Facebook (1.2.80), with the opening line and the hashtags of its post, in every
language; no player, script or frame of Instagram or Facebook on the portal.

    python -m pytest tests -q
"""
import json
from pathlib import Path

from markupsafe import escape

from conftest import make_app

ROOT = Path(__file__).resolve().parents[1]
REEL = json.loads((ROOT / "data" / "home_reel.json").read_text(encoding="utf-8"))
INSTAGRAM = "https://www.instagram.com/reel/Deg6QD_A4F3/"
FACEBOOK = "https://www.facebook.com/reel/1797045828084084"


def test_the_reel():
    assert REEL["url"] == INSTAGRAM and REEL["facebook"] == FACEBOOK
    assert "?" not in REEL["url"] and "?" not in REEL["facebook"]
    assert REEL["account"] == "ktsangamam" and REEL["date"] == "2026-10-15"
    assert REEL["tags"] == ["KashiTamilSangamam5", "KTS5", "VanakkamKashi", "UnityInDiversity", "EkBharatShreshthaBharat"]


def test_the_facebook_button_is_the_instagram_one_with_the_other_name():
    from kts.i18n import CATALOG
    for code, catalogue in CATALOG.items():
        assert catalogue["home.reel_watch_fb"] == catalogue["home.reel_watch"].replace("Instagram", "Facebook"), code


def test_the_home_page_links_to_the_reel_in_every_language():
    from kts.i18n import CATALOG
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    for code, catalogue in CATALOG.items():
        page = client.get(f"/?lang={code}").get_data(as_text=True)
        card = page[page.index('<div class="reel-card">'):]
        card = card[:card.index("</section>")]
        assert f'<span class="reel-title" id="home-reel-title">{escape(catalogue["home.reel_title"])}</span>' in card, code
        assert (f'<a class="btn saffron sm" href="{INSTAGRAM}" target="_blank" rel="noopener">'
                f'{escape(catalogue["home.reel_watch"])} <span aria-hidden="true">↗</span></a>') in card, code
        assert (f'<a class="btn sm reel-fb" href="{FACEBOOK}" target="_blank" rel="noopener">'
                f'{escape(catalogue["home.reel_watch_fb"])} <span aria-hidden="true">↗</span></a>') in card, code
        assert '<span class="reel-from"><span lang="en" dir="ltr">Instagram · @ktsangamam</span> · <bdi>' in card
        assert "#KashiTamilSangamam5 #KTS5 #VanakkamKashi #UnityInDiversity #EkBharatShreshthaBharat" in card
        assert str(escape("“India’s diversity is best experienced through its people, languages and traditions.”")) in card
        # links only: nothing of Instagram or Facebook is loaded by the page
        for gone in ("<iframe", "instagram.com/embed", "cdninstagram", "connect.facebook.net", "facebook.com/plugins", "fbcdn"):
            assert gone not in page, (code, gone)
    # the reel comes after the hero and before the section for the institutions
    page = client.get("/?lang=en").get_data(as_text=True)
    assert "Instagram · @ktsangamam</span> · <bdi>15 Oct 2026</bdi>" in page
    assert page.index('<section class="hero">') < page.index('class="section home-reel"') < page.index("For Higher Educational Institutions")

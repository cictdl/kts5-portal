"""
The Thirukkural in Uzbek on the home page (data/home_uzbek.json, version 1.2.102): the Hon'ble Prime Minister's call at
Tashkent State University of Oriental Studies (ANI on X, 31 August 2026) and CICT's short on its first meeting with the
University on the translation (YouTube, 23 September 2026), a card under the reel, in every language; links only,
nothing of X or YouTube is loaded by the page.

    python -m pytest tests -q
"""
import json
from pathlib import Path

from markupsafe import escape

from conftest import make_app

ROOT = Path(__file__).resolve().parents[1]
UZ = json.loads((ROOT / "data" / "home_uzbek.json").read_text(encoding="utf-8"))
X = "https://x.com/ANI/status/2094289671467700615"
YOUTUBE = "https://www.youtube.com/shorts/G4bi2H_fmXk"


def test_the_two_videos():
    # the addresses without the tracking part of the link the user sent
    assert UZ["x"] == {"account": "ANI", "date": "2026-08-31", "url": X}
    assert UZ["youtube"] == {"account": "cicttamil", "date": "2026-09-23", "url": YOUTUBE}
    assert UZ["meeting"] == "2026-09-23"
    assert UZ["quote"].startswith("The Thirukkural, written in Tamil millennia ago, remains a profound source of inspiration")


def test_the_strings_in_every_language():
    from kts.i18n import CATALOG
    for code, catalogue in CATALOG.items():
        assert catalogue["home.reel_watch_x"] == catalogue["home.reel_watch"].replace("Instagram", "X"), code
        assert catalogue["home.reel_watch_yt"] == catalogue["home.reel_watch"].replace("Instagram", "YouTube"), code
        assert catalogue["home.uz_text"].count("{date}") == 1 and "CICT" in catalogue["home.uz_text"], code
        if code != "en":
            assert catalogue["home.uz_title"] != CATALOG["en"]["home.uz_title"], code
            assert catalogue["home.uz_text"] != CATALOG["en"]["home.uz_text"], code


def test_the_card_on_the_home_page_in_every_language():
    from kts.i18n import CATALOG
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for code, catalogue in CATALOG.items():
        page = client.get(f"/?lang={code}").get_data(as_text=True)
        start = page.index('<section class="section home-reel home-uzbek" aria-labelledby="home-uz-title">')
        card = page[start:page.index("</section>", start)]
        assert f'<span class="reel-title" id="home-uz-title">{escape(catalogue["home.uz_title"])}</span>' in card, code
        before, after = catalogue["home.uz_text"].split("{date}")
        assert f'<span class="reel-text">{escape(before)}' in card and f"{escape(after)}</span>" in card and "{date}" not in card, code
        assert (f'<a class="btn saffron sm" href="{X}" target="_blank" rel="noopener">'
                f'{escape(catalogue["home.reel_watch_x"])} <span aria-hidden="true">↗</span></a>') in card, code
        assert (f'<a class="btn sm reel-yt" href="{YOUTUBE}" target="_blank" rel="noopener">'
                f'{escape(catalogue["home.reel_watch_yt"])} <span aria-hidden="true">↗</span></a>') in card, code
        assert '<span class="reel-from"><span lang="en" dir="ltr">X · @ANI</span> · <bdi>' in card
        assert '<span lang="en" dir="ltr">YouTube · @cicttamil</span> · <bdi>' in card
        assert str(escape("“The Thirukkural, written in Tamil millennia ago,")) in card
        # links only: nothing of X or YouTube is loaded by the page
        for gone in ("<iframe", "platform.twitter.com", "twimg.com", "youtube.com/embed", "youtube-nocookie"):
            assert gone not in page, (code, gone)
    page = client.get("/?lang=en").get_data(as_text=True)
    assert "X · @ANI</span> · <bdi>31 Aug 2026</bdi> · <span lang=\"en\" dir=\"ltr\">YouTube · @cicttamil</span> · <bdi>23 Sep 2026</bdi>" in page
    assert "the first meeting was held online on 23 Sep 2026." in page
    # after the hero, before the section for the institutions (the reel that stood above it is in KTS 5.0 in the news, 1.2.105)
    assert page.index('<section class="hero">') < page.index('class="section home-reel home-uzbek"') \
        < page.index("For Higher Educational Institutions")

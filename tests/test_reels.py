"""
Reels and shorts on the programme page: the short videos of CICT on YouTube in which the Thirukkural
is explained in another language (data/reels.json).

    python -m pytest tests -q
"""
import json
import re

from conftest import ROOT, make_app

REELS = json.loads((ROOT / "data" / "reels.json").read_text(encoding="utf-8"))


def test_the_list_holds_youtube_videos_only():
    assert REELS[0] == {"id": "adis-vEEOac", "lang": "Magahi", "native": "मगही", "presenter": "Madhulika"}
    for row in REELS:
        assert set(row) == {"id", "lang", "native", "presenter"}
        assert re.fullmatch(r"[A-Za-z0-9_-]{11}", row["id"]), row
    assert len({r["id"] for r in REELS}) == len(REELS)


def test_the_programme_page_links_every_short():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    page = client.get("/programme?lang=en").get_data(as_text=True)
    # under the card "Reels and shorts" of part II, which leads to them
    assert '<h3 id="reels" style="margin-top:28px">Reels and shorts</h3>' in page
    assert page.index("<h3>Reels and shorts</h3>") < page.index('id="reels"') < page.index("Reaching students who do not speak Tamil")
    assert '<a class="btn sm secondary" href="#reels">▶ ' in page
    langs = list(dict.fromkeys(r["lang"] for r in REELS))
    assert f"{len(REELS)} short videos in {len(langs)} languages" in page
    for row in REELS:
        assert f'href="https://www.youtube.com/shorts/{row["id"]}"' in page
    assert page.count('<div class="card reel">') == len(langs)
    # the presenters of one language stand under it: two in Kurukh
    kurukh = page.split("कुँड़ुख़")[1].split('<div class="card reel">')[0]
    assert "Bhubaneswar Oraon" in kurukh and "Mahesh S. Minj" in kurukh
    # ten in Hindi under one card, in the order of CICT's list
    hindi = page.split("<bdi>हिन्दी</bdi>")[1].split('<div class="card reel">')[0]
    assert hindi.count("youtube.com/shorts/") == 10 and hindi.index("Imtiyaz Dhafrani") < hindi.index("Mrs. Sabitri Tripathy")
    assert "facebook.com" not in page.split('id="reels"')[1].split("<footer")[0]
    assert 'href="https://www.youtube.com/@cicttamil/shorts"' in page
    # in Tamil the texts are Tamil, the names stay as they are written
    from kts.i18n import CATALOG
    tamil = client.get("/programme?lang=ta").get_data(as_text=True)
    assert CATALOG["ta"]["prog.reels.d"] in tamil and "Madhulika" in tamil and "Reels and shorts" not in tamil


def test_the_gaming_app_card_leads_to_the_four_games():
    import json
    app = make_app(ADMIN_PASSWORD=None)
    page = app.test_client().get("/programme?lang=en").get_data(as_text=True)
    card = page.split("Thirukkural Gaming App")[1].split("</div></div>")[0]
    # the same addresses as the entries of the repository
    seeds = {r["key"]: r["url"] for r in json.loads((ROOT / "data" / "resources.json").read_text(encoding="utf-8"))}
    for key in ("kural-bridge", "kural-run", "kural-crossword"):
        assert f'href="{seeds[key]}" target="_blank" rel="noopener"' in card, key
    assert seeds["classroom-quiz"] == "/quiz" and 'href="/quiz/">Classroom quiz</a>' in card
    assert card.index("Kural Bridge") < card.index("Kural Run") < card.index("Kural Crossword") < card.index("Classroom quiz")

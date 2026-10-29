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
    # thirteen in Hindi under one card, in the order of CICT's list (two added in 1.2.89, one in 1.2.117)
    hindi = page.split("<bdi>हिन्दी</bdi>")[1].split('<div class="card reel">')[0]
    assert hindi.count("youtube.com/shorts/") == 13 and hindi.index("Imtiyaz Dhafrani") < hindi.index("Mrs. Sabitri Tripathy")
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


def test_the_russian_short_of_naira_mkrtchyan():
    # added on 15 October 2026 (1.2.73), beside her Armenian short
    russian = [r for r in REELS if r["id"] == "FxmtSzR1IyQ"]
    assert russian == [{"id": "FxmtSzR1IyQ", "lang": "Russian", "native": "Русский", "presenter": "Naira Mkrtchyan"}]
    ids = [r["id"] for r in REELS]
    assert ids.index("FxmtSzR1IyQ") == ids.index("gTEOgoSTwfI") + 1


def test_the_shorts_added_on_21_october():
    # five Thirukkural shorts of @cicttamil (1.2.89): two new languages, Rajasthani and Malto, and Kurukh and Hindi
    assert REELS[36:41] == [
        {"id": "Le13vG99i_c", "lang": "Rajasthani", "native": "राजस्थानी", "presenter": "Dr. Gajadan Charan"},
        {"id": "45kzqtUXUk8", "lang": "Kurukh", "native": "कुँड़ुख़", "presenter": "Mahesh S. Minj"},
        {"id": "iqB7VU5SSYE", "lang": "Hindi", "native": "हिन्दी", "presenter": "Shankar Lal Sahu"},
        {"id": "Vg6A_LFynNk", "lang": "Hindi", "native": "हिन्दी", "presenter": "Dr. Gajadan Charan"},
        {"id": "EAvMVUp50-s", "lang": "Malto", "native": "माल्तो", "presenter": "R. George Edward"}]
    app = make_app(ADMIN_PASSWORD=None)
    page = app.test_client().get("/programme?lang=en").get_data(as_text=True)
    assert "47 short videos in 27 languages" in page
    kurukh = page.split("कुँड़ुख़")[1].split('<div class="card reel">')[0]
    assert kurukh.count("youtube.com/shorts/") == 3
    for native in ("माल्तो",):
        card = page.split(f"<bdi>{native}</bdi>")[1].split('<div class="card reel">')[0]
        assert card.count("youtube.com/shorts/") == 1, native


def test_the_shorts_added_on_26_october():
    # three Thirukkural shorts of @cicttamil of 22-24 October (1.2.101): Awadhi (CICT's English line says "Awati", its Tamil
    # line அவதி) and Kisan are new languages; Rajasthani has a second presenter
    assert REELS[41:44] == [
        {"id": "j9ew6qLdTTo", "lang": "Awadhi", "native": "अवधी", "presenter": "Ram Lakhan Pratapgarhi"},
        {"id": "0fFx8qOK-ZY", "lang": "Kisan", "native": "किसान", "presenter": "Dr. Laxman Kishan"},
        {"id": "jHnmlzUEkWY", "lang": "Rajasthani", "native": "राजस्थानी", "presenter": "Dr. Sharda Krishna"}]
    assert len({r["id"] for r in REELS}) == len(REELS) and len({r["lang"] for r in REELS}) == 27
    page = make_app(ADMIN_PASSWORD=None).test_client().get("/programme?lang=en").get_data(as_text=True)
    rajasthani = page.split("<bdi>राजस्थानी</bdi>")[1].split('<div class="card reel">')[0]
    assert rajasthani.count("youtube.com/shorts/") == 2 and "Dr. Sharda Krishna" in rajasthani
    # Kisan has a second short since 1.2.117
    for native in ("अवधी",):
        card = page.split(f"<bdi>{native}</bdi>")[1].split('<div class="card reel">')[0]
        assert card.count("youtube.com/shorts/") == 1, native


def test_the_short_added_on_27_october():
    # the Thirukkural short of @cicttamil in Gondi by Sidam Varaprasad (1.2.111): the second of the Gondi card
    assert REELS[44] == {"id": "ZpDwuVm8O1U", "lang": "Gondi", "native": "गोंडी", "presenter": "Sidam Varaprasad"}
    assert len({r["lang"] for r in REELS}) == 27
    page = make_app(ADMIN_PASSWORD=None).test_client().get("/programme?lang=en").get_data(as_text=True)
    gondi = page.split("<bdi>गोंडी</bdi>")[1].split('<div class="card reel">')[0]
    assert gondi.count("youtube.com/shorts/") == 2 and "Madhavi Limbarao" in gondi and "Sidam Varaprasad" in gondi


def test_the_shorts_added_on_29_october():
    # two Thirukkural shorts of @cicttamil of 27 and 28 October (1.2.117): Vijay Chittori, Awadhi translator, in Hindi, and
    # a second recording of Dr. Laxman Kishan in Kisan
    assert REELS[45:] == [
        {"id": "_3tLAQMZ_eQ", "lang": "Hindi", "native": "हिन्दी", "presenter": "Vijay Chittori"},
        {"id": "Kd5sxY9ltOY", "lang": "Kisan", "native": "किसान", "presenter": "Dr. Laxman Kishan"}]
    assert len(REELS) == 47 and len({r["lang"] for r in REELS}) == 27
    page = make_app(ADMIN_PASSWORD=None).test_client().get("/programme?lang=en").get_data(as_text=True)
    hindi = page.split("<bdi>हिन्दी</bdi>")[1].split('<div class="card reel">')[0]
    assert hindi.rindex("Vijay Chittori") > hindi.index("Dr. Gajadan Charan")
    kisan = page.split("<bdi>किसान</bdi>")[1].split('<div class="card reel">')[0]
    assert kisan.count("youtube.com/shorts/") == 2 and kisan.index("0fFx8qOK-ZY") < kisan.index("Kd5sxY9ltOY")

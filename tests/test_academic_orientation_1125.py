"""
The Academic Orientation of CICT on the portal (1.2.214). CICT, 25 November 2026, of the page that said "The content of the academic
orientation will be published here.": "CICT | KTS 5.O | Thirukkural Payilvom - 108 Thirukkural | First Hindi then all languages" -
the four video lectures of CICT on the 108 Thirukkural (chapters 1-27, 28-54, 55-81, 82-108) in each language, Hindi first. And
the latest Thirukkural reels of @cicttamil: seven in Tamil, each with its topic.

    python -m pytest tests/test_academic_orientation_1125.py -q
"""
import json
import re

from conftest import ROOT, make_app

ROWS = json.loads((ROOT / "data" / "academic_orientation.json").read_text(encoding="utf-8"))
REELS = json.loads((ROOT / "data" / "reels.json").read_text(encoding="utf-8"))


def test_the_lectures():
    assert len(ROWS) == 48 and len({r["youtube"] for r in ROWS}) == 48      # 20 up to 1.2.227; 7 languages more in 1.2.228
    assert [r["lang"] for r in ROWS[:4]] == ["hi"] * 4                        # Hindi first
    for r in ROWS:
        assert set(r) == {"lang", "session", "chapters", "youtube", "seconds", "published"}
        assert re.fullmatch(r"[A-Za-z0-9_-]{11}", r["youtube"]) and 300 < r["seconds"] < 3600      # the Odia ones are of 8-9 minutes
        assert r["chapters"] == {1: [1, 27], 2: [28, 54], 3: [55, 81], 4: [82, 108]}[r["session"]]
    langs = {}
    for r in ROWS:
        langs.setdefault(r["lang"], []).append(r["session"])
    assert langs == {code: [1, 2, 3, 4] for code in ("hi", "en", "ml", "sa", "ta", "bn", "gu", "kn", "mr", "or", "te", "ur")}


def test_the_page():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/academic-orientation?lang=en").get_data(as_text=True)
    main = page[page.index("<main"):page.index("</main>")]
    assert "The content of the academic orientation will be published here." not in main
    assert "The 108 Thirukkural · Video lectures" in main and 'href="/thirukkural-108"' in main
    # a card for each language, Hindi first, then the others in the order of the languages of the portal
    cards = re.findall(r'<div class="card acad-lang" id="acad-([a-z]+)">', main)
    from kts.i18n import LANG_INFO
    order = ["hi"] + [c for c in LANG_INFO if c != "hi" and c in {r["lang"] for r in ROWS}]
    assert cards == order and len(cards) == 12      # 5 up to 1.2.227
    for r in ROWS:
        assert f'href="https://www.youtube.com/watch?v={r["youtube"]}"' in main
    hindi = main[main.index('id="acad-hi"'):main.index(f'id="acad-{cards[1]}"')]
    assert hindi.count("youtube.com/watch?v=") == 4 and "हिन्दी" in hindi
    assert hindi.index("Chapters <bdi dir=\"ltr\">1–27</bdi>") < hindi.index("Chapters <bdi dir=\"ltr\">82–108</bdi>")
    # each lecture with its first and last chapter, and its length
    assert "The Praise of God (Katavul Vaazhththu)" in hindi and "Baseness (Kayamai)" in hindi and "24 min" in hindi
    # the day of the orientation stays, and the orientation lectures and the study material are a click away
    assert "Academic orientation by CICT" in main and 'href="/orientation"' in main
    # in Tamil: the chapters in Tamil
    tamil = client.get("/academic-orientation?lang=ta").get_data(as_text=True)
    assert "கடவுள் வாழ்த்து" in tamil and "கயமை" in tamil


def test_the_link_on_the_home_page():
    # CICT, 25 November 2026: "at home a prominant link should be given with a proper highlighting with color and font highlighting"
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/?lang=en").get_data(as_text=True)
    band = re.split(r'<div class="quiz-band"|<nav class="quick-links"', page[page.index('<div class="acad-band"'):])[0]      # by itself (1.2.215)
    assert 'href="/academic-orientation"' in band and "Academic Orientation: The 108 Thirukkural · Video lectures" in band
    assert '<span class="new-badge">NEW</span>' in band and "color:#ffd166;font-weight:800;font-size:1.4rem" in band
    langs = re.findall(r'<bdi lang="([a-z-]+)">', band)
    from kts.i18n import LANG_INFO
    assert langs == ["hi"] + [c for c in LANG_INFO if c != "hi" and c in {r["lang"] for r in ROWS}] and len(langs) == 12 and "हिन्दी" in band
    # high on the page: under the band of the circulars, above the quick links and the hero
    assert page.index('class="nodal-attention"') < page.index('class="acad-band"') < page.index('class="quick-links"') < page.index('class="hero"')
    # in every language, in its words
    tamil = client.get("/?lang=ta").get_data(as_text=True)
    from kts.i18n import CATALOG
    assert CATALOG["ta"]["nav.acad"] in tamil[tamil.index('class="acad-band"'):tamil.index('class="quick-links"')]


def test_the_tamil_reels():
    new = [r for r in REELS if r["lang"] == "Tamil"]
    assert [r["id"] for r in new] == ["JHEHNq387oU", "bYlR7k8UvrY", "9gaYo2DnHCs", "3L-0ullP87g", "-41h8VnAqpQ", "pX3Xgj79HFk", "B7KjNFCdv5Q"]
    assert REELS[-7:] == new and len(REELS) == 56
    assert all(r["native"] == "தமிழ்" and r["presenter"] == "CICT" and r["topic"] and r["topic_en"] for r in new)
    page = make_app(ADMIN_PASSWORD=None).test_client().get("/programme?lang=en").get_data(as_text=True)
    assert "56 short videos in 29 languages" in page
    tamil = page.split("<bdi>தமிழ்</bdi>")[1].split("</ul>")[0]
    assert tamil.count("youtube.com/shorts/") == 7
    assert '<bdi lang="ta">திருக்குறள் கூறும் கள்ளுண்ணாமை</bdi>' in tamil and "Abstaining from drinking as described in the Thirukkural" in tamil

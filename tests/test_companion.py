"""
The Thirukkural study companion (version 1.2.119): a question in any of the 23 languages answered with the couplets that
speak of it (kts/companion.py), on the portal alone and free to use; the page /companion, its self-check, its place in
the menu and the sitemap, and its switch in the Console.

    python -m pytest tests -q
"""
import re

from markupsafe import escape

from conftest import make_app

FRIEND = [79, 80, 81, 82, 83]
LOVE = list(range(109, 134))

# questions as students write them, with the chapters that answer them; the companion must name one of them first
QUESTIONS = [
    ("en", "What does Valluvar say about friendship?", FRIEND),
    ("en", "How should I choose my friends?", [80, 79, 51, 46, 82]),
    ("en", "Why is education important?", [40, 41, 42, 43]),
    ("en", "How should we treat our guests?", [9]),
    ("en", "Why should I be grateful to those who helped me?", [11]),
    ("en", "What is the importance of rain?", [2]),
    ("en", "Why is farming important?", [104]),
    ("en", "Should we eat meat?", [26]),
    ("en", "Why is drinking alcohol bad?", [93]),
    ("en", "Is gambling harmful?", [94]),
    ("en", "How to stay healthy and avoid disease?", [95]),
    ("en", "How should a king rule his people?", [39, 55, 56]),
    ("en", "Why should we be patient and forgive others?", [16]),
    ("en", "Why is jealousy bad?", [17]),
    ("en", "Should we speak ill of others behind their back?", [19]),
    ("en", "What is the value of hard work?", [62, 60, 61]),
    ("en", "How to face troubles without losing heart?", [63]),
    ("en", "When is the right time to act?", [49]),
    ("en", "Is everything decided by fate?", [38]),
    ("en", "missing the beloved who has gone away", LOVE),
    ("ta", "நட்பு பற்றி வள்ளுவர் என்ன கூறுகிறார்?", FRIEND),
    ("ta", "கோபத்தை எப்படி அடக்குவது?", [31, 16]),
    ("ta", "கல்வியின் சிறப்பு என்ன?", [40, 41, 42]),
    ("ta", "விவசாயம் ஏன் முக்கியம்?", [104]),
    ("ta", "மது அருந்துவது தீமையா?", [93]),
    ("ta", "உழைப்பின் பெருமை", [62, 60]),
    ("hi", "दोस्ती के बारे में वल्लुवर क्या कहते हैं?", FRIEND),
    ("hi", "गुस्से पर कैसे काबू करें?", [31, 16]),
    ("hi", "शिक्षा का महत्व", [40, 41, 42]),
    ("hi", "खेती क्यों जरूरी है?", [104]),
    ("hi", "शराब पीना", [93]),
    ("bn", "বন্ধুত্ব", FRIEND),
    ("te", "స్నేహం", FRIEND),
    ("gu", "મિત્રતા", FRIEND),
    ("ur", "دوستی", FRIEND),
    ("te", "కోపం", [31, 16]),
    ("sat", "ᱜᱟᱛᱮ", FRIEND),
    ("ks", "غصہ", [31, 132]),
    ("as", "বন্ধুত্ব", FRIEND),
    ("brx", "राग", [31]),
]


def test_words_keep_the_vowel_signs():
    from kts.companion import terms, words
    # \w of Python's regular expressions would cut these at every vowel sign and virama
    assert words("हिन्दी में क्रोध!") == ["हिन्दी", "में", "क्रोध"]
    assert words("நட்பின் பெருமை?") == ["நட்பின்", "பெருமை"]
    assert words("Friendship, IS it?") == ["friendship", "is", "it"]
    # a word is found by its beginning: "friend" in "friendship", மழை in மழையின்
    assert ("friend*", 0.35) in terms("friendship") and ("friend*", 0.35) in terms("friend")
    assert ("மழை*", 0.35) in terms("மழையின்") and ("மழை*", 0.35) in terms("மழை")
    assert terms("friends")[0] == ("friend", 1.0)


def test_the_questions_of_students():
    from kts import kural as K
    from kts.companion import ask
    wrong = []
    for stream, q, want in QUESTIONS:
        a = ask(q, stream)
        if not a["chapters"] or a["chapters"][0] not in want:
            wrong.append((q, a["chapters"]))
        # a couplet of a right chapter among the first five
        assert any(K.kural(n)["adhigaram"] in want for n in a["kurals"][:5]), (q, a["kurals"][:5])
    assert not wrong, wrong


def test_a_number_and_nothing():
    from kts.companion import MAX_SHOWN, ask
    a = ask("381", "en")
    assert a["number"] == 381 and a["kurals"][0] == 381 and a["chapters"][0] == 39
    a = ask("Kural 1330", "ta")
    assert a["kurals"][0] == 1330 and a["chapters"][0] == 133
    # words that are in no couplet, and words that every question has
    for q in ("xyzzy qwrtp", "what does Valluvar say about it?", "", "  "):
        assert ask(q, "en")["kurals"] == [], q
    assert len(ask("friendship", "en")["kurals"]) == MAX_SHOWN


def test_the_page_in_every_language():
    from kts.i18n import CATALOG
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for code, catalogue in CATALOG.items():
        page = client.get(f"/companion?lang={code}").get_data(as_text=True)
        assert f"<h1>{escape(catalogue['comp.title'])}</h1>" in page, code
        # without a question: the subjects to start from, and no answer
        assert page.count('<li><a class="pill" href="/companion?q=') == 10 and 'class="card comp-card"' not in page, code
        page = client.get(f"/companion?lang={code}&q=friendship").get_data(as_text=True)
        assert page.count('class="card comp-card"') == 5 and str(escape(catalogue["comp.lead"])) in page, code
        assert '<a href="/thirukkural?ch=79">' in page.split('class="card accent comp-lead"')[1].split("</div>")[0], code
        assert "comp." not in re.sub(r'class="[^"]*"|id="[^"]*"|href="[^"]*"', "", page.split('id="main"')[1]), code
    # the translation of the page's language, the Tamil commentary, the English, a reading in Tamil
    page = client.get("/companion?lang=hi&q=मित्रता").get_data(as_text=True)
    card = page.split('class="card comp-card"')[1]
    assert '<div class="comp-tr" dir="ltr" lang="hi">' in card and 'lang="en"' in card and 'class="comp-urai"' in card
    assert 'data-listen="/static/audio/ta/' in card
    # Tamil: the commentary open, no English
    card = client.get("/companion?lang=ta&q=நட்பு").get_data(as_text=True).split('class="card comp-card"')[1]
    assert '<details class="comp-urai" open>' in card and 'lang="en"' not in card.split("</li>")[0]


def test_more_couplets_and_escaping():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/companion?lang=en&q=friendship").get_data(as_text=True)
    assert '<a class="btn secondary" href="/companion?q=friendship&amp;more=1">' in page
    page = client.get("/companion?lang=en&q=friendship&more=1").get_data(as_text=True)
    assert page.count('class="card comp-card"') == 20 and "more=1" not in page.split('class="comp-list"')[1].split("</ol>")[0]
    page = client.get("/companion?lang=en&q=<script>alert(1)</script> anger").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;alert(1)&lt;/script&gt; anger" in page
    page = client.get("/companion?lang=en&q=xyzzy+qwrtp").get_data(as_text=True)
    assert 'class="card comp-none"' in page and 'class="card comp-card"' not in page


def test_the_self_check_never_asks_what_the_question_bank_asks():
    from kts.db import query
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    for code in ("en", "ta", "hi"):
        page = client.get(f"/companion?lang={code}&q=friendship").get_data(as_text=True)
        check = page.split('class="card comp-check"')[1].split("</section>")[0]
        asked = [int(n) for n in re.findall(r'href="/thirukkural/(\d+)"', check)]
        assert 1 <= len(asked) <= 3, code
        with app.app_context():
            taken = {r["kural_no"] for r in query(
                "SELECT kural_no FROM questions WHERE lang = ? AND qtype = 'complete' AND kural_no IS NOT NULL", (code,))}
        assert not set(asked) & taken, code


def test_menu_sitemap_and_switch():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    home = client.get("/?lang=en").get_data(as_text=True)
    menu = home[home.index('<li class="has-sub"><a href="/thirukkural"'):]
    menu = menu[:menu.index("</ul></li>")]
    assert '<li><a href="/companion">Thirukkural study companion</a></li>' in menu
    assert '<a href="/thirukkural">' in menu and '<a href="/daily-kural">' in menu
    assert 'href="/companion"' in client.get("/thirukkural").get_data(as_text=True)
    assert "/companion</loc>" in client.get("/sitemap.xml").get_data(as_text=True)
    page = client.get("/companion?q=anger").get_data(as_text=True)
    assert 'class="active" aria-haspopup="true">Thirukkural</a>' in page
    with app.app_context():
        set_setting("companion.on", "0")
    assert client.get("/companion").status_code == 404
    assert 'href="/companion"' not in client.get("/thirukkural").get_data(as_text=True)
    assert '<a href="/companion">' not in client.get("/").get_data(as_text=True)


def test_the_everyday_words_of_the_chapters():
    import json
    from conftest import ROOT
    from kts.companion import lexicon, words
    data = json.loads((ROOT / "data" / "companion_lexicon.json").read_text(encoding="utf-8"))
    # the 23 languages of the portal, every chapter with words of its subject
    assert len(data) == 23 and all(sorted(t, key=int) == [str(i) for i in range(1, 134)] for t in data.values())
    assert all(all(t.values()) for t in data.values())
    assert "anger" in data["en"]["31"] and "கோபம்" in data["ta"]["31"] and "दोस्ती" in data["hi"]["79"]
    assert len(lexicon()) == 133
    # the optional marks of the Arabic script and of Ol Chiki are read the same with or without them
    assert words("غصہٕ") == words("غصہ") == ["غصہ"] and words("ᱮᱫᱽᱨᱮ") == words("ᱮᱫᱨᱮ")

"""
The recorded lectures of the online orientation (data/orientation_lectures.json, version 1.2.78): the English and
Tamil sessions on CICT's YouTube channel, on the cards of their languages on the Online orientation programme page.

    python -m pytest tests -q
"""
import json
import re
from pathlib import Path

from conftest import make_app

ROOT = Path(__file__).resolve().parents[1]
LECTURES = json.loads((ROOT / "data" / "orientation_lectures.json").read_text(encoding="utf-8"))
CARD = {"en": ">English</bdi>", "ta": ">தமிழ்</bdi>", "hi": ">हिन्दी</bdi>", "ml": ">മലയാളം</bdi>", "kn": ">ಕನ್ನಡ</bdi>",
        "sa": ">संस्कृतम्</bdi>", "mr": ">मराठी</bdi>", "te": ">తెలుగు</bdi>", "ne": ">नेपाली</bdi>", "ur": ">اُردُو</bdi>",
        "kok": ">ಕೊಂಕಣಿ</bdi>", "as": ">অসমীয়া</bdi>", "bn": ">বাংলা</bdi>", "mni": ">মৈতৈলোন্</bdi>",
        # 1 November (1.2.134)
        "mai": ">मैथिली</bdi>", "doi": ">डोगरी</bdi>", "gu": ">ગુજરાતી</bdi>", "pa": ">ਪੰਜਾਬੀ</bdi>", "sat": ">ᱥᱟᱱᱛᱟᱲᱤ</bdi>", "or": ">ଓଡ଼ିଆ</bdi>", "sd": ">सिन्धी</bdi>",
        # 7 November (1.2.166)
        "brx": ">बड़ो</bdi>", "ks": ">कॉशुर</bdi>"}


def test_the_list_of_lectures():
    # the lectures of CICT's channel @CICT_Online, uploaded again on 21 October 2026 (1.2.91): 11 videos, 6 languages;
    # seven more by 26 October (1.2.101): Sanskrit 2, Marathi, Telugu and Nepali 1 and 2 = 18 videos, 9 languages; ten more
    # by 27 October (1.2.111): Urdu, Konkani, Assamese, Bengali and Manipuri 1 and 2 = 28 videos, 14 languages
    assert [(r["lang"], r["session"], r["youtube"]) for r in LECTURES] == [
        ("en", 1, "i_hSXzH5E9w"), ("en", 2, "Gw2g60MdH7I"), ("ta", 1, "85IHyYchdPE"), ("ta", 2, "FN-VgfQYoec"),
        ("hi", 1, "-z09JR2Z0nM"), ("hi", 2, "JkqyOBbmZxM"), ("ml", 1, "rJIF59YGhY4"), ("ml", 2, "gyNucEOvkTQ"),
        ("kn", 1, "AVuHG4b7XLI"), ("kn", 2, "IVg8GRzGDkc"), ("sa", 1, "5okDiOi4xYE"), ("sa", 2, "ZK4XvOiqiyU"),
        ("mr", 1, "DbHlmaVJTGo"), ("mr", 2, "-d6t_U9H8ok"), ("te", 1, "5XVI2_IPTh8"), ("te", 2, "esFy7zlzcAw"),
        ("ne", 1, "bcxdaQUzIpw"), ("ne", 2, "PIZsaQ-eLiU"), ("ur", 1, "0xFPlQM7xIw"), ("ur", 2, "5fCWISksGdI"),
        ("kok", 1, "GhRFpS3-O0g"), ("kok", 2, "MJ-Uv6M7ZBE"), ("as", 1, "QZT4lrKO0NQ"), ("as", 2, "eRpYMAHBNmI"),
        ("bn", 1, "PFDRJxvvahE"), ("bn", 2, "06ReFAfIz_M"), ("mni", 1, "1c78-AyG790"), ("mni", 2, "F1YEcxOSPJI"),
        # 1 November (1.2.134): thirteen more, and the Manipuri session 1 put up again by CICT (xAMAWU53XL8 before)
        ("mai", 1, "jgsx1xO1DrA"), ("mai", 2, "-m-eQ_hFbz0"), ("doi", 1, "8gsv4Nvd-wM"), ("doi", 2, "LytuiBhl4J0"),
        ("gu", 1, "8pvsooC75C0"), ("gu", 2, "6WkyzSJ34yo"), ("pa", 1, "nPpVYeKzBP4"), ("pa", 2, "htxlKleIIkM"),
        ("sat", 1, "j7thl1widis"), ("sat", 2, "vT6SUoS3SbA"), ("or", 1, "351WmVjnBWk"), ("or", 2, "-xYX5_HNsk4"),
        ("sd", 1, "kf5bDo1KQi8"),
        # 3 November (1.2.141)
        ("sd", 2, "YSMh6xfSabs"),
        # uploaded on 5 November, added on 7 November (1.2.166): Bodo and Kashmiri
        ("brx", 1, "zsTSSCRrEv0"), ("brx", 2, "lLHE2wpJQ0g"), ("ks", 1, "_ue0Vrsvf_M"), ("ks", 2, "I-hw1vsJQyc")]
    # by 1 November (1.2.134): Maithili, Dogri, Gujarati, Punjabi, Santali and Odia 1 and 2, Sindhi 1 = 41 videos, 21 languages
    # and Sindhi 2 by 3 November (1.2.141) = 42 videos
    # and Bodo and Kashmiri 1 and 2 on 7 November (1.2.166) = 46 videos, all 23 languages
    assert len({r["youtube"] for r in LECTURES}) == 46 and len({r["lang"] for r in LECTURES}) == 23
    # the earlier addresses, removed from the channel, are gone from the page
    old = {"GF6HH7H9zlk", "2w6mgosRYAE", "Z3fGrbHLFr8", "tL9j8Dz7LLw", "FP8bmjuvpuk", "ptuQ7RaWf34", "q-8j2uP_lAA", "HUH2ZriU-0A",
           "U6hypuFpDRA", "BRczoN6wNa0", "A8qPl1T916Y", "_BSi16KkrXw", "g9qHDwL2i04", "oLDi_Yn7MU0"}
    assert not old & {r["youtube"] for r in LECTURES}
    assert [r["title"] for r in LECTURES][:6] == ["Session 01 · Thirukkural and Thiruvalluvar",
                                                  "Session 02 · Insights from the Thirukkural",
                                                  "பாடம் 01 · திருக்குறள் மற்றும் திருவள்ளுவர்",
                                                  "பாடம் 02 · திருக்குறள் சிந்தனைகள்",
                                                  "पाठ 01 · तिरुक्कुऱळ् और तिरुवळ्ळुवर्", "पाठ 02 · तिरुक्कुऱळ् के विचार"]
    # CICT's English titles for the lectures in Malayalam, Kannada, Sanskrit, Marathi, Telugu, Nepali, Urdu, Konkani, Assamese,
    # Bengali and Manipuri are marked as English
    for r in LECTURES[6:]:
        assert r["title_lang"] == "en" and r["title"] in ("Session 01 · Thirukkural and Thiruvalluvar",
                                                          "Session 02 · Insights from the Thirukkural")
    from kts import kural as K
    for row in LECTURES:
        assert re.fullmatch(r"[A-Za-z0-9_-]{11}", row["youtube"]) and row["lang"] in K.ORIENTATION_LANGS


def test_each_card_shows_the_lectures_of_its_language():
    from kts.i18n import CATALOG
    app = make_app(ADMIN_PASSWORD=None)
    for lang in ("en", "ta", "hi"):
        page = app.test_client().get(f"/orientation?lang={lang}").get_data(as_text=True)
        cards = page.split('<div class="card">')[1:]
        with_lectures = []
        for code, heading in CARD.items():
            card = next(c for c in cards if heading in c)
            with_lectures.append(card)
            for row in (r for r in LECTURES if r["lang"] == code):
                assert (f'<a href="https://www.youtube.com/watch?v={row["youtube"]}" target="_blank" rel="noopener">'
                        f'<span aria-hidden="true">▶</span> <bdi lang="{row.get("title_lang") or code}">{row["title"]}</bdi></a>') in card, (lang, code)
        english = with_lectures[0]
        assert english.index("i_hSXzH5E9w") < english.index("Gw2g60MdH7I") and "85IHyYchdPE" not in english
        # these cards no longer say that their sessions are yet to be scheduled; the other cards still do
        tbs = CATALOG[lang]["orient.tbs"]
        assert all(tbs not in c for c in with_lectures)
        assert all(tbs in c for c in cards if not any(c is w for w in with_lectures)), lang

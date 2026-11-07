"""
The article/research note of at least 4 and not more than 10 pages, everywhere; item 7 with the college's website (1.2.167; CICT,
7 November 2026: "minimum 4 pages and not more than 10 pages and arrange for it to appear in the college website and college's
social media the local news media").

    python -m pytest tests/test_1107c.py -q
"""
from conftest import make_app

KEYS = ("reg.declare_participate", "reg.cdeclare_participate", "about.p2", "prog.i7.d", "paper.card_text", "paper.f_file",
        "guide.s6", "nl.b2", "nl.art_c4")


def test_the_minimum_in_every_text():
    from kts.i18n import CATALOG
    en = CATALOG["en"]
    for key in KEYS:
        text = en[key]
        assert ("at least 4 and not more than 10 pages" in text or "4 to 10 pages" in text
                or "at least four and not more than ten pages" in text), key
    assert en["paper.f_file"].startswith("The article/research note (4 to 10 pages)")
    assert "an article of 4 to 10 pages" in en["nl.art_c4"]
    assert en["prog.i7.d"].endswith("The student and the institution post the news of KTS 5.0 on the student's social media and "
                                     "arrange for it to appear on the college's website and social media and in the local news media.")
    # every language has its own words for them
    for code, cat in CATALOG.items():
        if code != "en":
            for key in KEYS:
                assert cat[key] != en[key], (code, key)


def test_the_pages():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    programme = client.get("/programme?lang=en").get_data(as_text=True)
    assert "an original article or research note of at least 4 and not more than 10 pages" in programme
    assert "on the college&#39;s website and social media and in the local news media" in programme
    assert "write an article or research note of at least 4 and not more than 10 pages" in client.get("/about?lang=en").get_data(as_text=True)

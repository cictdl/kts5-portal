"""
The syllabus of the institution-level assessment (version 1.2.98): CICT's study book "Thirukkural Payilvom – Let's Learn
Thirukkural" in Tamil and in translation, one PDF per language under static/syllabus, listed in data/syllabus.json, on the
page /syllabus with the visitor's language first, and linked from the assessment, the 108 Thirukkural, the menu, the
repository, the sitemap and the search.

    python -m pytest tests -q
"""
import json

from markupsafe import escape

from conftest import ROOT, make_app

BOOKS = json.loads((ROOT / "data" / "syllabus.json").read_text(encoding="utf-8"))


def _page(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def test_each_book_has_its_pdf_and_cover():
    from kts import kural as K
    # Tamil, English, Hindi, Kannada and Marathi in 1.2.98; Bengali, Maithili and Odia in 1.2.114 (with the new editions of
    # the Hindi and the Marathi book); Gujarati, Santali and Telugu in 1.2.120
    assert [b["lang"] for b in BOOKS] == ["ta", "en", "bn", "gu", "hi", "kn", "mai", "mr", "or", "sat", "te"]
    for b in BOOKS:
        assert b["lang"] in K.ORIENTATION_LANGS and b["pages"] > 40
        name = f"KTS5-Thirukkural-Payilvom-{b['lang']}"
        pdf, thumb = ROOT / "static" / "syllabus" / f"{name}.pdf", ROOT / "static" / "syllabus" / "thumbs" / f"{name}.jpg"
        assert pdf.read_bytes()[:5] == b"%PDF-" and pdf.stat().st_size < 3_000_000, b["lang"]
        assert thumb.read_bytes()[:3] == b"\xff\xd8\xff" and thumb.stat().st_size < 60_000, b["lang"]
        # the Tamil book is the original; each translation names its translator
        assert bool(b["translator"]) == (b["lang"] != "ta"), b["lang"]


def test_the_page_offers_the_visitors_language_first():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = _page(client, "/syllabus?lang=en")
    assert "Syllabus for the institution-level assessment" in page and "Let&#39;s Learn Thirukkural" in page
    books = page[page.index('id="books"'):]
    assert books.count('class="card syl-book"') == len(BOOKS) and books.count("⬇ Download (PDF)") == len(BOOKS)
    assert books.index("KTS5-Thirukkural-Payilvom-en.pdf") < books.index("KTS5-Thirukkural-Payilvom-ta.pdf")
    assert "In your language" in books and "Translator: <bdi>Dr. Sripada Divya</bdi>" in books
    assert "The original, in Tamil" in books and "61 pages · PDF" in books
    assert 'href="/static/syllabus/KTS5-Thirukkural-Payilvom-hi.pdf" download' in books
    assert "The study book is not yet available in your language" not in page
    # a language without its book yet (Malayalam since 1.2.120, Telugu before): told so, and the books as the file lists
    # them, Tamil first
    malayalam = _page(client, "/syllabus?lang=ml")
    from kts.i18n import CATALOG
    assert str(escape(CATALOG["ml"]["syl.not_yet"])) in malayalam
    m_books = malayalam[malayalam.index('id="books"'):]
    assert m_books.index("Payilvom-ta.pdf") < m_books.index("Payilvom-en.pdf") < m_books.index("Payilvom-mr.pdf")
    assert str(escape(CATALOG["ml"]["syl.yours"])) not in m_books


def test_the_syllabus_is_reached_from_where_students_look():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    exam = _page(client, "/examination?lang=en")
    assert exam.count('href="/syllabus"') >= 2 and '<span lang="ta">தமிழ்</span>' in exam and '<span lang="mr">मराठी</span>' in exam
    assert 'href="/syllabus"' in _page(client, "/thirukkural-108?lang=en")
    assert '<li><a href="/syllabus">Syllabus for the institution-level assessment</a></li>' in _page(client, "/about?lang=en")
    assert 'href="/syllabus"' in _page(client, "/sitemap?lang=en")
    assert 'href="/syllabus"' in _page(client, "/resources?cat=study&lang=en")
    assert "/syllabus" in _page(client, "/search?lang=en&q=syllabus")


def test_the_books_added_on_28_october():
    # the Bengali book of 28 October, 10:52 (1.2.115): its cover title drawn right, the vowel signs ি before their consonants
    import fitz
    bengali = fitz.open(ROOT / "static" / "syllabus" / "KTS5-Thirukkural-Payilvom-bn.pdf")
    assert bengali.metadata["modDate"].startswith("D:20261028") and "(Bengali)" in bengali[0].get_text()
    by_lang = {b["lang"]: b for b in BOOKS}
    assert {k: (by_lang[k]["pages"], by_lang[k]["translator"]) for k in ("bn", "mai", "or")} == {
        "bn": (84, "Dr. Shibnath Dutta"), "mai": (64, "Dr. Arun Kumar"), "or": (62, "Geetarani Bisoyi")}
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = _page(client, "/syllabus?lang=or")
    assert page.index("KTS5-Thirukkural-Payilvom-or.pdf") < page.index("KTS5-Thirukkural-Payilvom-ta.pdf")
    assert "Geetarani Bisoyi" in page and "The study book is not yet available in your language" not in page
    for code in ("bn", "mai"):
        assert f'href="/static/syllabus/KTS5-Thirukkural-Payilvom-{code}.pdf" download' in _page(client, f"/syllabus?lang={code}")


def test_the_books_added_on_30_october():
    # Gujarati, Santali (in Ol Chiki) and Telugu, uploaded by CICT on 29 October (1.2.120)
    import fitz
    by_lang = {b["lang"]: b for b in BOOKS}
    assert {k: (by_lang[k]["pages"], by_lang[k]["translator"]) for k in ("gu", "sat", "te")} == {
        "gu": (61, "Dr. Neelavaty Meghani"), "sat": (84, "Bodi Baski"), "te": (75, "Dr. S. Jayaprakash")}
    for lang, name in (("gu", "(Gujarati)"), ("sat", "(Santali)"), ("te", "(TELUGU)")):
        cover = fitz.open(ROOT / "static" / "syllabus" / f"KTS5-Thirukkural-Payilvom-{lang}.pdf")[0].get_text()
        assert name in cover and "Translator" in cover, lang
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for lang in ("gu", "sat", "te"):
        page = _page(client, f"/syllabus?lang={lang}")
        assert page.index(f"KTS5-Thirukkural-Payilvom-{lang}.pdf") < page.index("KTS5-Thirukkural-Payilvom-ta.pdf"), lang

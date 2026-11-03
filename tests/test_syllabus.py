"""
The syllabus of the institution-level assessment (version 1.2.98): CICT's study book "Thirukkural Payilvom – Let's Learn
Thirukkural" in Tamil and in translation, one PDF per language under static/syllabus, listed in data/syllabus.json, on the
page /syllabus in the order CICT asked for (Hindi, Sanskrit, Gujarati, Bengali, Kannada, Telugu, the others, English and Tamil
last; 1.2.143), the visitor's own book framed, and linked from the assessment, the 108 Thirukkural, the menu, the
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
    # the Hindi and the Marathi book); Gujarati, Santali and Telugu in 1.2.120; in the order CICT asked for since 1.2.143;
    # Assamese, Konkani, Malayalam, Manipuri, Nepali, Sindhi and Urdu in 1.2.144
    assert [b["lang"] for b in BOOKS] == ["hi", "gu", "bn", "kn", "te", "as", "kok", "mai", "ml", "mni", "mr", "ne", "or", "sat", "sd", "ur", "en", "ta"]
    for b in BOOKS:
        assert b["lang"] in K.ORIENTATION_LANGS and b["pages"] > 40
        name = f"KTS5-Thirukkural-Payilvom-{b['lang']}"
        pdf, thumb = ROOT / "static" / "syllabus" / f"{name}.pdf", ROOT / "static" / "syllabus" / "thumbs" / f"{name}.jpg"
        assert pdf.read_bytes()[:5] == b"%PDF-" and pdf.stat().st_size < 3_000_000, b["lang"]
        assert thumb.read_bytes()[:3] == b"\xff\xd8\xff" and thumb.stat().st_size < 60_000, b["lang"]
        # the Tamil book is the original; each translation names its translator
        assert bool(b["translator"]) == (b["lang"] != "ta"), b["lang"]


def test_the_page_offers_the_books_in_cicts_order():
    # 3 Nov 2026 (1.2.143), CICT: "Hindi, Sanskrit, Gujarati, Bengali, Kannada, Telugu, at last English and Tamil" - for every
    # visitor; the visitor's own book framed where it stands, with a link to it at the top
    from kts import kural as K
    assert K.SYLLABUS_FIRST == ["hi", "sa", "gu", "bn", "kn", "te"] and K.SYLLABUS_LAST == ["en", "ta"]
    ranks = sorted(K.ORIENTATION_LANGS, key=K.syllabus_rank)
    assert ranks[:6] == ["hi", "sa", "gu", "bn", "kn", "te"] and ranks[-2:] == ["en", "ta"] and len(ranks) == 23
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = _page(client, "/syllabus?lang=en")
    assert "Study material for the institution-level assessment" in page and "Let&#39;s Learn Thirukkural" in page   # 1.2.148
    books = page[page.index('id="books"'):]
    assert books.count('class="card syl-book"') == len(BOOKS) and books.count("⬇ Download (PDF)") == len(BOOKS)
    shown = [b["lang"] for b in BOOKS]
    assert [books.index(f"KTS5-Thirukkural-Payilvom-{c}.pdf") for c in shown] == sorted(books.index(f"KTS5-Thirukkural-Payilvom-{c}.pdf") for c in shown)
    assert shown[0] == "hi" and shown[-2:] == ["en", "ta"]
    assert '<div class="card syl-book" id="book-en" lang="en" style="border:2px solid var(--saffron)">' in books
    assert books.count("border:2px solid var(--saffron)") == 1 and '<a href="#book-en">⬇ In your language: <span lang="en">English</span></a>' in page
    assert "In your language" in books and "Translator: <bdi>Dr. Sripada Divya</bdi>" in books
    assert "The original, in Tamil" in books and "61 pages · PDF" in books
    assert 'href="/static/syllabus/KTS5-Thirukkural-Payilvom-hi.pdf" download' in books
    assert "The study book is not yet available in your language" not in page
    # a language without its book yet (Punjabi): told so, the books in the same order, none framed, no link
    punjabi = _page(client, "/syllabus?lang=pa")
    from kts.i18n import CATALOG
    assert str(escape(CATALOG["pa"]["syl.not_yet"])) in punjabi
    p_books = punjabi[punjabi.index('id="books"'):]
    assert p_books.index("Payilvom-hi.pdf") < p_books.index("Payilvom-gu.pdf") < p_books.index("Payilvom-mr.pdf") < p_books.index("Payilvom-en.pdf") < p_books.index("Payilvom-ta.pdf")
    assert 'href="#book-' not in punjabi and str(escape(CATALOG["pa"]["syl.yours"])) not in p_books and "border:2px solid var(--saffron)" not in p_books
    # in Hindi, the Hindi book first and framed
    hindi = _page(client, "/syllabus?lang=hi")
    h_books = hindi[hindi.index('id="books"'):]
    assert h_books.index("Payilvom-hi.pdf") < h_books.index("Payilvom-gu.pdf") and '<div class="card syl-book" id="book-hi" lang="hi" style="border:2px solid var(--saffron)">' in h_books
    # the assessment page lists the languages in the same order
    exam = _page(client, "/examination?lang=en")
    langs = exam[exam.index('class="exam-syllabus"'):]
    langs = langs[:langs.index("</p>")]
    import re
    assert [tag.split("-")[0] for tag in re.findall(r'<span lang="([^"]+)">', langs)] == shown


def test_the_syllabus_is_reached_from_where_students_look():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    exam = _page(client, "/examination?lang=en")
    assert exam.count('href="/syllabus"') >= 2 and '<span lang="ta">தமிழ்</span>' in exam and '<span lang="mr">मराठी</span>' in exam
    assert 'href="/syllabus"' in _page(client, "/thirukkural-108?lang=en")
    assert '<li><a href="/syllabus">Study material for the institution-level assessment</a></li>' in _page(client, "/about?lang=en")
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


def test_the_books_added_on_3_november():
    # CICT's Drive folder of 3 November 2026, "18 Languages - completed & updated" (1.2.144): seven new languages and a new
    # edition of the Marathi book (its Chapter 5 introduction in Marathi instead of Tamil); every one read page by page - all
    # 108 couplets of the Garland in each; the slips found went to CICT
    import fitz
    by_lang = {b["lang"]: b for b in BOOKS}
    assert len(BOOKS) == 18
    assert {k: (by_lang[k]["pages"], by_lang[k]["translator"]) for k in ("as", "kok", "ml", "mni", "ne", "sd", "ur", "mr")} == {
        "as": (92, "Dr. B. Vijayakumar"), "kok": (82, "Shwetha Pai"), "ml": (85, "Dr. N. Manoharan"), "mni": (91, "Dr. Soibam Rebika Devi"),
        "ne": (77, "Dr. Sunita dahal"), "sd": (78, "Dr. M. L. Nathani"), "ur": (82, "پروفیسر ڈاکٹر امان اللہ ایم بی"),
        "mr": (71, "Mrs Padma Sridha")}
    for lang, name in (("as", "(Assamese)"), ("kok", "(Konkani)"), ("ml", "(Malayalam)"), ("mni", "(Manipuri)"), ("ne", "(Nepali)"),
                       ("sd", "(Sindhi)"), ("ur", "(URDU)"), ("mr", "(Marathi)")):
        cover = fitz.open(ROOT / "static" / "syllabus" / f"KTS5-Thirukkural-Payilvom-{lang}.pdf")
        assert name in cover[0].get_text() and "Translator" in cover[0].get_text(), lang
    marathi = fitz.open(ROOT / "static" / "syllabus" / "KTS5-Thirukkural-Payilvom-mr.pdf")
    assert marathi.metadata["creationDate"].startswith("D:20261103")
    # the Konkani book is in Kannada script, as the portal names the language: Konkani (Kannada script)
    client = make_app(ADMIN_PASSWORD=None).test_client()
    konkani = _page(client, "/syllabus?lang=kok")
    card = konkani[konkani.index('id="book-kok"'):]
    card = card[:card.index('class="btn-row"')]
    assert "Konkani (Kannada script)" in card and "Shwetha Pai" in card
    assert 'style="border:2px solid var(--saffron)"' in konkani[konkani.index('id="book-kok"') - 60:konkani.index('id="book-kok"') + 120]
    for lang in ("as", "ml", "mni", "ne", "sd", "ur"):
        page = _page(client, f"/syllabus?lang={lang}")
        assert f'<a href="#book-{lang}">' in page and f'href="/static/syllabus/KTS5-Thirukkural-Payilvom-{lang}.pdf" download' in page, lang
    urdu = _page(client, "/syllabus?lang=ur")
    assert "<bdi>پروفیسر ڈاکٹر امان اللہ ایم بی</bdi>" in urdu


def test_study_material_not_syllabus():
    # 3 Nov 2026 (1.2.148), the user: "Change Syllabus for the institution-level assessment as Study material for the
    # institution-level assessment" - the title, the button and the line of the 108 couplets, in every language; the address
    # stays /syllabus; the repository's entry renamed once where it still has the title it came with
    from kts.i18n import CATALOG
    en = CATALOG["en"]
    assert en["syl.title"] == "Study material for the institution-level assessment" and en["syl.cta"] == "Study material: the study book"
    assert "the study material for the institution-level assessment" in en["syl.k108"]
    assert not any("syllabus" in v.lower() for k, v in en.items() if k.startswith("syl."))
    for code, catalogue in CATALOG.items():
        if code != "en":
            assert all(catalogue[k] != en[k] for k in ("syl.title", "syl.cta", "syl.k108")), code
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = _page(client, "/syllabus?lang=en")
    assert "<h1>Study material for the institution-level assessment</h1>" in page and "Syllabus" not in page
    exam = _page(client, "/examination?lang=en")
    assert "<b>Study material for the institution-level assessment</b>" in exam and "📘 Study material: the study book" in exam
    assert "the study material for the institution-level assessment" in _page(client, "/thirukkural-108?lang=en")
    hindi = _page(client, "/syllabus?lang=hi")
    assert str(escape(CATALOG["hi"]["syl.title"])) in hindi


def test_the_repository_entry_renamed_once():
    from kts.db import execute, query
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        assert query("SELECT title FROM resources WHERE url = '/syllabus'", one=True)["title"] == "Thirukkural Payilvom · Study material for the institution-level assessment"
        # a portal of before: the old title, not yet renamed; and one renamed in the Console, which keeps its name
        execute("UPDATE resources SET title = ? WHERE url = '/syllabus'", ("Thirukkural Payilvom · Syllabus for the institution-level assessment",))
        execute("DELETE FROM settings WHERE key = 'migrate.resource.study_material'")
    again = make_app(**{name: app.config[name] for name in ("INSTANCE_DIR", "DATABASE", "UPLOAD_DIR")})
    with again.app_context():
        assert query("SELECT title FROM resources WHERE url = '/syllabus'", one=True)["title"] == "Thirukkural Payilvom · Study material for the institution-level assessment"
        execute("UPDATE resources SET title = 'CICT study book' WHERE url = '/syllabus'")
        execute("DELETE FROM settings WHERE key = 'migrate.resource.study_material'")
    third = make_app(**{name: again.config[name] for name in ("INSTANCE_DIR", "DATABASE", "UPLOAD_DIR")})
    with third.app_context():
        assert query("SELECT title FROM resources WHERE url = '/syllabus'", one=True)["title"] == "CICT study book"

"""
The study books added on 10 November 2026 (1.2.169) from CICT's Drive folder "KTS 5.0 - Thirukkural Payilvom - Final Study
Materials": Bodo, Dogri, Kashmiri (in the Perso-Arabic script) and Punjabi - 22 books, every language of the portal but Sanskrit.

    python -m pytest tests/test_syllabus_1110.py -q
"""
import json
from pathlib import Path

from markupsafe import escape

from conftest import make_app

ROOT = Path(__file__).resolve().parents[1]
BOOKS = json.loads((ROOT / "data" / "syllabus.json").read_text(encoding="utf-8"))
# Dogri: the edition of 12 November 2026, 77 pages (1.2.181)
NEW = {"brx": (68, "", "(Bodo)"), "doi": (77, "डॉ. सुषमा रानी राजपूत", "(DOGRI)"), "ks": (62, "ڈاکٹر زرگر عادل احمد", "(Kashmiri)"),
       "pa": (65, "ਸੁਖਦੀਪ ਸੌਂਧੀ", "(Punjabi)")}


def _page(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def test_the_four_books():
    import fitz
    from kts import kural as K
    by_lang = {b["lang"]: b for b in BOOKS}
    assert len(BOOKS) == 22 and set(K.ORIENTATION_LANGS) - set(by_lang) == {"sa"}
    for lang, (pages, translator, cover_name) in NEW.items():
        b = by_lang[lang]
        assert (b["pages"], b["translator"]) == (pages, translator), lang
        pdf = ROOT / "static" / "syllabus" / f"KTS5-Thirukkural-Payilvom-{lang}.pdf"
        doc = fitz.open(pdf)
        assert doc.page_count == pages and cover_name in doc[0].get_text() and "Translator" in doc[0].get_text(), lang
        # nothing active in the file: no script, no action on opening, no launch, no embedded file
        for xref in range(1, doc.xref_length()):
            obj = doc.xref_object(xref, compressed=True)
            for key in ("/JS", "/JavaScript", "/OpenAction", "/AA", "/Launch", "/EmbeddedFile", "/RichMedia", "/SubmitForm"):
                at = obj.find(key)
                assert at == -1 or obj[at + len(key):at + len(key) + 1].isalnum(), (lang, xref, key)
        doc.close()
    # the script of the Kashmiri book, which is not that of the portal's own Kashmiri Thirukkural
    assert by_lang["ks"]["script"] == "ksn" and not any("script" in b for b in BOOKS if b["lang"] != "ks")


def test_the_page():
    from kts.i18n import CATALOG
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = _page(client, "/syllabus?lang=en")
    books = page[page.index('id="books"'):]
    assert books.count('class="card syl-book"') == 22
    # the Kashmiri book by its script: Perso-Arabic, not Devanagari
    ks = books[books.index('id="book-ks"'):books.index('id="book-kok"')]
    assert 'lang="ks-Arab"' in ks and "کٲشُر" in ks and "Kashmiri (Nastaliq)" in ks and "कॉशुर" not in ks
    assert "Translator: <bdi>ڈاکٹر زرگر عادل احمد</bdi>" in ks and "62 pages · PDF" in ks
    # the Bodo book names no translator, and is not called the original
    brx = books[books.index('id="book-brx"'):books.index('id="book-doi"')]
    assert "बड़ो" in brx and "Translator" not in brx and "The original, in Tamil" not in brx
    assert books.count("The original, in Tamil") == 1
    assert "Translator: <bdi>डॉ. सुषमा रानी राजपूत</bdi>" in books and "Translator: <bdi>ਸੁਖਦੀਪ ਸੌਂਧੀ</bdi>" in books
    # each of the four in its own language: framed, with the link to it; in Kashmiri the link names the book by its script
    for lang in NEW:
        own = _page(client, f"/syllabus?lang={lang}")
        assert f'<div class="card syl-book" id="book-{lang}"' in own and f'<a href="#book-{lang}">' in own, lang
        assert str(escape(CATALOG[lang]["syl.not_yet"])) not in own, lang
        assert f'href="/static/syllabus/KTS5-Thirukkural-Payilvom-{lang}.pdf" download' in own, lang
    assert '<span lang="ks-Arab">کٲشُر</span></a>' in _page(client, "/syllabus?lang=ks")
    # Sanskrit alone has no book yet; the two books to come stay announced
    assert str(escape(CATALOG["sa"]["syl.not_yet"])) in _page(client, "/syllabus?lang=sa")
    assert "Konkani (Devanagari script) and Manipuri (Meitei Mayek script) content will be added soon." in page
    for lang in NEW:
        r = client.get(f"/static/syllabus/KTS5-Thirukkural-Payilvom-{lang}.pdf")
        assert r.status_code == 200 and r.data[:5] == b"%PDF-", lang
        r.close()

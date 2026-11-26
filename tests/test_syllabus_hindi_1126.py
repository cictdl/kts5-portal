"""
The study book in Hindi: the corrected edition of 26 November 2026 (1.2.216). CICT, 26 November 2026, first of the card of the Hindi
book on the page of the study material ("हिन्दी · Hindi · Translator: डॉ. पि. सरस्वती · 103 pages · PDF · 1022 KB"): "remove",
"remove hindi only"; then, with the file "KTS5_CICT_Thirukkural Payilvom_Hindi_Correected version_26.11.2026.pdf": "add this
हिन्दी · Hindi"; and, with "KTS5_CICT_Thirukkural Payilvom_Hindi_26.11.2026.pdf": "add this pdf as final". The book here is that
final one.

The corrected book stands in the place of the book of 23 October 2026: the same name of the file, the same translator, 103 pages;
the cover of the list is made from its first page. It is the first of the 22 books, as before.

    python -m pytest tests/test_syllabus_hindi_1126.py -q
"""
import hashlib
import json
from pathlib import Path

from conftest import make_app

ROOT = Path(__file__).resolve().parent.parent
NAME = "KTS5-Thirukkural-Payilvom-hi"
PDF = ROOT / "static" / "syllabus" / f"{NAME}.pdf"
THUMB = ROOT / "static" / "syllabus" / "thumbs" / f"{NAME}.jpg"


def test_the_book_is_the_corrected_edition():
    import fitz
    data = PDF.read_bytes()
    assert len(data) == 1091811 and hashlib.sha256(data).hexdigest() == "cda6fd39f51715243d8d23ca1dee2cfb8f48f1ab482170c18846d477aab4aa33"
    doc = fitz.open(PDF)
    assert doc.page_count == 103 and not doc.is_encrypted and doc.embfile_count() == 0
    assert doc.metadata["creationDate"].startswith("D:20261126") and doc.metadata["author"] == "CICT"
    cover = doc[0].get_text()
    assert "(Hindi)" in cover and "Translator" in cover and "2026" in cover
    # the text of the final file can be read and searched: the title and the translator as they are printed
    assert "तिरुक्कुऱळ् पयिल्वोम्" in cover and "डॉ. पि.सरस्वती" in cover
    # nothing active in the file: no script, no action on opening, no launch, no embedded file, no link that leads away
    for xref in range(1, doc.xref_length()):
        obj = doc.xref_object(xref, compressed=True)
        for key in ("/JS", "/JavaScript", "/OpenAction", "/AA", "/Launch", "/EmbeddedFile", "/RichMedia", "/SubmitForm", "/URI"):
            at = obj.find(key)
            assert at == -1 or obj[at + len(key):at + len(key) + 1].isalnum(), (xref, key)
    assert not any(link.get("uri") for page in doc for link in page.get_links())
    doc.close()


def test_its_cover_in_the_list():
    from PIL import Image
    data = THUMB.read_bytes()
    assert data[:3] == b"\xff\xd8\xff" and 5_000 < len(data) < 60_000
    assert Image.open(THUMB).size == (360, 466)


def test_the_list_and_the_page():
    rows = json.loads((ROOT / "data" / "syllabus.json").read_text(encoding="utf-8"))
    assert len(rows) == 23 and rows[0] == {"lang": "hi", "pages": 103, "translator": "डॉ. पि. सरस्वती"}      # 23 with Sanskrit (1.2.219)
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/syllabus?lang=en").get_data(as_text=True)
    books = page[page.index('id="books"'):]
    assert books.count('class="card syl-book"') == 23
    card = books[books.index('id="book-hi"'):books.index('id="book-sa"')]            # the first book, before the Sanskrit one (1.2.219)
    assert "हिन्दी" in card and "Hindi" in card and "Translator: <bdi>डॉ. पि. सरस्वती</bdi>" in card
    assert "103 pages · PDF · 1066 KB" in card                                        # 1022 KB up to 1.2.215
    assert f'href="/static/syllabus/{NAME}.pdf" download' in card and f'src="/static/syllabus/thumbs/{NAME}.jpg"' in card
    # the file that the portal serves is the corrected one
    r = client.get(f"/static/syllabus/{NAME}.pdf")
    assert r.status_code == 200 and hashlib.sha256(r.data).hexdigest() == hashlib.sha256(PDF.read_bytes()).hexdigest()
    # a visitor in Hindi finds the book of his language framed, as before
    hindi = client.get("/syllabus?lang=hi").get_data(as_text=True)
    assert '<div class="card syl-book" id="book-hi" lang="hi" style="border:2px solid var(--saffron)">' in hindi

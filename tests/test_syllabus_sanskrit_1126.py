"""
The study book in Sanskrit (1.2.219). CICT, 26 November 2026, with the file "Thirukkural Payilvom_Sanskrit_26.11.2026.pdf": "add this".
The last language of the portal without a book: now 23 books, one in every language; the Sanskrit one second, after the Hindi one,
in the order CICT asked for (3 November 2026).

    python -m pytest tests/test_syllabus_sanskrit_1126.py -q
"""
import hashlib
import json
from pathlib import Path

from conftest import make_app

ROOT = Path(__file__).resolve().parent.parent
NAME = "KTS5-Thirukkural-Payilvom-sa"
PDF = ROOT / "static" / "syllabus" / f"{NAME}.pdf"
THUMB = ROOT / "static" / "syllabus" / "thumbs" / f"{NAME}.jpg"


def test_the_book():
    import fitz
    data = PDF.read_bytes()
    assert len(data) == 1007363 and hashlib.sha256(data).hexdigest() == "99269f5052e1b348e8d5363fab098be51659979334e2f24b97c714d034d9d9a5"
    doc = fitz.open(PDF)
    assert doc.page_count == 58 and not doc.is_encrypted and doc.embfile_count() == 0
    cover = doc[0].get_text()
    assert "(संस्कृतम्)" in cover and "Translator" in cover and "Dr. Bishnu pada pal" in cover and "2026" in cover
    assert "108." in doc[57].get_text()                               # the last of the 108 Thirukkural, on the last page
    for xref in range(1, doc.xref_length()):
        obj = doc.xref_object(xref, compressed=True)
        for key in ("/JS", "/JavaScript", "/OpenAction", "/AA", "/Launch", "/EmbeddedFile", "/RichMedia", "/SubmitForm", "/URI"):
            at = obj.find(key)
            assert at == -1 or obj[at + len(key):at + len(key) + 1].isalnum(), (xref, key)
    doc.close()
    thumb = THUMB.read_bytes()
    assert thumb[:3] == b"\xff\xd8\xff" and 5_000 < len(thumb) < 60_000


def test_the_list_and_the_page():
    from kts import kural as K
    rows = json.loads((ROOT / "data" / "syllabus.json").read_text(encoding="utf-8"))
    assert len(rows) == 23 and {r["lang"] for r in rows} == set(K.ORIENTATION_LANGS)
    assert rows[1] == {"lang": "sa", "pages": 58, "translator": "Dr. Bishnu pada pal"}
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/syllabus?lang=en").get_data(as_text=True)
    books = page[page.index('id="books"'):]
    assert books.count('class="card syl-book"') == 23
    card = books[books.index('id="book-sa"'):books.index('id="book-gu"')]
    assert "संस्कृतम्" in card and "Sanskrit" in card and "Translator: <bdi>Dr. Bishnu pada pal</bdi>" in card
    assert "58 pages · PDF · 983 KB" in card
    assert f'href="/static/syllabus/{NAME}.pdf" download' in card and f'src="/static/syllabus/thumbs/{NAME}.jpg"' in card
    assert books.index('id="book-hi"') < books.index('id="book-sa"') < books.index('id="book-gu"')
    r = client.get(f"/static/syllabus/{NAME}.pdf")
    assert r.status_code == 200 and r.data == PDF.read_bytes()
    # the assessment page names Sanskrit among the languages of the book, second
    exam = client.get("/examination?lang=en").get_data(as_text=True)
    langs = exam[exam.index('class="exam-syllabus"'):]
    langs = langs[:langs.index("</p>")]
    assert langs.index('<span lang="hi">') < langs.index('<span lang="sa">') < langs.index('<span lang="gu">')
    # the numbers of the portal count 23 books
    with client.application.test_request_context("/"):
        from kts import public
        assert len(public.syllabus_books()) == 23

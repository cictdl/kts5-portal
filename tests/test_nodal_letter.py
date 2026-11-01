"""
The sample letter of the Nodal Institution to its Participating Institutions (version 1.2.137): a Word file made by the portal
for any State/UT of Annexure-I in any of the 23 languages (/nodal-institutions/letter.docx), offered on the page of the Nodal
Institutions and in Console > Nodal officers; its texts nl.* in every language, the dates of the settings in the month names
of the language, the Nodal Officer from the account, the infographic made for each language (static/img/letter).

    python -m pytest tests -q
"""
import io
import re
import zipfile
from urllib.parse import quote

from conftest import ROOT, make_app
from test_nodal_access import _nodal
from test_public_fixes import _staff

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _letter(client, state, lang):
    r = client.get(f"/nodal-institutions/letter.docx?state={quote(state)}&lang={lang}")
    assert r.status_code == 200 and r.mimetype == DOCX, (state, lang, r.status_code)
    z = zipfile.ZipFile(io.BytesIO(r.data))
    return r, z, z.read("word/document.xml").decode("utf-8")


def _portal():
    from kts.db import execute, set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("reg.end", "2026-11-20")   # the tests' portal keeps registration open far ahead
    return app


def test_the_texts_in_every_language_with_their_placeholders():
    from kts.i18n import CATALOG
    keys = [k for k in CATALOG["en"] if k.startswith("nl.")]
    assert len(keys) == 81 and "nl.p1" in keys and "nl.art_c4" in keys
    for code, catalogue in CATALOG.items():
        for key in keys:
            value = catalogue.get(key)
            assert value and value.strip(), (code, key)
            assert sorted(re.findall(r"\{[a-z_]+\}", value)) == sorted(re.findall(r"\{[a-z_]+\}", CATALOG["en"][key])), (code, key)
            if code != "en":
                assert value != CATALOG["en"][key] or key in ("nl.ref",), (code, key)


def test_the_letter_of_tamil_nadu_in_english():
    from kts.db import execute
    app = _portal()
    _nodal(app, "nodal.tn@cutn.example", ["Tamil Nadu"])
    with app.app_context():
        execute("UPDATE users SET name = 'Dr. T. N. Officer', designation = 'Registrar', phone = '9444000001' WHERE email = 'nodal.tn@cutn.example'")
    client = app.test_client()
    r, z, doc = _letter(client, "Tamil Nadu", "en")
    assert r.headers["Content-Disposition"] == "attachment; filename=KTS5-letter-tamil-nadu-en.docx"
    assert {"[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml", "word/_rels/document.xml.rels",
            "word/media/lockup.png", "word/media/art.png"} <= set(z.namelist())
    assert z.read("word/media/art.png") == (ROOT / "static" / "img" / "letter" / "en.png").read_bytes()
    # the letterhead, the Nodal Officer, the row of Annexure-I and its number
    assert "CENTRAL UNIVERSITY OF TAMIL NADU" in doc and "Nodal Higher Educational Institution for Tamil Nadu and Andaman and Nicobar Islands" in doc
    assert "Dr. T. N. Officer, Nodal Officer · Registrar · nodal.tn@cutn.example · 9444000001" in doc
    assert "The Ministry has designated Central University of Tamil Nadu as the Nodal Higher Educational Institution for Tamil Nadu and Andaman and Nicobar Islands, to select 50 Participating Institutions" in doc
    # the dates of the settings, in words
    for when in ("Assess your students by 19 November 2026.", "Nominate one student on merit by 20 November 2026.", "Verification, 21 November – 5 December 2026.",
                 "28 November – 12 December 2026 at Varanasi", "The one-month research and academic engagement, 15 December 2026 – 14 January 2027.",
                 "an academic orientation by 14 December 2026", "By 14 January 2027 the article", "By 19 November 2026"):
        assert when in doc, when
    assert "kts.cict.in/institution/login" in doc and "kts.cict.in/static/KTS5-nomination-form.pdf" in doc and "youtu.be/" in doc
    assert "registrar@cict.in" in doc and "At a glance" in doc and "Yours faithfully," in doc and "Nodal Officer, KTS 5.0 – Tamil Nadu and Andaman and Nicobar Islands" in doc
    assert "<w:bidi/>" not in doc and "<w:rtl/>" not in doc and '<w:pageBreakBefore/>' in doc and doc.count("<w:tbl>") == 2
    assert "(Name of the Nodal Officer)" not in doc


def test_without_an_officer_and_in_tamil_and_urdu():
    from kts.db import set_setting
    from kts.i18n import text
    app = _portal()
    client = app.test_client()
    _r, _z, doc = _letter(client, "Kerala", "en")
    assert "(Name of the Nodal Officer), Nodal Officer · (Designation) · (e-mail) · (phone)" in doc and "Kerala and Lakshadweep" in doc
    assert "to select 21 Participating Institutions" in doc
    # an account exists but CICT keeps the officers off the public pages: blanks
    _nodal(app, "nodal.kl@cuk.example", ["Kerala"])
    with app.app_context():
        set_setting("nodal.officers_public", "0")
    _r, _z, doc = _letter(client, "Kerala", "en")
    assert "(Name of the Nodal Officer)" in doc and "nodal.kl@cuk.example" not in doc
    with app.app_context():
        set_setting("nodal.officers_public", "1")
    _r, _z, doc = _letter(client, "Kerala", "en")
    assert "nodal.kl@cuk.example" in doc
    # Tamil: the row of Annexure-I and the months in Tamil, the picture of the language
    r, z, doc = _letter(client, "Tamil Nadu", "ta")
    assert r.headers["Content-Disposition"].endswith("KTS5-letter-tamil-nadu-ta.docx")
    assert "தமிழ்நாடு மற்றும் அந்தமான் நிக்கோபார் தீவுகள்" in doc and f"19 {text('month.11', 'ta')} 2026" in doc
    assert z.read("word/media/art.png") == (ROOT / "static" / "img" / "letter" / "ta.png").read_bytes()
    assert 'w:cs="Nirmala UI"' in doc and "<w:bidi/>" not in doc
    # Urdu: right to left
    _r, z, doc = _letter(client, "Jammu and Kashmir", "ur")
    assert "<w:bidi/>" in doc and "<w:rtl/>" in doc and "<w:bidiVisual/>" in doc and 'w:cs="Segoe UI"' in doc
    assert z.read("word/media/art.png") == (ROOT / "static" / "img" / "letter" / "ur.png").read_bytes()


def test_only_the_rows_of_annexure_i_and_the_languages_of_the_portal():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for query in ("state=Lakshadweep&lang=en", "state=Atlantis&lang=en", "state=Tamil+Nadu&lang=xx", "lang=en"):
        assert client.get(f"/nodal-institutions/letter.docx?{query}").status_code == 404, query
    # no language given: the language of the visitor
    r = client.get("/nodal-institutions/letter.docx?state=Goa", headers={"Accept-Language": "en"})
    assert r.status_code == 200 and r.mimetype == DOCX


def test_the_pages_offer_it():
    from kts.i18n import CATALOG
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    page = client.get("/nodal-institutions?lang=en").get_data(as_text=True)
    assert "Sample letter to the Participating Institutions" in page and 'action="/nodal-institutions/letter.docx"' in page
    form = page[page.index('action="/nodal-institutions/letter.docx"'):page.index("</form>", page.index('action="/nodal-institutions/letter.docx"'))]
    assert form.count('<option value="') == 31 + len(CATALOG) and '<option value="Tamil Nadu">Tamil Nadu and Andaman and Nicobar Islands</option>' in form
    assert '<option value="ta" lang="ta" >தமிழ்' in form and '<option value="en" lang="en" selected>' in form
    assert "Download the sample letter (Word)" in form
    tamil = client.get("/nodal-institutions?lang=ta").get_data(as_text=True)
    assert CATALOG["ta"]["nl.page_title"] in tamil and '<option value="ta" lang="ta" selected>' in tamil
    admin = _staff(app, "admin@tests.example", "superadmin")
    console = admin.get("/console/nodal").get_data(as_text=True)
    assert 'href="/nodal-institutions/letter.docx?state=Kerala&amp;lang=en">Sample letter to the institutions (Word)</a>' in console


def test_the_pictures_of_the_23_languages():
    from kts.i18n import CATALOG
    for code in CATALOG:
        data = (ROOT / "static" / "img" / "letter" / f"{code}.png").read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n", code
        assert (int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")) == (2000, 1340), code
        assert 20_000 < len(data) < 900_000, (code, len(data))

"""
Posters and charts (version 1.2.67): four A3 PDFs on the Thirukkural in each of the 23 languages, under static/posters,
with a thumbnail each; the page /posters that offers them; the links from the programme page, the repository and the sitemap.

    python -m pytest tests -q
"""
from pathlib import Path

from conftest import make_app

ROOT = Path(__file__).resolve().parent.parent
POSTERS = ROOT / "static" / "posters"


def test_every_language_has_its_four_posters_and_they_are_light():
    from kts import kural as K
    total = 0
    for lang in K.ORIENTATION_LANGS:
        for n in range(1, 5):
            pdf = POSTERS / f"KTS5-poster-{n}-{lang}.pdf"
            thumb = POSTERS / "thumbs" / f"KTS5-poster-{n}-{lang}.jpg"
            assert pdf.is_file() and thumb.is_file(), (lang, n)
            size = pdf.stat().st_size
            assert 30_000 < size < 700_000, (lang, n, size)
            assert pdf.read_bytes()[:5] == b"%PDF-" and thumb.read_bytes()[:3] == b"\xff\xd8\xff"
            total += size
    assert total < 32_000_000


def test_the_page_offers_the_posters_of_the_language_chosen():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    r = client.get("/posters?lang=en")
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    assert "Posters and charts" in page and page.count("⬇ Download (PDF)") == 4
    for n in range(1, 5):
        assert f'href="/static/posters/KTS5-poster-{n}-en.pdf" download' in page and f"/static/posters/thumbs/KTS5-poster-{n}-en.jpg" in page
    assert "1 · Let us learn the Thirukkural" in page and "2 · Ten couplets on learning" in page and "4 · The Thirukkural at a glance" in page
    assert "A3 · print at 100%" in page and 'name="l"' in page
    assert page.split('id="l"')[1].split("</select>")[0].count("<option value=") == 23
    # the Tamil posters, asked for from the English interface; the interface language otherwise
    ta = client.get("/posters?l=ta&lang=en").get_data(as_text=True)
    assert "KTS5-poster-1-ta.pdf" in ta and "KTS5-poster-1-en.pdf" not in ta and '<option value="ta" lang="ta" selected>' in ta
    hi = client.get("/posters?lang=hi").get_data(as_text=True)
    assert "KTS5-poster-2-hi.pdf" in hi
    # a script variant of the interface takes the posters of its language; an unknown stream, English
    ks = client.get("/posters?l=ksn&lang=en").get_data(as_text=True)
    assert "KTS5-poster-1-ks.pdf" in ks and '<option value="ks" lang="ks-Arab" selected>کٲشُر · Kashmiri</option>' in ks
    assert '<option value="kok" lang="kok-Deva" >कोंकणी · Konkani</option>' in ks
    assert "KTS5-poster-1-en.pdf" in client.get("/posters?l=xx&lang=en").get_data(as_text=True)


def test_found_from_the_programme_page_the_repository_and_the_sitemap():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    prog = client.get("/programme?lang=en").get_data(as_text=True)
    assert 'href="/posters">⬇ Download the posters (PDF)</a>' in prog
    res = client.get("/resources?cat=poster&lang=en").get_data(as_text=True)
    assert "Posters and charts in 23 languages" in res and "Posters and charts · ★" in res
    from kts.db import query
    with app.app_context():
        rid = query("SELECT id FROM resources WHERE url = '/posters'", one=True)["id"]
    r = client.get(f"/resources/{rid}")
    assert r.status_code in (301, 302) and r.headers["Location"].endswith("/posters")
    assert "/posters" in client.get("/sitemap.xml").get_data(as_text=True)
    assert 'href="/posters">Posters and charts' in client.get("/sitemap?lang=en").get_data(as_text=True)


def test_the_language_of_the_posters_leaves_the_interface_language_alone():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    page = client.get("/posters?l=ks&lang=en").get_data(as_text=True)
    assert '<html lang="en" dir="ltr"' in page and "KTS5-poster-1-ks.pdf" in page
    menu = page.split('id="ui-lang"', 1)[1].split("</select>", 1)[0]
    assert '<option value="en" lang="en" selected>' in menu and '<option value="ks" lang="ks" selected>' not in menu

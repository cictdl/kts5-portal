"""
The Kural Journey Banners under Programme › Public displays (version 1.2.60): sample layouts of Thirukkural
banners for airports and railway stations, each a PDF with a preview, and one PDF with all of them.

    python -m pytest tests -q
"""
import json

from conftest import ROOT, make_app

DATA = json.loads((ROOT / "data" / "banners.json").read_text(encoding="utf-8"))
STATIC = ROOT / "static" / "banners"


def test_every_banner_has_its_print_file_and_its_preview():
    assert len(DATA["banners"]) == 10
    for b in DATA["banners"]:
        pdf, jpg = STATIC / b["file"], STATIC / b["thumb"]
        assert pdf.read_bytes()[:5] == b"%PDF-" and pdf.stat().st_size < 600_000, b["file"]
        assert jpg.read_bytes()[:3] == b"\xff\xd8\xff" and b["w"] == 640, b["thumb"]
        assert b["title"] and b["where"] and b["size"] and b["place"]
    every = STATIC / DATA["all"]
    assert every.read_bytes()[:5] == b"%PDF-" and every.stat().st_size < 2_000_000
    # nothing else in the folder
    assert {p.name for p in STATIC.iterdir()} == {DATA["all"]} | {b["file"] for b in DATA["banners"]} | {b["thumb"] for b in DATA["banners"]}


def test_the_programme_page_offers_them_under_public_displays():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    page = client.get("/programme?lang=en").get_data(as_text=True)
    card = page.split("Public displays</h3>")[1].split("</div>")[0]
    assert 'href="#banners">⬇ Kural Journey Banners</a>' in card
    section = page.split('id="banners"')[1].split('<h2')[0]
    assert "Kural Journey Banners: the Thirukkural at airports and railway stations" in section
    assert f'href="/static/banners/{DATA["all"]}" download>⬇ Download all the banners (PDF)</a>' in section
    assert section.count('<figure class="card banner-card"') == 10 and section.count(">⬇ Download PDF</a>") == 10
    assert 'alt="Welcome hoarding"' in section and "Kural 84" in section
    for b in DATA["banners"]:
        assert client.get(f"/static/banners/{b['file']}").status_code == 200
    assert client.get("/programme?lang=ta").status_code == 200

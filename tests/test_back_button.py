"""
A Back button on every page but the home page, in the Console too, and the participating institutions as prominently
on the home page as the list of Nodal HEIs (version 1.2.77).

    python -m pytest tests -q
"""
from pathlib import Path

from markupsafe import escape

from conftest import make_app
from test_public_fixes import _staff

ROOT = Path(__file__).resolve().parents[1]
PAGES = ("/about", "/programme", "/schedule", "/institutions", "/nodal-institutions", "/resources", "/orientation",
         "/practice", "/examination", "/how-to-take-part", "/notices", "/thirukkural/1", "/thirukkural-108", "/posters",
         "/register", "/status", "/contact", "/gallery", "/partners")


def test_every_page_but_the_home_page_has_a_back_button():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    assert "data-back" not in client.get("/?lang=en").get_data(as_text=True)
    for path in PAGES:
        page = client.get(f"{path}?lang=en").get_data(as_text=True)
        assert '<a class="back-link" href="/" data-back><span aria-hidden="true">←</span> Back</a>' in page, path
    # in the language of the page, the arrow following the direction of reading
    from kts.i18n import CATALOG
    for code, catalogue in CATALOG.items():
        page = client.get(f"/schedule?lang={code}").get_data(as_text=True)
        arrow = "→" if code in ("ur", "ks", "sd") and 'dir="rtl"' in page else "←"
        assert f'<span aria-hidden="true">{arrow}</span> {escape(catalogue["common.back"])}</a>' in page, code


def test_the_console_has_a_back_button_too():
    app = make_app()
    client = _staff(app, "root@tests.example", "superadmin")
    assert "data-back" not in client.get("/console/").get_data(as_text=True)
    page = client.get("/console/applications").get_data(as_text=True)
    assert '<a class="back-link" href="/console/" data-back><span aria-hidden="true">←</span> Back</a>' in page


def test_the_back_button_goes_back_within_the_portal_only():
    js = (ROOT / "static" / "js" / "portal.js").read_text(encoding="utf-8")
    block = js[js.index("// The Back button (1.2.77)"):]
    assert 'document.querySelectorAll("[data-back]")' in block
    assert 'ref.indexOf(location.origin + "/") === 0' in block and "history.back()" in block
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    assert "@media print { .back-row, .back-link { display: none !important; } }" in css


def test_the_participating_institutions_on_the_home_page():
    from kts.i18n import CATALOG
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    for code, catalogue in CATALOG.items():
        page = client.get(f"/?lang={code}").get_data(as_text=True)
        band = page[page.index('<div class="nodal-attention">'):page.index('<section class="hero">')]
        assert '<a class="na-link" href="/nodal-institutions">' in band, code
        assert f'<a class="na-btn" href="/institutions"><span aria-hidden="true">🏛️ </span>{escape(catalogue["nav.institutions"])} ' in band, code
    assert client.get("/institutions?lang=en").status_code == 200

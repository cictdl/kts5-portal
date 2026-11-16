"""
The logo of the Government of India changed (1.2.196). CICT, 16 November 2026: "change the logo", with the picture - the State
Emblem and "भारत सरकार / GOVERNMENT OF INDIA" in black, with a black bar - for the one with the tricolour bar and "INDIA" in
colours. The same file name, so every page that showed the logo shows the new one: the masthead, the band of the logos over the
footer, the page of the launch and the display screen.

    python -m pytest tests/test_goi_logo_1116.py -q
"""
from conftest import ROOT, make_app

LOGO = ROOT / "static" / "img" / "logos" / "goi.png"


def test_the_file_is_the_black_logo_on_a_clear_ground():
    from PIL import Image
    im = Image.open(LOGO)
    assert im.format == "PNG" and im.size == (988, 440)      # twice 494 x 220: the proportions the pages give the logo
    rgba = im.convert("RGBA")
    # black only: no saffron, green or blue of the logo before
    assert {c[:3] for _n, c in rgba.getcolors(maxcolors=1 << 16) if c[3]} == {(0, 0, 0)}
    # the ground is clear, and most of the picture is ground
    assert all(rgba.getpixel(p)[3] == 0 for p in ((0, 0), (987, 0), (0, 439), (987, 439), (270, 220)))
    alpha = rgba.getchannel("A")
    assert alpha.getextrema() == (0, 255)
    inked = sum(n for n, a in alpha.getcolors() if a > 127) / (988 * 440)
    assert 0.20 < inked < 0.45, inked
    # the drawing fills the width and stands in the middle of the height
    left, top, right, bottom = alpha.getbbox()
    assert (left, right) == (0, 988) and 0 < top < 20 and 420 < bottom < 440
    assert LOGO.stat().st_size < 60_000      # it is on every page


def test_the_pages_show_it():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/?lang=en").get_data(as_text=True)
    assert '<img class="gov-logo goi" src="/static/img/logos/goi.png" alt="Government of India" height="54">' in page
    band = page[page.index('<section class="logo-band"'):]
    assert '<img src="/static/img/logos/goi.png" alt="Government of India">' in band
    r = client.get("/static/img/logos/goi.png")
    assert r.status_code == 200 and r.mimetype == "image/png" and r.data == LOGO.read_bytes()
    r.close()

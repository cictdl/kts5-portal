"""
The photographs of the release of the Thirukkural in 50 languages on the home page (1.2.238). CICT, 28 November 2026: "Paste in
picture on the Home page with caption. 50 Thirukkural translations released on 28 November 2026 at KTS 5.0 at Varanasi.", twice,
with a photograph each time. The two photographs as CICT sent them (only the tag of Facebook taken out), side by side under the bands
at the top of the home page, the caption under them in CICT's words, while the Console's switch home.photo shows them.

    python -m pytest tests/test_home_photo_1128.py -q
"""
import json
import re

from conftest import ROOT, make_app
from test_reserve_1111 import LANGS

CAPTION = "50 Thirukkural translations released on 28 November 2026 at KTS 5.0 at Varanasi."
FILES = ["img/home/kts5-thirukkural-50-languages-2026-11-28.jpg", "img/home/kts5-inauguration-kural-391-2026-11-28.jpg"]


def _block(page):
    if '<section class="home-photo"' not in page:
        return None
    start = page.index('<section class="home-photo"')
    return page[start:page.index("</section>", start)]


def test_the_photographs_and_their_data():
    from PIL import Image
    data = json.loads((ROOT / "data" / "home_photo.json").read_text(encoding="utf-8"))
    assert data["caption"] == CAPTION and data["date"] == "2026-11-28"
    assert [p["file"] for p in data["photos"]] == FILES
    assert "Thirukkural · 50 languages" in data["photos"][0]["alt"] and "couplet 391 of the Thirukkural" in data["photos"][1]["alt"]
    for p in data["photos"]:
        assert "Varanasi" in p["alt"]
        raw = (ROOT / "static" / p["file"]).read_bytes()
        assert raw[:3] == b"\xff\xd8\xff" and len(raw) < 200_000
        assert b"Exif" not in raw and b"Photoshop" not in raw and b"FBMD" not in raw and b"XMP" not in raw   # no tags of the source
        with Image.open(ROOT / "static" / p["file"]) as im:
            assert im.format == "JPEG" and im.size == (p["width"], p["height"]) == (1188, 792)
    assert sorted(p.name for p in (ROOT / "static" / "img" / "home").iterdir()) == sorted(f.rsplit("/", 1)[1] for f in FILES)


def test_on_the_home_page_under_the_bands():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/?lang=en").get_data(as_text=True)
    block = _block(page)
    assert block is not None
    imgs = re.findall(r'<img src="([^"]+)" alt="([^"]+)" width="1188" height="792" lang="en" style="([^"]+)">', block)
    assert [i[0] for i in imgs] == [f"/static/{f}" for f in FILES]                     # the 50 languages first
    assert "Thirukkural · 50 languages" in imgs[0][1] and "couplet 391" in imgs[1][1]
    assert all("width:100%;height:auto" in i[2] for i in imgs)
    # side by side, one above the other where there is no room for two of 300 pixels
    assert 'style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:12px"' in block
    assert (f'<figcaption id="home-photo-cap" lang="en" dir="ltr" style="margin-top:10px;font-weight:800;font-size:1.2rem;'
            f'line-height:1.4;text-align:center">{CAPTION}</figcaption>') in block
    assert block.count("<figcaption") == 1 and 'aria-labelledby="home-photo-cap"' in block and "max-width:1100px" in block
    # under the bands at the top (the press release, the circular, the lectures, the quiz), above the quick links and the hero
    at = [page.index(mark) for mark in ('class="pib-band"', 'class="nodal-attention"', 'class="home-photo"', 'class="quick-links"',
                                        'class="hero"')]
    assert at == sorted(at)
    for f in FILES:
        r = client.get(f"/static/{f}")
        assert r.status_code == 200 and r.mimetype == "image/jpeg"
    # the caption in CICT's words on the page of every language
    for code in LANGS:
        other = _block(client.get(f"/?lang={code}").get_data(as_text=True))
        assert other is not None and CAPTION in other and all(f'src="/static/{f}"' in other for f in FILES), code
    # on the home page only
    assert _block(client.get("/programme?lang=en").get_data(as_text=True)) is None


def test_the_switch_of_the_console():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS, set_setting
    assert DEFAULT_SETTINGS["home.photo"] == "1"
    site = {k: (label, kind) for k, label, kind in dict(SETTING_GROUPS)["Site"]}
    assert site["home.photo"][1] == "bool" and site["home.photo"][0].startswith("Show the photographs of the release of the Thirukkural")
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    assert _block(client.get("/?lang=en").get_data(as_text=True)) is not None
    with app.app_context():
        set_setting("home.photo", "0")
    page = client.get("/?lang=en").get_data(as_text=True)
    assert _block(page) is None and not any(f in page for f in FILES) and '<div class="pib-band"' in page
    with app.app_context():
        set_setting("home.photo", "1")
    assert _block(client.get("/?lang=en").get_data(as_text=True)) is not None

"""
The home page carries, above the hero, a band for the attention of all: the State/UT-wise list of Nodal Higher
Educational Institutions, linking to /nodal-institutions, in every language (version 1.2.74).

    python -m pytest tests -q
"""
from pathlib import Path

from markupsafe import escape

from conftest import make_app

ROOT = Path(__file__).resolve().parents[1]


def test_the_home_page_points_everyone_to_the_nodal_institutions():
    from kts.i18n import CATALOG
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    for code, catalogue in CATALOG.items():
        page = client.get(f"/?lang={code}").get_data(as_text=True)
        band = page.index('<div class="nodal-attention">')
        assert band < page.index('<section class="hero">'), code
        block = page[band:page.index('<section class="hero">')]
        assert '<a class="na-link" href="/nodal-institutions">' in block, code
        assert f'<span class="na-title">{escape(catalogue["nodal.title"])}</span>' in block, code
        assert str(escape(catalogue["tag.circular"])) in block, code
    page = client.get("/?lang=en").get_data(as_text=True)
    assert "State/UT-wise list of Nodal Higher Educational Institutions" in page
    assert client.get("/nodal-institutions?lang=en").status_code == 200


def test_the_band_is_plain_and_its_new_blinks_only_for_those_who_allow_movement():
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8").replace("\r\n", "\n")
    band = css[css.index(".nodal-attention {"):css.index(".btn.saffron:hover")]
    # a plain band since 1.2.152 (CICT: "should not be highlighted with red background ... keep simple background"), in both themes
    assert ".nodal-attention { background: var(--surface);" in band and "#8f1d17" not in band and "linear-gradient" not in band
    # the NEW beside "Circular" blinks continuously (1.2.153; five times in 1.2.152), not at all for those who ask for reduced motion
    assert "@media (prefers-reduced-motion: no-preference) {\n  .new-badge { animation: new-blink 1s steps(1, end) .3s infinite; }\n}" in band
    assert "new-blink-again" not in band

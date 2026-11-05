"""
The band at the top on a phone (1.2.160): the button of the band ("Register your institution →") may break into two lines on a
narrow screen. Kept on one line, in Tamil (and other long languages) it was wider than a 375-390 px phone, and every page scrolled
sideways (found on 5 November 2026; CICT: "yes fix it").

    python -m pytest tests/test_banner_wrap_1105.py -q
"""
import re
from pathlib import Path

from conftest import make_app

ROOT = Path(__file__).resolve().parents[1]


def test_the_button_of_the_band_wraps_on_a_phone():
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    phone = re.search(r"@media \(max-width: 599px\) \{ \.banner\.reg-open \{[^}]*\}(.*?)\n", css).group(1)
    rule = re.search(r"\.banner\.reg-open \.banner-go \{([^}]*)\}", phone).group(1)
    assert "white-space: normal" in rule and "max-width: 100%" in rule
    # on a wider screen it stays on one line
    assert re.search(r"\.banner\.reg-open \.banner-go \{[^}]*white-space: nowrap", css)
    # the name of the source on a card of the news, on a phone of 320 px
    assert "@media (max-width: 599px) { .news-day .pill { white-space: normal; } }" in css
    # long words in narrow boxes break rather than push the page sideways
    assert ".quick-links .ql > span:last-child { min-width: 0; overflow-wrap: anywhere; }" in css
    # the quick links and the steps in one column on a phone, after the rule of 599 px so that it wins
    one = "@media (max-width: 479px) { .quick-links .ql-grid, .steps { grid-template-columns: minmax(0, 1fr); } }"
    assert one in css and css.index(one) > css.index(".steps { grid-template-columns: repeat(2, minmax(0, 1fr)); }")
    assert ".step, .pi .pi-kpi .lbl { overflow-wrap: anywhere; }" in css and ".num-visit { max-width: 100%; }" in css


def test_the_pages_ask_for_the_new_stylesheet():
    page = make_app(ADMIN_PASSWORD=None).test_client().get("/in-the-news?lang=ta").get_data(as_text=True)
    assert '<link rel="stylesheet" href="/static/css/portal.css?v=49">' in page

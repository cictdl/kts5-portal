"""
The Academic Orientation in seven more languages (1.2.228). CICT, 26 November 2026: "The 108 Thirukkural · Video lectures - CICT |
KTS 5.O | Thirukkural Payilvom - 108 Thirukkural from https://www.youtube.com/@CICT_Online". The four lectures of CICT (CICT Chennai)
in Bengali, Gujarati, Kannada, Marathi, Odia, Telugu and Urdu, each card with its own videos in the order of the sessions.

    python -m pytest tests/test_academic_more_1126.py -q
"""
import re

from conftest import make_app

NEW = {
    "bn": ["_DP1UJFAX8Q", "jUfR5EDEbNc", "0ms9qFOo_eU", "OZ7dsc1irPQ"],
    "gu": ["--3VQe3qpBU", "UtDze4u_VwY", "nwxXnghfykc", "o-U-lhV42Oo"],
    "kn": ["J_CYsG6IVvw", "OMYKe2zjaCc", "gCt-7i620Dw", "xNO590GVM9M"],
    "mr": ["foMhnqDJvCo", "IdfNRSrzwbg", "Xpbtg7fIG-k", "FjmiNWOEBYI"],
    "or": ["NM_VzdVcu3Y", "pBvAN2E7va0", "PO8SJBVX0SY", "TbLfLfohpjE"],
    "te": ["Th9l2vCuNDU", "mqsFUAN8SY8", "XCnjcbSOPyw", "E235jGsxGWA"],
    "ur": ["RN0dztG-FAs", "Wl-XKzxREu0", "UvrG7BiEAt0", "TLh_P8WDK1c"],
}


def test_the_cards_of_the_seven_languages():
    from kts.i18n import LANG_INFO
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for ui in ("en", "ta", "ur"):
        page = client.get(f"/academic-orientation?lang={ui}").get_data(as_text=True)
        main = page[page.index("<main"):page.index("</main>")]
        cards = re.findall(r'<div class="card acad-lang" id="acad-([a-z]+)">', main)
        for code, ids in NEW.items():
            at = main.index(f'id="acad-{code}"')
            following = [main.index(f'id="acad-{c}"') for c in cards if main.index(f'id="acad-{c}"') > at]
            card = main[at:min(following) if following else len(main)]
            assert re.findall(r'href="https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})"', card) == ids
            assert f'<bdi lang="{code}">{LANG_INFO[code]["native"]}</bdi>' in card
            assert [m for m in re.findall(r'<bdi dir="ltr">(\d+–\d+)</bdi>', card)] == ["1–27", "28–54", "55–81", "82–108"]


def test_the_band_of_the_home_page():
    from kts.i18n import LANG_INFO
    page = make_app(ADMIN_PASSWORD=None).test_client().get("/?lang=en").get_data(as_text=True)
    band = page[page.index('<div class="acad-band"'):page.index('<nav class="quick-links"')]
    for code in NEW:
        assert f'<bdi lang="{code}">{LANG_INFO[code]["native"]}</bdi>' in band

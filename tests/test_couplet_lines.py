"""
A couplet keeps its two lines whole (version 1.2.58): four words, then three, each line on one line of its
own; the script makes the type smaller when a line would not fit, never breaks it.

    python -m pytest tests -q
"""
import re

from conftest import ROOT, make_app


def _couplet(page, cls):
    m = re.search(rf'<div class="{cls} ta couplet" dir="ltr" lang="ta"><span>([^<]+)</span><span>([^<]+)</span></div>', page)
    assert m, cls
    return m.group(1), m.group(2)


def test_the_couplet_pages_keep_the_two_lines_whole():
    from kts import kural as K
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    one = client.get("/thirukkural/391?lang=en").get_data(as_text=True)
    assert _couplet(one, "big-kural") == ("கற்க கசடறக் கற்பவை கற்றபின்", "நிற்க அதற்குத் தக.")
    assert [len(x.split()) for x in _couplet(one, "big-kural")] == [4, 3]
    with app.app_context():
        today = K.daily()
    home = client.get("/?lang=en").get_data(as_text=True)
    assert _couplet(home, "tamil") == tuple(K.lines(today, "ta"))
    # the portrait stands beside the label, so the couplet has the whole width of the card
    head = re.search(r'<div class="kc-head">(.*?)<div class="tamil ta couplet"', home, re.S).group(1)
    assert 'class="label"' in head and 'class="avatar"' in head
    daily = client.get("/daily-kural?lang=en").get_data(as_text=True)
    assert _couplet(daily, "big-kural")
    chapter = client.get("/thirukkural?lang=en").get_data(as_text=True)
    assert chapter.count('class="tamil ta couplet"') == 10
    for page in (one, home, daily, chapter):
        assert not re.search(r'lang="ta">[^<]+<br>', page)


def test_the_style_and_the_script():
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    assert ".couplet > span { display: block; white-space: nowrap; }" in css
    js = (ROOT / "static" / "js" / "portal.js").read_text(encoding="utf-8")
    assert 'document.querySelectorAll(".couplet")' in js and "Math.max(11," in js and "document.fonts.ready.then(fitCouplets)" in js

"""
LIVE: Inauguration of Kashi Tamil Sangamam 5.0 on the home page (1.2.233). CICT, 28 November 2026: "https://www.youtube.com/watch?v=
AiCjCUD29Ng give a link on the home page LIVE: Inauguration of Kashi Tamil Sangamam 5.0", then "https://www.youtube.com/
watch?v=0bV8uPVhtbg this link also" (Doordarshan National). A band of its own at the very top - deep
red, large bold white letters, a blinking LIVE - that opens the stream on YouTube in a new tab, up to 28 November 2026, 6:00 PM IST,
while the Console's switch home.live shows it.

    python -m pytest tests/test_live_band_1128.py -q
"""
import re
from datetime import datetime

from conftest import ROOT, make_app
from test_quiz_band_1125 import _contrast
from test_reserve_1111 import LANGS

URL = "https://www.youtube.com/watch?v=AiCjCUD29Ng"
URL_DD = "https://www.youtube.com/watch?v=0bV8uPVhtbg"


def _at(monkeypatch, moment):
    """The clock of the public pages at that moment (IST)."""
    from kts import public
    when = datetime.fromisoformat(moment + "+05:30")
    monkeypatch.setattr(public, "now_ist", lambda: when)


def _band(page):
    if '<div class="live-band"' not in page:
        return None
    return page[page.index('<div class="live-band"'):page.index('<div class="nodal-attention">')]


def test_the_band_on_the_home_page(monkeypatch):
    from kts.public import LIVE_STREAMS, LIVE_UNTIL, LIVE_URL
    assert LIVE_URL == URL and LIVE_UNTIL == "2026-11-28T18:00"
    assert LIVE_STREAMS == (("Ministry of Education", URL), ("DD National", URL_DD))
    _at(monkeypatch, "2026-11-28T11:05:00")
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/?lang=en").get_data(as_text=True)
    band = _band(page)
    assert band is not None
    # "LIVE: Inauguration of Kashi Tamil Sangamam 5.0", large and bold, opening the stream on YouTube in a new tab
    link = re.search(r'<a class="live-link" href="([^"]+)" target="_blank" rel="noopener" style="([^"]+)">(.*?)</a>', band, flags=re.S)
    assert link and link.group(1) == URL and "color:#fff;font-weight:800;font-size:1.4rem" in link.group(2)
    assert link.group(3) == ('<span class="new-badge" lang="en">LIVE</span><span class="visually-hidden" lang="en">:</span> '
                             'Inauguration of Kashi Tamil Sangamam 5.0 <span aria-hidden="true">↗</span>')
    words = re.sub(r"<[^>]+>", "", link.group(3))
    assert words == "LIVE: Inauguration of Kashi Tamil Sangamam 5.0 ↗"
    # beside it a link to each of the two streams: the Ministry's and Doordarshan National's ("this link also")
    streams = re.findall(r'<a class="live-on" href="([^"]+)" target="_blank" rel="noopener" lang="en" dir="ltr" style="[^"]+">'
                         r'<span aria-hidden="true">▶ </span>YouTube · ([^<]+) <span aria-hidden="true">↗</span></a>', band)
    assert streams == [(URL, "Ministry of Education"), (URL_DD, "DD National")]
    # nothing of YouTube on the portal: links, no frame
    assert "<iframe" not in page and "youtube-nocookie" not in page and page.count(f'href="{URL}"') == 2 and page.count(f'href="{URL_DD}"') == 1
    # deep red, on which the white of the link and the gold of "YouTube" are read with ease
    assert "background:linear-gradient(90deg,#7a0000,#a30000)" in band
    assert _contrast("#ffffff", "#a30000") > 7 and _contrast("#ffd166", "#a30000") > 4.5
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    assert ".live-band a:focus-visible { outline: 3px solid #fff; outline-offset: 3px; border-radius: 2px; }" in css
    assert '<link rel="stylesheet" href="/static/css/portal.css?v=59">' in page and "<style" not in page
    # the very first, above the band of the press release, the circular band and the hero
    at = [page.index(mark) for mark in ('class="live-band"', 'class="pib-band"', 'class="nodal-attention"', 'class="acad-band"',
                                        'class="quick-links"', 'class="hero"')]
    assert at == sorted(at) and page.index('class="live-band"') > page.index("<main")
    # in the other languages the name of the inauguration in the language of the page
    from kts.i18n import CATALOG
    for code in LANGS:
        other = _band(client.get(f"/?lang={code}").get_data(as_text=True))
        assert other is not None and f'href="{URL}"' in other, code
        assert str(CATALOG[code]["timeline.inauguration"]).replace("'", "&#39;") in other, code
    # on the home page only
    assert _band(client.get("/programme?lang=en").get_data(as_text=True)) is None


def test_up_to_6_pm_on_28_november(monkeypatch):
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for moment, shown in (("2026-11-28T09:00:00", True), ("2026-11-28T11:00:00", True), ("2026-11-28T18:00:00", True),
                          ("2026-11-28T18:01:00", False), ("2026-11-29T10:00:00", False)):
        _at(monkeypatch, moment)
        assert (_band(client.get("/?lang=en").get_data(as_text=True)) is not None) is shown, moment


def test_the_console_takes_it_off(monkeypatch):
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS, set_setting
    assert DEFAULT_SETTINGS["home.live"] == "1"
    site = {k: kind for k, _label, kind in dict(SETTING_GROUPS)["Site"]}
    assert site["home.live"] == "bool"
    _at(monkeypatch, "2026-11-28T11:05:00")
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    with app.app_context():
        set_setting("home.live", "0")
    page = client.get("/?lang=en").get_data(as_text=True)
    assert _band(page) is None and URL not in page and URL_DD not in page and '<div class="pib-band"' in page
    with app.app_context():
        set_setting("home.live", "1")
    assert _band(client.get("/?lang=en").get_data(as_text=True)) is not None

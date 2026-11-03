"""
The home page of 3 November 2026 (version 1.2.145): CICT's banner of KTS 5.0 before the Kural of the day; "Apply now" at the top
right of every page leading to "Register your institution" while the registration of institutions is open; the video guide off
the home page (tests/test_guide_videos.py).

    python -m pytest tests -q
"""
from PIL import Image

from conftest import ROOT, make_app


def _page(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def _app(hei_open="1", hei_end="2099-12-31"):
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("hei.open", hei_open)
        set_setting("hei.end", hei_end)
    return app


def test_the_banner_files():
    for px in (720, 1080):
        path = ROOT / "static" / "img" / "banner" / f"kts5-banner-ta-{px}.jpg"
        with Image.open(path) as im:
            assert im.format == "JPEG" and im.size == (px, px) and not im.info.get("exif"), path
        assert path.stat().st_size < 400_000, path


def test_the_banner_before_the_kural_of_the_day():
    client = _app().test_client()
    for lang in ("en", "ta", "hi", "ur"):
        page = _page(client, f"/?lang={lang}")
        hero = page[page.index('<section class="hero">'):page.index('<section class="hub-section"')]
        assert hero.index('<div class="hero-side">') < hero.index('class="home-banner no-print"') < hero.index('<aside class="kural-card">'), lang
        banner = hero[hero.index('class="home-banner no-print"'):hero.index('<aside class="kural-card">')]
        assert 'href="/institutions/register"' in banner, lang
        assert 'src="/static/img/banner/kts5-banner-ta-1080.jpg"' in banner and "/static/img/banner/kts5-banner-ta-720.jpg 720w" in banner
        assert 'width="1080" height="1080"' in banner and 'lang="ta"' in banner and "1000 பயிற்சி பணி வாய்ப்புகள்" in banner
        assert "₹10,000" in banner and "kts.cict.in" in banner
    # once the registration of institutions has ended, the banner opens itself
    page = _page(_app(hei_end="2020-01-01").test_client(), "/?lang=en")
    banner = page[page.index('class="home-banner no-print"'):page.index('<aside class="kural-card">')]
    assert 'href="/static/img/banner/kts5-banner-ta-1080.jpg"' in banner and "/institutions/register" not in banner


def test_apply_now_leads_to_the_registration_of_institutions():
    client = _app().test_client()
    for path in ("/?lang=en", "/about?lang=en", "/syllabus?lang=hi"):
        page = _page(client, path)
        assert '<a class="btn saffron cta" href="/institutions/register">' in page, path
    assert '<a class="btn saffron cta" href="/institutions/register">Apply now</a>' in _page(client, "/?lang=en")
    # while it is not open: the students' registration, as before
    for app in (_app(hei_open="0"), _app(hei_end="2020-01-01")):
        assert '<a class="btn saffron cta" href="/register">Apply now</a>' in _page(app.test_client(), "/?lang=en")


def test_no_video_guide_on_the_home_page():
    client = _app().test_client()
    home = _page(client, "/?lang=en")
    assert "video-guide" not in home and "gv-btn" not in home and "gv-home" not in home
    # the hub's video buttons lead to the institutions' part of "How to take part"
    assert home.count('<a class="btn ghost" href="/how-to-take-part#institutions">▶ Part 2: For Participating Institutions</a>') == 1
    guide = _page(client, "/how-to-take-part?lang=en")
    assert 'id="institutions"' in guide and 'id="video-guide"' in guide

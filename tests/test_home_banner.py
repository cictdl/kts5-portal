"""
The home page of 3 November 2026 (version 1.2.145): CICT's banner of KTS 5.0 before the Kural of the day (in English since
1.2.146, in Tamil for those reading the portal in Tamil); "Apply now" at the top
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
    for lang, size in (("ta", {720: (720, 720), 1080: (1080, 1080)}), ("en", {720: (720, 764), 1080: (1080, 1146)})):
        for px in (720, 1080):
            path = ROOT / "static" / "img" / "banner" / f"kts5-banner-{lang}-{px}.jpg"
            with Image.open(path) as im:
                assert im.format == "JPEG" and im.size == size[px] and not im.info.get("exif"), path
            assert path.stat().st_size < 400_000, path
    from kts.public import HOME_BANNERS
    assert {k: v["size"] for k, v in HOME_BANNERS.items()} == {"en": (1080, 1146), "ta": (1080, 1080)}


def test_the_banner_before_the_kural_of_the_day():
    client = _app().test_client()
    for lang in ("en", "ta", "hi", "ur"):
        page = _page(client, f"/?lang={lang}")
        hero = page[page.index('<section class="hero">'):page.index("</aside>", page.index('<section class="hero">'))]
        assert hero.index('<div class="hero-side">') < hero.index('class="home-banner no-print"') < hero.index('<aside class="kural-card">'), lang
        banner = hero[hero.index('class="home-banner no-print"'):hero.index('<aside class="kural-card">')]
        assert 'href="/institutions/register"' in banner, lang
        assert "₹10,000" in banner and "kts.cict.in" in banner
        if lang == "ta":   # the Tamil banner for those reading the portal in Tamil
            assert 'src="/static/img/banner/kts5-banner-ta-1080.jpg"' in banner and "/static/img/banner/kts5-banner-ta-720.jpg 720w" in banner
            assert 'width="1080" height="1080"' in banner and 'lang="ta"' in banner and "1000 பயிற்சி பணி வாய்ப்புகள்" in banner
        else:   # the English one for every other language (1.2.146)
            assert 'src="/static/img/banner/kts5-banner-en-1080.jpg"' in banner and "/static/img/banner/kts5-banner-en-720.jpg 720w" in banner, lang
            assert 'width="1080" height="1146"' in banner and 'lang="en"' in banner and "1000 internships for students of higher education" in banner
    # once the registration of institutions has ended, the banner opens itself
    page = _page(_app(hei_end="2020-01-01").test_client(), "/?lang=en")
    banner = page[page.index('class="home-banner no-print"'):page.index('<aside class="kural-card">')]
    assert 'href="/static/img/banner/kts5-banner-en-1080.jpg"' in banner and "/institutions/register" not in banner


def test_apply_now_leads_to_the_registration_of_institutions():
    client = _app().test_client()
    for path in ("/?lang=en", "/about?lang=en", "/syllabus?lang=hi"):
        page = _page(client, path)
        assert '<a class="btn saffron cta" href="/institutions/register">' in page, path
    assert '<a class="btn saffron cta" href="/institutions/register">Apply now</a>' in _page(client, "/?lang=en")
    # while it is not open: nothing, the students' registration being hidden (1.2.147); shown, the students' registration
    for app in (_app(hei_open="0"), _app(hei_end="2020-01-01")):
        assert 'class="btn saffron cta"' not in _page(app.test_client(), "/?lang=en")
    with app.app_context():   # the students' registration shown (hidden by default since 1.2.147)
        from kts.db import set_setting as _set
        _set("reg.public", "1")
        assert '<a class="btn saffron cta" href="/register">Apply now</a>' in _page(app.test_client(), "/?lang=en")


def test_no_video_guide_on_the_home_page():
    from kts.db import set_setting
    app = _app()
    with app.app_context():
        set_setting("home.hub", "1")
    client = app.test_client()
    home = _page(client, "/?lang=en")
    assert "video-guide" not in home and "gv-btn" not in home and "gv-home" not in home
    # the hub (shown) has no video button either; the video guide is off every page since 1.2.148
    assert "▶ Part 2" not in home
    guide = _page(client, "/how-to-take-part?lang=en")
    assert 'id="institutions"' in guide and 'id="video-guide"' not in guide


def test_find_your_next_step_and_the_launch_video_hidden(monkeypatch):
    # 3 Nov 2026 (1.2.146), the user: "hide Find your next step and Launch of the KTS 5.0 web portal and registration" - off the
    # home page by default; the Console's settings home.hub and home.launch_video show them again
    from kts.db import DEFAULT_SETTINGS, set_setting
    from kts.admin import SETTING_GROUPS
    assert DEFAULT_SETTINGS["home.hub"] == "0" and DEFAULT_SETTINGS["home.launch_video"] == "0"
    site = dict(SETTING_GROUPS)["Site"]
    assert [k for k, _label, kind in site if k in ("home.hub", "home.launch_video") and kind == "bool"] == ["home.hub", "home.launch_video"]
    app = _app()
    client = app.test_client()
    for lang in ("en", "ta", "hi"):
        home = _page(client, f"/?lang={lang}")
        assert 'class="hub-section"' not in home and "hub-title" not in home and "launch-video" not in home, lang
        assert "kts5-launch.mp4" not in home and "data-hub" not in home, lang
    assert "Find your next step" not in _page(client, "/?lang=en")
    # the search of the hub stays on its own page
    assert client.get("/my-college?lang=en").status_code == 200
    with app.app_context():
        set_setting("home.hub", "1")
        set_setting("home.launch_video", "1")
        set_setting("launch.on", "1")   # the tests' portal has no launch of its own
        set_setting("launch.at", "2026-10-22T12:00")
    home = _page(client, "/?lang=en")
    assert '<section class="hub-section"' in home and '<h2 id="hub-title">Find your next step</h2>' in home
    assert 'class="section launch-video"' in home and "Launch of the KTS 5.0 web portal and registration" in home

"""
The launch of the KTS 5.0 web portal and registration by the Hon'ble Minister of Education, Shri Pralhad Joshi, on 14 October 2026 at
5:00 PM (version 1.2.69): the banner announces it before the hour, registration opens at it, the home page counts down
to it and then says it was launched; the stage screen /launch, with the photograph of the Hon'ble Prime Minister and Thiruvalluvar; the launch video on the home page; the pinned notice and the schedule; the programme's
purpose on the home and About pages; the cards for social media; and the leftovers of the central test of earlier
versions (mails, candidate sign-in, programme, admit card) and the Daily Kural kits that are not there yet.

    python -m pytest tests -q
"""
from datetime import datetime
from pathlib import Path

from conftest import ROOT, make_app


def _at(day, hour=0, minute=0, month=10):
    from kts.utils import IST
    return datetime(2026, month, day, hour, minute, tzinfo=IST)


def _clock(monkeypatch, now):
    from kts import public, utils
    monkeypatch.setattr(utils, "now_ist", lambda: now)
    monkeypatch.setattr(public, "now_ist", lambda: now)


def _app(**settings):
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        from kts.db import DEFAULT_SETTINGS, set_setting
        for key in ("launch.on", "launch.at", "launch.until", "reg.start", "reg.end"):
            set_setting(key, settings.get(key, DEFAULT_SETTINGS[key]))
    return app


def test_the_moment_and_the_phases():
    from kts.db import DEFAULT_SETTINGS
    from kts.utils import launch_at, launch_phase, registration_state
    s = dict(DEFAULT_SETTINGS)
    assert s["launch.on"] == "1" and s["launch.at"] == "2026-10-14T17:00" and s["launch.until"] == "2026-10-22"
    assert s["reg.start"] == "2026-10-14" and s["reg.end"] == "2026-10-22"
    assert launch_at(s).isoformat() == "2026-10-14T17:00:00+05:30"
    assert launch_phase(s, _at(14, 16, 59)) == "before" and launch_phase(s, _at(14, 17)) == "after"
    assert launch_phase(s, _at(22, 23, 59)) == "after" and launch_phase(s, _at(23)) is None
    for off in ({"launch.on": "0"}, {"launch.at": ""}, {"launch.at": "5 PM"}):
        assert launch_at({**s, **off}) is None and launch_phase({**s, **off}, _at(14, 9)) is None


def test_registration_opens_at_the_launch(monkeypatch):
    from kts.db import DEFAULT_SETTINGS, RETIRED_DEFAULTS
    from kts.utils import registration_state
    s = dict(DEFAULT_SETTINGS)
    _clock(monkeypatch, _at(14, 16, 59))
    assert registration_state(s) == "not_yet"
    _clock(monkeypatch, _at(14, 17))
    assert registration_state(s) == "open"
    _clock(monkeypatch, _at(23))
    assert registration_state(s) == "closed"
    # a database that kept the day of the timeline of 8 October 2026 takes the day of the launch
    assert "2026-10-15" in RETIRED_DEFAULTS["reg.start"]


def test_the_banner_and_the_home_page_before_and_after(monkeypatch):
    app = _app()
    client = app.test_client()
    _clock(monkeypatch, _at(14, 16, 30))
    before = client.get("/?lang=en").get_data(as_text=True)
    assert ('<div class="banner launch">' in before and "The Kashi Tamil Sangamam 5.0 web portal and its registration will be launched by "
            "the Hon&#39;ble Minister of Education, Shri Pralhad Joshi, on 14 Oct 2026 at 5:00 PM." in before)
    assert '<div class="launch-card">' in before and "Launch of the KTS 5.0 web portal and registration" in before
    assert 'data-countdown="2026-10-14T17:00:00+05:30" data-done="The KTS 5.0 web portal and its registration are being launched" data-reload="1"' in before
    assert "Kashi Tamil Sangamam 5.0 begins in" not in before and 'id="launched"' not in before
    # the programme's purpose, under the theme
    assert ("Kashi Tamil Sangamam 5.0 will be held from 28 Nov 2026 to 12 Dec 2026 under the theme "
            "“Thirukkural Payilvom – Thirukkural Abhyas Karen”. The programme seeks to celebrate the cultural and civilisational "
            "bonds between Kashi and Tamil Nadu" in before)
    tamil = client.get("/?lang=ta").get_data(as_text=True)
    assert "பிரகலாத் ஜோஷி" in tamil and "14-10-2026 அன்று 17:00 மணிக்கு" in tamil
    hindi = client.get("/?lang=hi").get_data(as_text=True)
    assert "KTS 5.0 वेब पोर्टल एवं पंजीकरण का शुभारंभ" in hindi
    _clock(monkeypatch, _at(14, 17, 1))
    after = client.get("/?lang=en").get_data(as_text=True)
    assert '<div class="banner launch">' not in after and "Applications for KTS 5.0" in after
    assert ('id="launched"' in after and "The Kashi Tamil Sangamam 5.0 web portal and its registration were launched by the "
            "Hon&#39;ble Minister of Education, Shri Pralhad Joshi, on 14 Oct 2026." in after)
    assert '<div class="launch-card">' not in after and "Kashi Tamil Sangamam 5.0 begins in" in after
    about = client.get("/about?lang=en").get_data(as_text=True)
    assert "were launched by the Hon&#39;ble Minister of Education" in about and "civilisational bonds between Kashi" in about
    _clock(monkeypatch, _at(23))
    assert 'id="launched"' not in client.get("/?lang=en").get_data(as_text=True)


def test_the_stage_shows_launched_after_the_button(monkeypatch):
    # the button of the stage screen opens the home page with ?launched=1; that browser sees the portal as launched
    app = _app()
    client = app.test_client()
    _clock(monkeypatch, _at(14, 16, 58))
    page = client.get("/?launched=1&lang=en").get_data(as_text=True)
    assert 'id="launched"' in page and '<div class="banner launch">' not in page
    assert 'id="launched"' in client.get("/?lang=en").get_data(as_text=True)
    # every other browser waits for the hour, and registration too
    other = app.test_client().get("/?lang=en").get_data(as_text=True)
    assert '<div class="launch-card">' in other


def test_the_launch_postponed(monkeypatch):
    # the launch postponed: switched off in the Console with registration and the banner, hidden but not removed
    app = _app(**{"launch.on": "0"})
    with app.app_context():
        from kts.db import LAUNCH_NOTICE, query, set_setting
        set_setting("reg.open", "0")
        set_setting("site.banner_on", "0")
        nid = query("SELECT id FROM notices WHERE title = ?", (LAUNCH_NOTICE[0],), one=True)["id"]
    _clock(monkeypatch, _at(14, 15))
    client = app.test_client()
    home = client.get("/?lang=en").get_data(as_text=True)
    for gone in ("will be launched by", '<div class="banner', "launch-card", "kts5-launch.mp4", "14 October 2026, 5:00 PM"):
        assert gone not in home, gone
    assert "Kashi Tamil Sangamam 5.0 begins in" in home
    assert "14 October 2026, 5:00 PM" not in client.get("/notices?lang=en").get_data(as_text=True)
    assert client.get(f"/notices/{nid}").status_code == 404
    assert "opening of registration" not in client.get("/schedule?lang=en").get_data(as_text=True)
    register = client.get("/register?lang=en").get_data(as_text=True)
    assert "Registration is closed." in register and "Registrations closed on" not in register
    assert client.get("/launch").status_code == 200          # the stage screen stays, for the day
    # switched on again with a new moment: everything is back, for that day
    with app.app_context():
        set_setting("launch.on", "1")
        set_setting("launch.at", "2026-10-20T17:00")
        set_setting("reg.open", "1")
        set_setting("site.banner_on", "1")
    home = app.test_client().get("/?lang=en").get_data(as_text=True)
    assert "will be launched by" in home and "20 Oct 2026" in home and "launch-card" in home
    assert "5:00 PM" in app.test_client().get(f"/notices/{nid}").get_data(as_text=True)
    # after registration has really closed, its last day is named
    with app.app_context():
        set_setting("launch.on", "0")
    _clock(monkeypatch, _at(23, 10))
    assert "Registrations closed on" in app.test_client().get("/register?lang=en").get_data(as_text=True)


def test_the_postponement_switches_the_launch_off_once():
    from kts.db import get_setting, init_db, set_setting
    # a new database: nothing is switched off
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        assert get_setting("reg.open") == "1" and get_setting("site.banner_on") == "1"
        assert get_setting("seed.launch.postponed") == "1"
    # the live database, which announced the launch with the release of the morning: switched off at the next start
    with app.app_context():
        from kts.db import execute
        execute("DELETE FROM settings WHERE key = 'seed.launch.postponed'")
        for key in ("launch.on", "reg.open", "site.banner_on"):
            set_setting(key, "1")
    init_db(app)
    with app.app_context():
        assert [get_setting(k) for k in ("launch.on", "reg.open", "site.banner_on")] == ["0", "0", "0"]
        assert get_setting("launch.at") == "2026-10-14T17:00"          # the rest stays as it was
        # CICT switches them on again with the new moment: later starts leave them on
        for key in ("launch.on", "reg.open", "site.banner_on"):
            set_setting(key, "1")
    init_db(app)
    with app.app_context():
        assert [get_setting(k) for k in ("launch.on", "reg.open", "site.banner_on")] == ["1", "1", "1"]


def test_the_launch_video_on_the_home_page(monkeypatch):
    app = _app()
    _clock(monkeypatch, _at(14, 16, 30))
    assert "kts5-launch.mp4" not in app.test_client().get("/?lang=en").get_data(as_text=True)
    # from the hour: two minutes on the programme and the portal; the poster opens it in the browser's own player
    _clock(monkeypatch, _at(14, 17, 5))
    page = app.test_client().get("/?lang=en").get_data(as_text=True)
    for text in ('<section class="section launch-video"', 'id="launch-video-title"', "Launch of the KTS 5.0 web portal and registration",
                 '<a href="/static/video/kts5-launch.mp4" target="_blank" rel="noopener"',
                 '<img src="/static/video/kts5-launch-poster.jpg" alt="Launch of the KTS 5.0 web portal and registration"'):
        assert text in page, text
    assert page.index('class="hero"') < page.index("launch-video") < page.index("hei-intro")
    # after the days of the launch too, and in every language
    _clock(monkeypatch, _at(30, 10))
    assert "kts5-launch.mp4" in app.test_client().get("/?lang=ta").get_data(as_text=True)
    # the hall's computer, opened as launched by the stage screen a few minutes before the hour
    _clock(monkeypatch, _at(14, 16, 58))
    hall = app.test_client()
    assert "kts5-launch.mp4" in hall.get("/?launched=1&lang=en").get_data(as_text=True)
    # no launch, no video
    _clock(monkeypatch, _at(14, 17, 5))
    assert "kts5-launch.mp4" not in _app(**{"launch.on": "0"}).test_client().get("/?lang=en").get_data(as_text=True)
    # the files: a web copy that streams, the poster, and the captions of all thirteen lines of the voice-over
    folder = ROOT / "static" / "video"
    mp4 = folder / "kts5-launch.mp4"
    assert mp4.read_bytes()[4:8] == b"ftyp" and mp4.stat().st_size < 25_000_000
    assert (folder / "kts5-launch-poster.jpg").read_bytes()[:3] == b"\xff\xd8\xff"
    vtt = (folder / "kts5-launch.en.vtt").read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT") and vtt.count(" --> ") == 13 and "Shri Pralhad Joshi" in vtt and "Visit kts.cict.in." in vtt
    client = app.test_client()
    assert client.get("/static/video/kts5-launch.en.vtt").mimetype == "text/vtt"
    part = client.get("/static/video/kts5-launch.mp4", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.data) == 100 and part.mimetype == "video/mp4"


def test_the_stage_screen(monkeypatch):
    app = _app()
    client = app.test_client()
    r = client.get("/launch")
    assert r.status_code == 200 and r.headers["X-Robots-Tag"] == "noindex"
    page = r.get_data(as_text=True)
    for text in ("Launch of the KTS 5.0 web portal and registration", "KTS 5.0 वेब पोर्टल एवं पंजीकरण का शुभारंभ",
                 "KTS 5.0 இணையதள வெளியீடும் பதிவுத் தொடக்கமும்",
                 "माननीय शिक्षा मंत्री श्री प्रल्हाद जोशी द्वारा", "by the Hon&#39;ble Minister of Education, Shri Pralhad Joshi",
                 "14 October 2026 · 5:00 PM", 'id="go"', "data:image/png;base64,", "kts.cict.in",
                 'data-home="/?launched=1"', "/static/js/launch.js", "/static/css/launch.css",
                 "img/logos/moe.png", "img/cict-logo.png", "Opening the portal…"):
        assert text in page, text
    assert 'data-stay="1"' in client.get("/launch?stay=1").get_data(as_text=True)
    assert "Opening the portal" not in client.get("/launch?stay=1").get_data(as_text=True)
    script = (ROOT / "static" / "js" / "launch.js").read_text(encoding="utf-8")
    assert '"Enter", " ", "PageDown"' in script and "prefers-reduced-motion" in script and 'classList.add("open")' in script
    # not a page for search engines or the sitemap
    assert "/launch" not in client.get("/sitemap.xml").get_data(as_text=True)


def test_the_photograph_on_the_stage_screen():
    page = _app().test_client().get("/launch").get_data(as_text=True)
    # the caption the organisers gave, under the photograph and as its alternative text
    assert '<figure class="side pm">' in page and "/static/img/launch-pm.jpg" in page
    assert """alt="Hon'ble Prime Minister of Bharat, Shri Narendra Modi\"""" in page
    assert "<span>Hon'ble Prime Minister of Bharat,</span> <strong>Shri Narendra Modi</strong>" in page
    # Thiruvalluvar at the right: the portal's own picture (as on the About page), named in Tamil and English
    assert '<figure class="side tv">' in page and "/static/img/thiruvalluvar.jpg" in page
    assert 'alt="Thiruvalluvar, author of the Thirukkural"' in page
    assert '<span lang="ta">திருவள்ளுவர்</span> <strong>Thiruvalluvar</strong>' in page
    # above the curtain and outside the front, so they stay while the curtain opens and on the address screen after it
    assert (page.index('class="curtain right"') < page.index('id="front"') < page.index('<figure class="side pm">')
            < page.index('<figure class="side tv">') < page.index('id="full"'))
    photo = ROOT / "static" / "img" / "launch-pm.jpg"
    assert photo.read_bytes()[:3] == b"\xff\xd8\xff" and photo.stat().st_size < 80_000
    assert (ROOT / "static" / "img" / "thiruvalluvar.jpg").is_file()
    css = (ROOT / "static" / "css" / "launch.css").read_text(encoding="utf-8")
    assert ".side {" in css and "z-index: 5" in css.split(".side {", 1)[1].split("}", 1)[0]
    assert ".side.pm { left:" in css and ".side.tv { right:" in css
    # the content is centred between the two pictures
    assert "padding-left: var(--pl); padding-right: var(--pl);" in css
    assert "@media (max-aspect-ratio: 1/1)" in css and "@media (max-aspect-ratio: 16/10)" in css
    assert "css/launch.css') }}?v=5" in (ROOT / "templates" / "public" / "launch.html").read_text(encoding="utf-8")


def test_the_notice_and_the_schedule(monkeypatch):
    app = _app()
    with app.app_context():
        from kts.db import LAUNCH_NOTICE, query
        rows = query("SELECT * FROM notices WHERE title = ?", (LAUNCH_NOTICE[0],))
        assert len(rows) == 1 and rows[0]["pinned"] == 1 and rows[0]["published"] == 1
        assert "Shri Pralhad Joshi" in rows[0]["body"] and "14 October 2026 (Wednesday) at 5:00 PM" in rows[0]["body"]
    client = app.test_client()
    _clock(monkeypatch, _at(14, 10))
    assert "Launch of the KTS 5.0 web portal and registration" in client.get("/notices?lang=en").get_data(as_text=True)
    schedule = client.get("/schedule?lang=en").get_data(as_text=True)
    # the schedule's own entry for the day: the launch of the web portal and the opening of registration, on 14 October
    i = schedule.index("Launch of the KTS 5.0 web portal and opening of registration")
    assert "14 Oct 2026" in schedule[max(0, i - 600):i]
    assert "KTS 5.0 இணையதள வெளியீடும் பதிவுத் தொடக்கமும்" in client.get("/schedule?lang=ta").get_data(as_text=True)


def test_the_cards_for_social_media():
    from PIL import Image
    app = _app()
    page = app.test_client().get("/about?lang=en").get_data(as_text=True)
    assert '<meta property="og:image" content="' in page and "/static/img/og-kts5.jpg" in page
    assert '<meta property="og:title" content="About Kashi Tamil Sangamam · Thirukkural Payilvom' in page
    assert '<meta name="twitter:card" content="summary_large_image">' in page and '<meta property="og:url" content="' in page
    im = Image.open(ROOT / "static" / "img" / "og-kts5.jpg")
    assert im.size == (1200, 630) and im.format == "JPEG"


def test_the_central_test_is_not_announced_any_more():
    app = _app()
    client = app.test_client()
    programme = client.get("/programme?lang=en").get_data(as_text=True)
    assert "11:30" not in programme and "Assessments at the institutions" in programme
    login = client.get("/candidate/login?lang=en").get_data(as_text=True)
    assert "11:30" not in login
    home = (ROOT / "templates" / "candidate" / "home.html").read_text(encoding="utf-8")
    assert "and settings['exam.open'] != '0' %}<a class=\"btn sm secondary\" href=\"{{ url_for('candidate.admit_card') }}\">" in home
    assert "online selection test" not in (ROOT / "kts" / "admin.py").read_text(encoding="utf-8")
    assert "sign in for the online test" not in (ROOT / "kts" / "public.py").read_text(encoding="utf-8")


def test_the_daily_kural_names_the_kits_only_when_there_are_some():
    app = _app()
    client = app.test_client()
    assert "cat=daily" not in client.get("/daily-kural?lang=en").get_data(as_text=True)
    with app.app_context():
        from kts.db import execute, utcnow
        execute("INSERT INTO resources(title, category, url, published, created_at, updated_at) VALUES(?,?,?,1,?,?)",
                ("Daily Kural chart", "daily", "https://example.org/chart.pdf", utcnow(), utcnow()))
    assert "cat=daily" in client.get("/daily-kural?lang=en").get_data(as_text=True)


def test_the_console_can_move_the_hour():
    from kts.admin import SETTING_GROUPS
    keys = [k for _title, items in SETTING_GROUPS for k, *_ in items]
    assert {"launch.on", "launch.at", "launch.until"} <= set(keys)

"""
Release 1.2.152 (4 November 2026, CICT's annotated screenshot and its note "KTS_Website_Details_04_11_2026"): "Institution login" in
the top strip in place of "Candidate login"; no "Apply now"; the strip of the registration of institutions larger, on a coloured
band; the circular band plain, the newest circular of the Ministry first, with a blinking NEW while it is recent; quick links; the
Guidelines for Nodal Institutions; "KTS 5.0 – Key dates"; the schedule without CICT's central online test; the nomination tile of
/how-to-take-part; the steps of submitting the selected student; the number of the D.O. letter as printed.

    python -m pytest tests -q
"""
import json
import re

from markupsafe import escape

from conftest import ROOT, make_app

CATALOGUES = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "data" / "i18n").glob("*.json")}


def _get(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def _app(**values):
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for key, value in values.items():
            set_setting(key.replace("_", "."), value)
    return app


# as the live portal stands: the students' registration switched off after the launch, the institutions registering
LIVE = {"reg_open": "0", "launch_on": "0", "hei_open": "1", "hei_end": "2099-12-31", "reg_end": "2099-12-31"}


def test_the_settings():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS["schedule.central_test"] == "0" and DEFAULT_SETTINGS["circular.new_days"] == "30"
    site = {k: kind for k, _label, kind in dict(SETTING_GROUPS)["Site"]}
    assert site["schedule.central_test"] == "bool" and site["circular.new_days"] == "text"


def test_the_top_strip_and_the_masthead():
    client = _app(**LIVE).test_client()
    for code, cat in CATALOGUES.items():
        page = _get(client, f"/?lang={code}")
        strip = page[page.index('<div class="gov-strip">'):page.index("<header")]
        assert f'<a href="/institution/login">{escape(cat["nav.inst_login"])}</a>' in strip, code
        assert "/candidate/login" not in strip and escape(cat["nav.candidate"]) not in strip, code
        masthead = page[page.index('<header class="masthead">'):page.index("</header>")]
        assert "cta" not in masthead and escape(cat["home.cta_register"]) not in masthead, code
    # the candidate portal still opens at its address
    assert client.get("/candidate/login?lang=en").status_code == 200


def test_the_strip_of_the_registration_is_highlighted():
    client = _app(**LIVE).test_client()
    page = _get(client, "/?lang=en")
    assert '<div class="banner reg-open">' in page
    strip = page[page.index('<div class="banner reg-open">'):]
    strip = strip[:strip.index("</div></div>")]
    assert "Registration is now open for Participating Institutions." in strip
    assert '<a class="banner-go" href="/institutions/register">Register your institution' in strip
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    rule = css[css.index(".banner.reg-open {"):]
    rule = rule[:rule.index("}")]
    assert "font-size: 1.12rem" in rule and "background: #1f3a5f" in rule


def test_the_circular_band():
    from kts.db import DO_NOTICE, DO_NOTICE_FILE
    app = _app(**LIVE)
    client = app.test_client()
    for code, cat in CATALOGUES.items():
        page = _get(client, f"/?lang={code}")
        band = page[page.index('<div class="nodal-attention">'):page.index('<section class="hero">')]
        assert str(escape(cat["tag.circular"])) in band and f'<span class="new-badge">{escape(cat["circ.new"])}</span>' in band, code
        first = band.index('<li class="na-first">')
        # the newest circular of the Ministry first, its letter beside it; then the guidelines and the list of the Nodal HEIs
        assert first < band.index('href="/guidelines-for-nodal-institutions"') < band.index('<a class="na-link" href="/nodal-institutions">'), code
        assert f'<span class="na-title">{escape(cat["ng.title"])}</span>' in band and f'<span class="na-title">{escape(cat["nodal.title"])}</span>' in band, code
        assert f'href="/files/{DO_NOTICE_FILE}"' in band, code
        assert band.index('<span class="na-title" lang="en" dir="ltr">D.O. letter of the Ministry of Education, 31 October 2026</span>') > first, code
    # NEW only while the circular is recent; never with 0
    with app.app_context():
        from kts.db import execute, set_setting
        execute("UPDATE notices SET created_at = '2026-01-01T00:00:00' WHERE title = ?", (DO_NOTICE[0],))
        assert "new-badge" not in _get(client, "/?lang=en")
        set_setting("circular.new_days", "100000")
        assert '<span class="new-badge">NEW</span>' in _get(client, "/?lang=en")
        set_setting("circular.new_days", "0")
        assert "new-badge" not in _get(client, "/?lang=en")
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    rules = css[css.index(".nodal-attention {"):css.index(".btn.saffron:hover")]
    # a plain band, not red; the NEW blinks continuously (1.2.153, the user: "make the NEW badge blink continuously"), and never
    # for those who ask for reduced motion
    assert ".nodal-attention { background: var(--surface);" in rules and "linear-gradient" not in rules and "#8f1d17" not in rules
    assert "@media (prefers-reduced-motion: no-preference) {\n  .new-badge { animation: new-blink 1s steps(1, end) .3s infinite; }" in rules.replace("\r\n", "\n")


def test_a_newer_circular_comes_first():
    app = _app(**LIVE)
    with app.app_context():
        from kts.db import execute
        execute("INSERT INTO notices(title, body, category, lang, pinned, published, attachment, created_at, updated_at) "
                "VALUES('D.O. letter of the Ministry of Education, 9 December 2026: something new', '', 'circular', 'en', 1, 1, "
                "'notices/KTS5-DO-letter-31-October-2026.pdf', '2099-01-01T00:00:00', '2099-01-01T00:00:00')")
    band = _get(app.test_client(), "/?lang=en").split('<li class="na-first">')[1].split("</li>")[0]
    assert ">D.O. letter of the Ministry of Education, 9 December 2026</span>" in band


def test_the_quick_links():
    client = _app(**LIVE).test_client()
    for code, cat in CATALOGUES.items():
        page = _get(client, f"/?lang={code}")
        assert page.index('<div class="nodal-attention">') < page.index('<nav class="quick-links"') < page.index('<section class="hero">'), code
        links = page[page.index('<nav class="quick-links"'):]
        links = links[:links.index("</nav>")]
        hrefs = re.findall(r'<a class="ql[^"]*" href="([^"]+)">', links)
        assert hrefs == ["/institutions/register", "/how-to-take-part", "/guidelines-for-nodal-institutions", "/thirukkural-108",
                         "/syllabus", "/how-to-submit-the-student", "/institution/login", "/console/login"], (code, hrefs)
        for key in ("hei.cta", "home.hei_guidelines", "ng.title", "k108.title", "ql.study", "ql.submit", "nav.inst_login", "nav.nodal_login"):
            assert f"<span>{escape(cat[key])}</span>" in links, (code, key)
    # once the registration of institutions is over, its tile goes
    page = _get(_app(**dict(LIVE, hei_end="2020-01-01")).test_client(), "/?lang=en")
    assert 'href="/institutions/register"><span class="ql-ico"' not in page and 'href="/how-to-take-part"><span class="ql-ico"' in page


def test_the_key_dates():
    # the tests' portal keeps its registration open to 2030; the live portal has the day of the letter
    client = _app(reg_end="2026-11-20").test_client()
    for path in ("/", "/schedule", "/guidelines-for-nodal-institutions"):
        page = _get(client, path + "?lang=en")
        box = page[page.index('<div class="kd-box">'):]
        box = box[:box.index("</div>\n</div>") if "</div>\n</div>" in box else 6000]
        text = re.sub(r"<[^>]+>", "|", box)
        for line in ("KTS 5.0 – Key dates", "Registration and selection", "Online programme", "Research and submission",
                     "Up to 15 Nov 2026", "Last date for the registration of institutions",
                     "16 Nov 2026 – 17 Nov 2026", "Selection of the Participating Institutions by the Nodal Institutions",
                     "By 19 Nov 2026", "Thirukkural assessment of the interested students by each Participating Institution",
                     "20 Nov 2026", "Each Participating Institution nominates one student on merit through the CICT portal",
                     "28 Nov 2026", "Inaugural function of KTS 5.0", "12 Dec 2026", "Valedictory function of KTS 5.0",
                     "All Nodal Institutions, Participating Institutions and nominated students will join online. The joining links will be shared separately.",
                     "All participants will receive a certificate of participation from CICT.",
                     "By 14 Dec 2026", "Academic orientation and study material from CICT",
                     "15 Dec 2026 – 14 Jan 2027", "One-month research and writing period",
                     "By 14 Jan 2027", "Last date to submit the research work and reports"):
            assert f"|{line}|" in text, (path, line)
    # in a language other than English the days read as numbers
    page = _get(client, "/?lang=hi")
    assert "15-11-2026" in page and "16-11-2026 – 17-11-2026" in page


def test_the_schedule_without_the_central_online_test():
    app = _app()
    client = app.test_client()
    for path in ("/schedule?lang=en", "/?lang=en"):
        assert "central online test" not in _get(client, path), path
    with app.app_context():
        from kts.db import set_setting
        set_setting("schedule.central_test", "1")
    assert "CICT&#39;s central online test, from the candidate portal" in _get(client, "/schedule?lang=en")


def test_the_guide_names_the_nomination_by_the_institution():
    client = _app().test_client()
    for code, cat in CATALOGUES.items():
        page = _get(client, f"/how-to-take-part?lang={code}")
        assert f'<div class="lbl">{escape(cat["guide.date_nominate"])}</div>' in page, code
        assert f'<div class="lbl">{escape(cat["guide.date_reg"])}</div>' not in page, code


def test_the_guidelines_for_nodal_institutions():
    client = _app().test_client()
    page = _get(client, "/guidelines-for-nodal-institutions?lang=en")
    assert "<h1>Guidelines for Nodal Institutions</h1>" in page
    assert ('Key points of the D.O. letter of the Ministry of Education, Government of India, <span class="do-no" dir="ltr">D.O. No. '
            '16-2/2026-Skt.I (Pt.)</span>, dated 31 Oct 2026, on the Students&#39; Engagement Programme of Kashi Tamil Sangamam 5.0.') in page
    for line in ("<b>Constitution of the Committee:</b> The Head of each Nodal Institution shall constitute an Evaluation Committee.",
                 "<b>Members of the Committee:</b> The Committee shall consist of at least three members, including the State/UT Nodal Officer.",
                 "<b>Evaluation process:</b> The Committee shall evaluate all eligible applications and award marks according to the criteria "
                 "and scoring parameters in Paragraph 3 of the Standard Operating Procedure.",
                 "<b>Authentication:</b> All members of the Committee shall sign the evaluation sheets.",
                 "<b>Approval:</b> The Committee shall recommend the selected list and the reserve list for approval by the competent "
                 "authority of the Nodal Institution.",
                 "<b>Total: 100 marks. Recommended qualifying benchmark: 60 marks.</b>"):
        assert line in page, line
    assert page.count('<td class="num"><b>20</b></td>') == 5
    assert '<a class="btn saffron" href="/files/notices/KTS5-DO-letter-31-October-2026.pdf"' in page
    r = client.get("/files/notices/KTS5-DO-letter-31-October-2026.pdf")
    assert r.status_code == 200 and r.data[:5] == b"%PDF-"
    for code, cat in CATALOGUES.items():
        page = _get(client, f"/guidelines-for-nodal-institutions?lang={code}")
        assert f"<h1>{escape(cat['ng.title'])}</h1>" in page and "{do}" not in page and "{date}" not in page, code
        assert "16-2/2026-Skt.I (Pt.)" in page, code


def test_submitting_the_selected_student():
    client = _app().test_client()
    page = _get(client, "/how-to-submit-the-student?lang=en")
    assert "<h1>Submitting the selected student on the portal</h1>" in page
    assert 'Open <a href="/institution/login">Institution login</a> and enter the e-mail address' in page
    assert 'press <b class="ui-name" lang="en" dir="ltr">Select</b> beside the student chosen on merit' in page
    assert 'In <b class="ui-name" lang="en" dir="ltr">Verification queue</b>, open each application' in page
    assert "by 19 Nov 2026" in page and "with {open_reg}" not in page and "by 05 Dec 2026" in page and "by 17 Nov 2026" in page
    assert 'Open <a href="/console/login">Nodal Officer login</a> and sign in' in page
    for code, cat in CATALOGUES.items():
        page = _get(client, f"/how-to-submit-the-student?lang={code}")
        assert f"<h1>{escape(cat['hs.title'])}</h1>" in page, code
        main = page[page.index("<main"):page.index("</main>")]
        assert not re.search(r"\{[a-z_0-9]+\}", main), (code, re.findall(r"\{[a-z_0-9]+\}", main))
        assert main.count('class="ui-name"') == 22 and '<b class="ui-name" lang="en" dir="ltr">✓ Verify</b>' in main, code
        assert 'href="/institution/login"' in main and 'href="/console/login"' in main, code


def test_the_new_pages_in_the_menu_the_sitemap_and_the_search():
    client = _app().test_client()
    page = _get(client, "/?lang=en")
    menu = page.split('id="primary-menu"')[1].split("</nav>")[0]
    assert '<li><a href="/guidelines-for-nodal-institutions">Guidelines for Nodal Institutions</a></li>' in menu
    assert '<li><a href="/how-to-submit-the-student">Submitting the selected student on the portal</a></li>' in menu
    sitemap = _get(client, "/sitemap?lang=en")
    assert 'href="/guidelines-for-nodal-institutions"' in sitemap and 'href="/how-to-submit-the-student"' in sitemap
    xml = _get(client, "/sitemap.xml")
    assert "/guidelines-for-nodal-institutions</loc>" in xml and "/how-to-submit-the-student</loc>" in xml
    assert 'href="/guidelines-for-nodal-institutions"' in _get(client, "/search?lang=en&q=guidelines+nodal")


def test_the_number_of_the_letter_as_printed():
    from kts.db import DO_NOTICE
    assert "D.O. No. 16-2/2026-Skt.I (Pt.) of 31 October 2026" in DO_NOTICE[1]
    for code, cat in CATALOGUES.items():
        assert "16-2/2026-Skt.I (Pt.)" in cat["nl.reference"] and "Skt.(Pt.)" not in json.dumps(cat, ensure_ascii=False), code
    # the notice put in before takes it where its text is still the one put in, once; a text CICT changed stays as it is
    from kts.db import execute, init_db, query
    app = make_app(ADMIN_PASSWORD=None)
    old = DO_NOTICE[1].replace("16-2/2026-Skt.I (Pt.)", "16-2/2026-Skt.(Pt.)")
    with app.app_context():
        assert "16-2/2026-Skt.I (Pt.)" in query("SELECT body FROM notices WHERE title = ?", (DO_NOTICE[0],), one=True)["body"]
        execute("UPDATE notices SET body = ? WHERE title = ?", (old, DO_NOTICE[0]))
        execute("DELETE FROM settings WHERE key = 'migrate.do_31oct.number'")
    init_db(app)
    with app.app_context():
        assert query("SELECT body FROM notices WHERE title = ?", (DO_NOTICE[0],), one=True)["body"] == DO_NOTICE[1]
        execute("UPDATE notices SET body = ? WHERE title = ?", (old + " (edited)", DO_NOTICE[0]))
        execute("DELETE FROM settings WHERE key = 'migrate.do_31oct.number'")
    init_db(app)
    with app.app_context():
        assert query("SELECT body FROM notices WHERE title = ?", (DO_NOTICE[0],), one=True)["body"] == old + " (edited)"

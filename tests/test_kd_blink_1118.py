"""
The last date for the registration of institutions in bold, blinking letters on the home page (1.2.205). CICT, 18 November 2026:
"the last date for the registration of institutions 21 Nov 2026 in blinking letters on home Page, bold letters".

The row of the Key dates of the home page, while the registration of institutions is open; a row like the others after the last
date, and on the other pages that show the box. It blinks as the NEW badge does, and not for those who ask for reduced motion.

And CICT, of the same box, a little later: "hide these" (the selection on 22 November, the assessment by 23 November, the
nomination on 24 November) - "also hide and selection": the first group holds the registration alone, under "Registration".

    python -m pytest tests/test_kd_blink_1118.py -q
"""
import re

from conftest import ROOT, make_app

ROW = '<li class="kd-blink"><span class="kd-when"><bdi>Up to {}</bdi></span><span class="kd-what">Last date for the registration of institutions</span></li>'
PLAIN = '<li><span class="kd-when"><bdi>Up to {}</bdi></span><span class="kd-what">Last date for the registration of institutions</span></li>'


def _portal(last_day):
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("hei.open", "1")
        set_setting("hei.end", last_day)
    return app.test_client()


def test_the_row_of_the_home_page_while_the_registration_is_open():
    client = _portal("2099-12-31")
    home = client.get("/?lang=en").get_data(as_text=True)
    assert ROW.format("31 Dec 2099") in home and home.count('class="kd-blink"') == 1
    # the other rows are as they were
    assert '<span class="kd-what">Selection of the Participating Institutions by the Nodal Institutions</span></li>' in home
    assert re.search(r'<li><span class="kd-when"><bdi>[^<]+</bdi></span><span class="kd-what">Selection of the Participating', home)
    # in another language the same row, with its own words
    tamil = client.get("/?lang=ta").get_data(as_text=True)
    assert tamil.count('class="kd-blink"') == 1
    # the schedule and the Guidelines show the box without it
    for path in ("/schedule", "/guidelines-for-nodal-institutions"):
        page = client.get(path + "?lang=en").get_data(as_text=True)
        assert "kd-blink" not in page and PLAIN.format("31 Dec 2099") in page, path


def test_after_the_last_date_it_is_a_row_like_the_others():
    client = _portal("2020-01-01")
    home = client.get("/?lang=en").get_data(as_text=True)
    assert "kd-blink" not in home and PLAIN.format("01 Jan 2020") in home
    # and where the registration of institutions is switched off
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("hei.open", "0")
        set_setting("hei.end", "2099-12-31")
    assert "kd-blink" not in app.test_client().get("/?lang=en").get_data(as_text=True)


def _group1(page):
    """The first group of the Key dates box: (its heading, its rows as text)."""
    box = page[page.index('<div class="kd-box">'):]
    group = box[box.index('<section class="kd-group kd-1"'):]
    group = group[:group.index("</section>")]
    heading = re.search(r'<h3 class="kd-gh"[^>]*>([^<]+)</h3>', group).group(1)
    rows = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", li)).strip() for li in re.findall(r"<li[^>]*>.*?</li>", group, re.S)]
    return heading, rows


def test_the_selection_the_assessment_and_the_nomination_are_hidden():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS, set_setting
    from kts.i18n import CATALOG
    assert DEFAULT_SETTINGS["kd.select_rows"] == "0"
    rows = {k: (label, kind) for _group, items in SETTING_GROUPS for k, label, kind in items}
    assert rows["kd.select_rows"] == ("Show in the Key dates the selection of the Participating Institutions, the assessment and the "
                                      "nomination, under the heading “Registration and selection” (off: the registration alone, under "
                                      "“Registration”)", "bool")
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("kd.select_rows", "0")
        set_setting("hei.open", "1")
        set_setting("hei.end", "2099-12-31")
    client = app.test_client()
    for path in ("/", "/schedule", "/guidelines-for-nodal-institutions"):
        page = client.get(path + "?lang=en").get_data(as_text=True)
        heading, rows = _group1(page)
        assert heading == "Registration" and rows == ["Up to 31 Dec 2099 Last date for the registration of institutions"], (path, heading, rows)
        box = page[page.index('<div class="kd-box">'):][:6000]
        for gone in ("Registration and selection", "Selection of the Participating Institutions by the Nodal Institutions",
                     "Thirukkural assessment of the interested students", "nominates one student on merit through the CICT portal"):
            assert gone not in box, (path, gone)
        # the other groups stay
        assert "Inaugural function of KTS 5.0" in box and "Academic orientation and study material from CICT" in box, path
    # the row blinks on the home page as before, alone in its group
    home = client.get("/?lang=en").get_data(as_text=True)
    assert ROW.format("31 Dec 2099") in home
    # in each language the heading is the word "Registration" of the schedule
    for code in ("ta", "hi", "ur", "sat"):
        heading, rows = _group1(client.get(f"/?lang={code}").get_data(as_text=True))
        assert heading == CATALOG[code]["tag.registration"] and heading != CATALOG[code]["kd.g1"] and len(rows) == 1, code
    # switched on in the Console, the three rows and the heading come back
    with app.app_context():
        set_setting("kd.select_rows", "1")
    heading, rows = _group1(client.get("/?lang=en").get_data(as_text=True))
    assert heading == "Registration and selection" and len(rows) == 4


def test_the_letters_are_bold_and_blink_as_the_new_badge_does():
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    assert ".kd-list li.kd-blink .kd-what { font-weight: 800; }" in css
    assert ".kd-when { font-weight: 800;" in css                      # the day itself was in bold already
    # once a second, for as long as the page is open; only where the reader has not asked for reduced motion
    block = css[css.index(".kd-list li.kd-blink .kd-what"):]
    assert re.match(r"[^\n]+\n@media \(prefers-reduced-motion: no-preference\) \{\n  \.kd-list li\.kd-blink \{ animation: new-blink 1s steps\(1, end\) \.3s infinite; \}\n\}", block)
    assert "@keyframes new-blink { 0%, 60% { opacity: 1; } 61%, 100% { opacity: .08; } }" in css
    assert css.count("kd-blink") == 2
    # every browser takes the new style sheet
    page = _portal("2099-12-31").get("/?lang=en").get_data(as_text=True)
    assert '<link rel="stylesheet" href="/static/css/portal.css?v=58">' in page      # 54 since 1.2.215

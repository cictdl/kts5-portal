"""
The nomination by the Participating Institutions (version 1.2.154; the user: "Make arrangement to Each Participating Institution
nominates one student on merit through the CICT portal"): the personal registration link of the student a Participating Institution
selects opens the form up to reg.end even while the students' own registration is switched off (reg.open '0', as on the live portal
since the launch) and hidden (reg.public '0'); without a link the registration stays closed; nominate.open '0' or a past reg.end
closes the links too. The strip and the key dates point the institutions to the steps.

    python -m pytest tests -q
"""
import re

from markupsafe import escape

from conftest import make_app
from test_campus import _accepted, _coordinator, _portal, _register_with


def _live_like(app, **more):
    """The settings of the live portal: registration switched off after the launch, the students' registration hidden."""
    from kts.db import set_setting
    with app.app_context():
        for key, value in {"reg.open": "0", "launch.on": "0", "reg.public": "0", "reg.end": "2099-12-31", **more}.items():
            set_setting(key, value)


def _selected(app):
    """An accepted institution whose coordinator enters the student selected after its own assessment: (inst, link, coordinator)."""
    inst = _accepted(app)
    coord, token = _coordinator(app, inst)
    r = coord.post("/institution/winner", data={"_csrf": token, "action": "enter", "name": "Priya Student",
                                                 "email": "priya@student.example", "mobile": "9123456780", "roll_no": "21TAM007",
                                                 "course": "B.A. Tamil, 2nd year", "lang": "hi"}, follow_redirects=True)
    page = r.get_data(as_text=True)
    assert "Priya Student is selected" in page, page[:2000]
    return inst, re.search(r"https?://[^\s<]+/register\?token=[A-Za-z0-9_-]+", page).group(0), coord


def _path(link):
    return "/register?token=" + link.split("token=")[1] + "&lang=en"


def test_the_setting():
    from kts.admin import SETTING_GROUPS
    from kts.db import DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS["nominate.open"] == "1"
    assert [k for k, _label, kind in dict(SETTING_GROUPS)["Site"] if k == "nominate.open" and kind == "bool"] == ["nominate.open"]


def test_the_institution_nominates_its_student_while_registration_is_off():
    from kts.db import query
    app = _portal()
    _live_like(app)
    # without a link the registration is closed, as since the launch: the students are selected through the institutions
    page = app.test_client().get("/register?lang=en").get_data(as_text=True)
    assert 'name="full_name"' not in page
    inst, link, coord = _selected(app)
    form, r = _register_with(app, link)
    # the form, with the institution fixed and the student filled in, and the nomination is stored
    assert 'name="full_name"' in form and "from your registration link" in form and inst["name"] in form and 'value="Priya Student"' in form
    assert r.status_code == 302, r.get_data(as_text=True)[:1500]
    with app.app_context():
        a = query("SELECT * FROM applications", one=True)
        assert (a["institution_id"], a["status"], a["full_name"]) == (inst["id"], "submitted", "Priya Student")
        assert query("SELECT application_id FROM institutions WHERE id = ?", (inst["id"],), one=True)["application_id"] == a["id"]
    page = coord.get("/institution").get_data(as_text=True)
    assert "has registered: application" in page and a["app_no"] in page
    # the link works once; and still nothing without one
    assert 'name="full_name"' not in app.test_client().get(_path(link)).get_data(as_text=True)
    assert 'name="full_name"' not in app.test_client().get("/register?lang=en").get_data(as_text=True)


def test_the_links_close_with_the_setting_or_after_the_last_day():
    from kts.db import set_setting
    app = _portal()
    _live_like(app)
    _inst, link, _coord = _selected(app)
    assert 'name="full_name"' in app.test_client().get(_path(link)).get_data(as_text=True)
    with app.app_context():
        set_setting("nominate.open", "0")
    assert 'name="full_name"' not in app.test_client().get(_path(link)).get_data(as_text=True)
    with app.app_context():
        set_setting("nominate.open", "1")
        set_setting("reg.end", "2020-01-01")
    page = app.test_client().get(_path(link)).get_data(as_text=True)
    assert 'name="full_name"' not in page
    with app.app_context():
        set_setting("reg.end", "2099-12-31")
    assert 'name="full_name"' in app.test_client().get(_path(link)).get_data(as_text=True)


def test_the_strip_and_the_key_dates_point_to_the_nomination():
    from kts.i18n import CATALOG
    app = make_app(ADMIN_PASSWORD=None)
    # the registration of institutions over (15 November), the nomination open (to 20 November)
    _live_like(app, **{"hei.open": "1", "hei.end": "2020-01-01"})
    client = app.test_client()
    for code, cat in CATALOG.items():
        page = client.get(f"/?lang={code}").get_data(as_text=True)
        strip = page[page.index('<div class="banner reg-open">'):]
        strip = strip[:strip.index("</div></div>")]
        assert str(escape(cat["kd.nominate"])) in strip, code
        assert f'<a class="banner-go" href="/how-to-submit-the-student">{escape(cat["ql.submit"])}' in strip, code
        box = page[page.index('<div class="kd-box">'):]
        assert f'<a href="/how-to-submit-the-student">{escape(cat["kd.nominate"])}</a>' in box, code
    page = client.get("/?lang=en").get_data(as_text=True)
    assert "Each Participating Institution nominates one student on merit through the CICT portal · By 31 Dec 2099" in page
    # while the institutions register, their registration, as before
    _live_like(app, **{"hei.end": "2099-12-31"})
    page = client.get("/?lang=en").get_data(as_text=True)
    strip = page[page.index('<div class="banner reg-open">'):]
    strip = strip[:strip.index("</div></div>")]
    assert "Registration is now open for Participating Institutions." in strip and "/institutions/register" in strip
    assert "nominates one student" not in strip
    # with the nomination closed by CICT, the strip does not invite it
    _live_like(app, **{"hei.end": "2020-01-01", "nominate.open": "0"})
    strip = client.get("/?lang=en").get_data(as_text=True)
    strip = strip[strip.index('<div class="banner reg-open">'):]
    assert "nominates one student" not in strip[:strip.index("</div></div>")]

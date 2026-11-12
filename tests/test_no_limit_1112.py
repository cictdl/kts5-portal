"""
"Any number of institutions of a State/UT may register." beside every "Register your institution" (1.2.176; CICT, 12 November
2026: "any state can add any number of institution", asked where: say it clearly, no rule changes), and the sentence under the
reserve list while an institution of it has no marks yet (hei.marks_first off, 1.2.175).

    python -m pytest tests/test_no_limit_1112.py -q
"""
import itertools
import re

from conftest import make_app

LANGS = ["as", "bn", "brx", "doi", "en", "gu", "hi", "kn", "kok", "ks", "mai", "ml", "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd",
         "ta", "te", "ur"]
NUMBERS = itertools.count(1)


def _app(**settings):
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("hei.end", "2099-12-31")
        set_setting("hei.open", "1")
        set_setting("join.on", "1")
        for key, value in settings.items():
            set_setting(key.replace("_", "."), value)
    return app


def _insert(app, name, state, status, total=None):
    from kts.db import execute, utcnow
    with app.app_context():
        execute("INSERT INTO institutions(ref, name, itype, state, district, inst_key, status, head_name, sop_total, created_at, updated_at) "
                "VALUES(?, ?, 'Government college', ?, 'District', ?, ?, 'Dr. Head', ?, ?, ?)",
                (f"KTS5-HEI-8{next(NUMBERS):04d}", name, state, f"name:{name.lower()}|{state.lower()}", status, total, utcnow(), utcnow()))


def test_the_label_beside_every_register_button():
    from kts import drive as DRIVE
    from kts.i18n import CATALOG
    app = _app()
    client = app.test_client()
    with app.app_context():
        code = DRIVE.code_of("Puducherry")
    for lang in ("en", "ta", "hi", "ur"):
        label = CATALOG[lang]["hei.no_limit"]
        for path in ("/", "/institutions", "/nodal-institutions", f"/join/{code}"):
            page = client.get(f"{path}?lang={lang}").get_data(as_text=True)
            assert f'<span class="pill green hei-no-limit"' in page and label in page, (lang, path)
            # beside the button
            button = page.index(f">{CATALOG[lang]['hei.cta']}</a>", page.index("btn saffron"))
            assert 0 < page.index(label, button) - button < 400, (lang, path)
    assert CATALOG["en"]["hei.no_limit"] == "Any number of institutions of a State/UT may register."
    # the registration form: the whole sentence, not dimmed
    form = client.get("/institutions/register?lang=en").get_data(as_text=True)
    assert '<p class="hei-any-number" style="max-width:72ch"><b>Any number of institutions of a State/UT may register. The Nodal' in form


def test_no_label_while_registration_is_closed():
    app = _app(hei_open="0")
    page = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    assert "hei-no-limit" not in page


def test_the_reserve_list_in_the_list_of_its_state():
    # CICT, 12 November 2026: "The reserve list also should be added to the registered list. No separate reserve list needed",
    # chose the same table, no tag (1.2.177): the sentence of 1.2.176 under a separate list is gone with it
    from kts.db import set_setting
    from kts.i18n import CATALOG
    app = _app()
    _insert(app, "Selected Kochi College", "Kerala", "accepted", 80)
    _insert(app, "Marked Reserve College", "Kerala", "reserve", 70)
    _insert(app, "Unmarked Reserve College", "Kerala", "reserve")
    page = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    kerala = page[page.index('<h2 id="st-kerala"'):]
    kerala = kerala[:kerala.index("</table>")]
    assert re.findall(r'<td class="num">([^<]+)</td><td lang="en" dir="ltr">([^<]+)</td>', kerala) == [
        ("1", "Marked Reserve College"), ("2", "Selected Kochi College"), ("3", "Unmarked Reserve College")]
    assert '<span class="small muted">(3)</span></h2>' in kerala and "3 institutions from 1 States/UTs" in page
    assert 'id="reserve' not in page and CATALOG["en"]["hei.reserve_unmarked"] not in page and "Reserve list" not in page
    pi = page[page.index('<section class="pi"'):page.index('<p><b>')]
    assert '<div class="num">3</div><div class="lbl">Participating institutions</div>' in pi   # counted together (1.2.178)
    for lang in ("ta", "hi", "bn", "ks", "sat"):
        page = app.test_client().get(f"/institutions?lang={lang}").get_data(as_text=True)
        assert "Unmarked Reserve College" in page and CATALOG[lang]["hei.reserve_unmarked"] not in page, lang
    # the reserve list kept off the website: only the Participating Institutions
    with app.app_context():
        set_setting("hei.reserve_public", "0")
    page = app.test_client().get("/institutions?lang=en").get_data(as_text=True)
    assert "Selected Kochi College" in page and "Reserve College" not in page and "1 institutions from 1 States/UTs" in page


def test_the_two_texts_in_23_languages():
    from kts.i18n import CATALOG
    assert sorted(CATALOG) == sorted(LANGS)
    for code in LANGS:
        c = CATALOG[code]
        for key in ("hei.no_limit", "hei.reserve_unmarked"):
            assert c[key].strip() and "\n" not in c[key], (code, key)
            assert code == "en" or c[key] != CATALOG["en"][key], (code, key)
        # the label is the first sentence of the reviewed text of 1.2.174
        assert c["hei.any_number"].startswith(c["hei.no_limit"]), code

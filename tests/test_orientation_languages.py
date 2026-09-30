"""
The orientation and the test are offered in the 22 scheduled languages, Tamil among them, and in
English: 23 languages in all.

    python -m pytest tests -q
"""
import json

import pytest

from conftest import ROOT, make_app
from test_public_fixes import _register, _stored


def _codes():
    return sorted(p.stem for p in (ROOT / "data" / "i18n").glob("*.json"))


def test_tamil_is_among_the_languages():
    from kts import kural as K
    assert len(K.ORIENTATION_LANGS) == 23 == len(set(K.ORIENTATION_LANGS))
    assert K.ORIENTATION_LANGS[0] == "en" and "ta" in K.ORIENTATION_LANGS
    assert set(K.ORIENTATION_LANGS) == {"en"} | set(K.SCHEDULED)


def test_a_student_can_choose_tamil():
    app = make_app(ADMIN_PASSWORD=None)
    page = app.test_client().get("/register?lang=en").get_data(as_text=True)
    select = page.split('id="pref_lang"')[1].split("</select>")[0]
    assert select.count("<option value=") == 24      # the empty choice and the 23 languages
    assert '<option value="ta"' in select
    r = _register(app, 1, pref_lang="ta")
    assert r.status_code == 302 and _stored(app) == 1


def test_a_paper_in_tamil_can_be_drawn():
    from kts import kural as K
    rows = K.generate_questions("ta", 60, seed="tests")
    assert len(rows) >= 50 and all(r["lang"] == "ta" for r in rows)


@pytest.mark.parametrize("code", _codes())
def test_the_pages_say_22_languages(code):
    texts = json.loads((ROOT / "data" / "i18n" / f"{code}.json").read_text(encoding="utf-8"))
    for key in ("home.step_orient", "res.orient_intro", "home.orient_val", "prog.i5.t", "prog.i5.d", "agency.cict.role"):
        assert "22" in texts[key] and "21" not in texts[key], (code, key)
    assert "23" in texts["prog.i5.d"], code


def test_the_home_page_names_22_languages_and_english():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    assert "22 languages and English" in client.get("/?lang=en").get_data(as_text=True)
    page = client.get("/orientation?lang=en").get_data(as_text=True)
    assert "21 " not in page.split("<main")[1].split("</main>")[0]


def test_the_role_seeded_by_an_earlier_version_is_brought_up_to_date():
    import sqlite3
    from kts.db import RETIRED_AGENCY_ROLES
    app = make_app(ADMIN_PASSWORD=None)
    conn = sqlite3.connect(str(app.config["DATABASE"]))
    conn.execute("UPDATE agencies SET role_desc = ? WHERE code = 'CICT'", (RETIRED_AGENCY_ROLES["CICT"][0],))
    conn.execute("UPDATE agencies SET role_desc = 'Our own wording' WHERE code = 'BHU'")
    conn.commit()
    conn.close()
    again = make_app(**{name: app.config[name] for name in ("INSTANCE_DIR", "DATABASE", "UPLOAD_DIR")})
    client = again.test_client()
    page = client.get("/partners?lang=en").get_data(as_text=True)
    assert "22-language orientation" in page and "21-language" not in page and "Our own wording" in page
    # the translation of the role is found again
    from kts import i18n
    assert i18n.text("agency.cict.role", "ta") in client.get("/partners?lang=ta").get_data(as_text=True)

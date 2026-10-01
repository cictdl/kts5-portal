"""
The public page that tells the selected students how to give their bank details (/stipend).

    python -m pytest tests -q
"""
import re

import pytest
from markupsafe import escape

from conftest import make_app

KEYS = ["stip.title", "stip.intro", "stip.s1_t", "stip.s1", "stip.s2_t", "stip.s2", "stip.need_account", "stip.need_bank",
        "stip.need_proof", "stip.s3_t", "stip.s3", "stip.s4_t", "stip.s4", "stip.s5_t", "stip.s5", "stip.s6_t", "stip.s6",
        "stip.warn_t", "stip.warn_one", "stip.warn_secret", "stip.warn_help"]


def _text(key, lang="en"):
    from kts.i18n import CATALOG
    return str(escape(CATALOG[lang][key]))


def _portal(**settings):
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        for key, value in settings.items():
            set_setting(key, value)
    return app


def _page(app, path):
    r = app.test_client().get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def _on(monkeypatch, day):
    from datetime import datetime
    from kts import public, utils
    now = datetime.fromisoformat(f"{day}T10:00").replace(tzinfo=utils.IST)
    monkeypatch.setattr(utils, "now_ist", lambda: now)
    monkeypatch.setattr(public, "now_ist", lambda: now)


def test_the_page_gives_the_steps_in_order():
    page = _page(_portal(), "/stipend?lang=en")
    places = [page.index(_text(key)) for key in KEYS]
    assert places == sorted(places)
    # the title of the form, as the student will find it, follows the step that names it
    assert page.index(_text("stip.s3")) < page.index("<b>" + _text("bank.title") + "</b>") < page.index(_text("stip.s4_t"))
    assert 'href="/candidate/login"' in page and 'href="/merit-list"' in page and 'href="/status"' in page and 'href="/contact"' in page
    assert "₹10,000" in page


def test_until_the_merit_list_is_out_the_form_is_said_to_open_later():
    page = _page(_portal(**{"stipend.open": "1"}), "/stipend?lang=en")
    assert _text("stip.state_wait") in page and _text("stip.state_open") not in page
    page = _page(_portal(**{"merit.published": "1"}), "/stipend?lang=en")
    assert _text("stip.state_wait") in page


def test_the_page_says_when_the_form_is_open_and_until_when(monkeypatch):
    app = _portal(**{"merit.published": "1", "stipend.open": "1", "stipend.last_date": "2026-10-31"})
    _on(monkeypatch, "2026-10-25")
    page = _page(app, "/stipend?lang=en")
    assert _text("stip.state_open") in page and _text("bank.last_date") + ": 31 Oct 2026" in page
    assert '<a class="btn sm saffron" href="/candidate/login">' in page
    _on(monkeypatch, "2026-11-01")
    page = _page(app, "/stipend?lang=en")
    assert _text("bank.closed") in page and _text("stip.state_open") not in page
    # without a last date the form stays open
    app = _portal(**{"merit.published": "1", "stipend.open": "1", "stipend.last_date": ""})
    page = _page(app, "/stipend?lang=en")
    assert _text("stip.state_open") in page and _text("bank.last_date") not in page


def test_the_aadhaar_number_is_named_only_when_the_form_asks_for_it():
    assert _text("stip.need_aadhaar") in _page(_portal(**{"stipend.aadhaar": "1"}), "/stipend?lang=en")
    assert _text("stip.need_aadhaar") not in _page(_portal(**{"stipend.aadhaar": "0"}), "/stipend?lang=en")


def test_the_page_tells_what_the_form_asks():
    # the facts of the page are those of the form
    from kts.stipend import PROOF_MAX_BYTES
    assert PROOF_MAX_BYTES == 2 * 1024 * 1024 and "under 2 MB" in _text("stip.need_proof") and "under 2 MB" in _text("bank.proof_help")
    assert "IFSC (11 characters)" in _text("stip.need_account") and "11 characters" in _text("bank.ifsc_help")
    assert "12 digits" in _text("stip.need_aadhaar") and "12 digits" in _text("bank.aadhaar_help")
    assert "PIN, OTP" in _text("stip.warn_secret")


@pytest.mark.parametrize("lang", ["ta", "hi", "ur", "sat", "mni", "ks"])
def test_the_page_is_in_the_language_of_the_reader(lang):
    page = _page(_portal(**{"stipend.aadhaar": "1"}), f"/stipend?lang={lang}")
    for key in KEYS + ["stip.need_aadhaar", "stip.state_wait"]:
        assert _text(key, lang) != _text(key), key
        assert _text(key, lang) in page, key
    assert "<b>" + _text("bank.title", lang) + "</b>" in page


def test_the_page_is_linked_from_the_home_page_the_programme_the_footer_and_the_form():
    app = _portal()
    for path in ("/?lang=en", "/programme?lang=en", "/contact?lang=en"):
        assert 'href="/stipend"' in _page(app, path), path
    home = _page(app, "/?lang=en")
    note = home[home.index('<p class="stipend-note">'):]
    assert note.index('href="/stipend"') < note.index("</p>")
    from pathlib import Path
    form = (Path(__file__).resolve().parent.parent / "templates" / "candidate" / "bank.html").read_text(encoding="utf-8")
    assert "url_for('public.stipend_guide')" in form


def test_the_page_carries_no_script_of_its_own():
    page = _page(_portal(), "/stipend?lang=en")
    assert "<script>" not in page and not re.search(r"\son[a-z]+=", page)

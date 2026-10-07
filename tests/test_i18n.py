"""
The interface in 23 languages: every translation file is complete and in its own script, every
language offered in the menu renders the public pages, and Urdu and Kashmiri run right to left.

    python -m pytest tests -q
"""
import json
import re
from pathlib import Path

import pytest

# The `client` fixture and the throw-away database come from tests/conftest.py.
ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "data" / "i18n"
EN = json.loads((I18N / "en.json").read_text(encoding="utf-8"))
CODES = sorted(p.stem for p in I18N.glob("*.json") if p.stem != "en")
PAGES = ["/", "/about", "/programme", "/register", "/status", "/examination", "/merit-list", "/resources",
         "/thirukkural", "/thirukkural/1", "/daily-kural", "/orientation", "/notices", "/schedule", "/partners", "/gallery",
         "/contact", "/candidate/login", "/no-such-page"]


def test_twenty_three_languages():
    from kts.i18n import LANGUAGES, LANG_INFO
    assert len(LANGUAGES) == 23 and len(LANG_INFO) == 23
    assert LANG_INFO["en"]["dir"] == "ltr"
    assert {code for code, info in LANG_INFO.items() if info["dir"] == "rtl"} == {"ur", "ks"}
    from kts import kural as K
    # each interface language shows a stream of the corpus that exists
    for code, info in LANG_INFO.items():
        assert K.lang_info(info["corpus"]), code
    # the 22 languages of the Eighth Schedule and English
    assert set(LANG_INFO) == set(K.SCHEDULED) | {"en"}


@pytest.mark.parametrize("code", CODES)
def test_translation_file(code):
    import check_i18n
    errors, _warnings = check_i18n.check(code, EN)
    assert not errors, errors[:10]


@pytest.mark.parametrize("code", ["en"] + CODES)
def test_refusal_promises_no_time(code):
    """
    reg.err_rate is shown where the door opens again after 15 minutes (sign-in of the candidates,
    status page) and where it opens after an hour (registration, contact form): one sentence,
    which names no time. The marks: full stop, danda, Arabic full stop, mucaad of Ol Chiki.
    """
    value = json.loads((I18N / f"{code}.json").read_text(encoding="utf-8"))["reg.err_rate"]
    assert [ch for ch in value if ch in ".।۔᱾"] == [value[-1]], value
    assert not re.search(r"\d", value) and value == value.strip(), value
    if code == "en":
        assert value == "Too many attempts from this connection."


@pytest.mark.parametrize("code", ["en"] + CODES)
def test_pages_render(client, code):
    from kts.i18n import LANG_INFO
    r = client.get(f"/lang/{code}")
    assert r.status_code == 302
    for path in PAGES:
        r = client.get(path)
        assert r.status_code == (404 if path == "/no-such-page" else 200), (code, path)
        html = r.data.decode("utf-8")
        assert f'<html lang="{code}" dir="{LANG_INFO[code]["dir"]}"' in html, (code, path)
        # no key of the catalogue may be shown in place of its text
        leaked = re.findall(r">\s*((?:nav|site|home|common|reg|status|cand|exam|res|notices|schedule|partners|contact|about|"
                            r"programme|prog|daily|kural|admit|merit|orient|opt|q|js|err|tag|state|agency|set)\.[a-z0-9_.]+)\s*<", html)
        assert not leaked, (code, path, leaked[:5])
    client.get("/lang/en")


def test_menu_lists_every_language(client):
    from kts.i18n import available
    client.get("/lang/en")
    html = client.get("/").data.decode("utf-8")
    for info in available():
        assert f'<option value="{info["code"]}"' in html, info["code"]
        assert f'href="/lang/{info["code"]}"' in html, info["code"]
    assert client.get("/lang?code=ta", headers={"Referer": "/about"}).status_code == 302
    assert '<html lang="ta"' in client.get("/about").data.decode("utf-8")
    # a code that is not a language changes nothing
    client.get("/lang/xx")
    assert '<html lang="ta"' in client.get("/about").data.decode("utf-8")
    client.get("/lang/en")


def test_dates_need_no_translation(client):
    client.get("/lang/en")
    assert re.search(r"\d{2} [A-Z][a-z]{2} 20\d{2}", client.get("/schedule").data.decode("utf-8"))
    client.get("/lang/hi")
    html = client.get("/schedule").data.decode("utf-8")
    assert re.search(r"\d{2}-\d{2}-20\d{2}", html)
    assert not re.search(r"\d{2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) 20\d{2}", html)
    client.get("/lang/en")


def test_question_stems():
    from kts import kural as K
    from kts.i18n import CATALOG, REVIEWED, STREAM_UI, stream_text
    english = CATALOG["en"]["q.chapter"]
    assert stream_text("q.chapter", "en") == english
    for stream in ("ta", "hi"):
        assert stream_text("q.chapter", stream) == CATALOG[stream]["q.chapter"]
    # streams written in another script than the interface language keep the English stem
    for stream in ("ks", "kok", "sat", "mei", "bho"):
        assert stream_text("q.chapter", stream) == english
    # a draft language gives its own wording and the English below it
    for stream, ui in STREAM_UI.items():
        if ui and ui not in REVIEWED and CATALOG.get(ui, {}).get("q.chapter"):
            assert stream_text("q.chapter", stream) == CATALOG[ui]["q.chapter"] + "\n" + english
    rows = K.generate_questions("hi", 20, seed="t")
    assert len(rows) == 20 and all(r["text"] and r["correct"] in "ABCD" for r in rows)

"""
The recorded lectures of the online orientation (data/orientation_lectures.json, version 1.2.78): the English and
Tamil sessions on CICT's YouTube channel, on the cards of their languages on the Online orientation programme page.

    python -m pytest tests -q
"""
import json
import re
from pathlib import Path

from conftest import make_app

ROOT = Path(__file__).resolve().parents[1]
LECTURES = json.loads((ROOT / "data" / "orientation_lectures.json").read_text(encoding="utf-8"))
CARD = {"en": ">English</bdi>", "ta": ">தமிழ்</bdi>"}


def test_the_list_of_lectures():
    assert [(r["lang"], r["session"], r["youtube"]) for r in LECTURES] == [
        ("en", 1, "2w6mgosRYAE"), ("en", 2, "Z3fGrbHLFr8"), ("ta", 1, "tL9j8Dz7LLw")]
    assert [r["title"] for r in LECTURES] == ["Session 01 · Thirukkural and Thiruvalluvar",
                                              "Session 02 · Insights from the Thirukkural",
                                              "பாடம் 01 · திருக்குறள் மற்றும் திருவள்ளுவர்"]
    from kts import kural as K
    for row in LECTURES:
        assert re.fullmatch(r"[A-Za-z0-9_-]{11}", row["youtube"]) and row["lang"] in K.ORIENTATION_LANGS


def test_each_card_shows_the_lectures_of_its_language():
    from kts.i18n import CATALOG
    app = make_app(ADMIN_PASSWORD=None)
    for lang in ("en", "ta", "hi"):
        page = app.test_client().get(f"/orientation?lang={lang}").get_data(as_text=True)
        cards = page.split('<div class="card">')[1:]
        with_lectures = []
        for code, heading in CARD.items():
            card = next(c for c in cards if heading in c)
            with_lectures.append(card)
            for row in (r for r in LECTURES if r["lang"] == code):
                assert (f'<a href="https://www.youtube.com/watch?v={row["youtube"]}" target="_blank" rel="noopener">'
                        f'<span aria-hidden="true">▶</span> <bdi lang="{code}">{row["title"]}</bdi></a>') in card, (lang, code)
        english = with_lectures[0]
        assert english.index("2w6mgosRYAE") < english.index("Z3fGrbHLFr8") and "tL9j8Dz7LLw" not in english
        # these cards no longer say that their sessions are yet to be scheduled; the other cards still do
        tbs = CATALOG[lang]["orient.tbs"]
        assert all(tbs not in c for c in with_lectures)
        assert all(tbs in c for c in cards if not any(c is w for w in with_lectures)), lang

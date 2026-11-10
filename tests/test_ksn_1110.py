"""
The Kashmiri Thirukkural in the Perso-Arabic script (stream ksn), couplets 224 to 252 (1.2.170, 10 November 2026).

The repair of 28 September (tools/fix_ksn_alignment.py, step 1) moved every entry from 94 on one couplet back. From 224 to 252
the data had been in place, so those couplets showed the translation of the next one: under 224 the ascetic and the one who
relieves hunger (225), under 249 the strong over the weak (250), under 251 a second version of 252. Three of them are among the
108 of the test (226, 231, 241). Step 2 puts them back and leaves 224, which the data does not have, to the English.

    python -m pytest tests/test_ksn_1110.py -q
"""
import json
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

from markupsafe import escape

from conftest import make_app

ROOT = Path(__file__).resolve().parents[1]
MARK = json.loads((ROOT / "data" / "kurals" / "ksn-repair.json").read_text(encoding="utf-8"))
# words of each couplet's own translation: the poor fed (226), the gift to the poor (231), the weak (250), meat (251, 252)
WORDS = {225: "ضبطِ نفس", 226: "غریٖبن", 231: "غریٖبس عطیہ", 250: "کمزورس", 251: "جانور ماز", 252: "فضوٗل خرچی"}


def _text(n):
    from kts import kural as K
    return " ".join(K.lines(K.kural(n), "ksn"))


def test_the_couplets_are_in_place():
    from kts import kural as K
    assert K.lines(K.kural(224), "ksn") == [] and K.lines(K.kural(1330), "ksn") == []
    for n, words in WORDS.items():
        assert words in _text(n), n
        assert words not in _text(n - 1), n
    # the neighbours of 223 and 253 are as they were; no verse is in the stream twice, and the second version of 252 is out
    assert _text(223).startswith("بہٕ چھُس غریٖب") and "مارن وٲلِس" in _text(253)
    verses = [tuple(K.lines(K.kural(n), "ksn")) for n in range(1, 1331) if K.lines(K.kural(n), "ksn")]
    assert len(set(verses)) == len(verses) == 1328
    assert tuple(MARK["second"]["taken_out"]["text"]) not in verses
    # every other couplet keeps a text
    assert [n for n in range(1, 1331) if not K.lines(K.kural(n), "ksn")] == [224, 1330]


def test_the_repair_is_recorded_once():
    from kts import kural as K
    assert MARK["repaired"] == "entries 94 to 1330 moved to couplets 93 to 1329" and MARK["without_text"] == [1330]
    second = MARK["second"]
    assert second["repaired"] == "entries 224 to 250 moved to couplets 225 to 251" and second["without_text"] == [224]
    taken = second["taken_out"]
    assert (taken["entry"], taken["second_version_of"]) == (251, 252)
    assert SequenceMatcher(None, " ".join(taken["text"]), _text(252)).ratio() > 0.6
    assert K.lines(K.kural(252), "ksn") != taken["text"]


def test_the_pages():
    from kts import kural as K
    client = make_app(ADMIN_PASSWORD=None).test_client()
    # the page of a couplet: 226 in Kashmiri as its own; 224 without a Kashmiri block in the Perso-Arabic script
    page = client.get("/thirukkural/226?lang=en").get_data(as_text=True)
    assert str(escape(K.lines(K.kural(226), "ksn")[0])) in page
    main = client.get("/thirukkural/224?lang=en").get_data(as_text=True).split("<main", 1)[1].split("</main>")[0]
    assert 'lang="ks-Arab"' not in main and 'lang="ks-Deva"' in main
    # the Kural of the day for 224 (12 August 2026 in its cycle) falls back to the English
    assert K.daily_number(date(2026, 8, 12)) == 224
    page = client.get("/daily-kural?d=2026-08-12&l=ksn").get_data(as_text=True)
    assert str(escape(" ".join(K.lines(K.kural(224), "en")))) in " ".join(page.replace("<br>", " ").split())

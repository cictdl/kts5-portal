"""
The credits of the portal (version 1.2.83): under "Implementing institute" at the foot of every page, the five CICT staff
who developed the portal and its content (data/credits.json), with their designations and their roles in KTS 5.0, in
English in every language, with their e-mail addresses as they are (1.2.103; name[dot]x[at]cict[dot]in before).
And pages in long-worded languages fit a phone: the links of the footer and the tiles of the home page wrap.

    python -m pytest tests -q
"""
import json
from pathlib import Path

from markupsafe import escape

from conftest import make_app

ROOT = Path(__file__).resolve().parents[1]
CREDITS = json.loads((ROOT / "data" / "credits.json").read_text(encoding="utf-8"))


def test_the_people():
    assert [(c["name"], c["designation"], c["role"]) for c in CREDITS] == [
        ("Dr. Devi N", "Research Officer, CICT", "Content Developer (Academic)"),
        ("Dr. Periasamy N", "Junior Research Officer, CICT", "Content Developer (Academic)"),
        ("Shri S. Karthikeyan", "Programmer, CICT", "Content Developer (Technical & Visual)"),
        ("Dr. Akilan Rajarethinam", "Programmer, CICT", "Content Developer (Technical & Visual)"),
        ("Shri K. Kannan", "Junior Resource Person, CICT", "KTS 5.0 Portal Development & Administration")]
    assert [c["email"] for c in CREDITS] == ["devi.n@cict.in", "periasamy.n@cict.in", "karthikeyan.s@cict.in", "akilan.r@cict.in",
                                              "kannan.k@cict.in"]


def test_the_foot_of_every_page_in_every_language():
    from kts.i18n import CATALOG
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for code, catalogue in CATALOG.items():
        for path in ("/", "/about", "/resources"):
            page = client.get(f"{path}?lang={code}").get_data(as_text=True)
            foot = page[page.index('<footer class="site">'):]
            column = foot[foot.index(f"<h4>{escape(catalogue['site.coordinating'])}</h4>"):]
            column = column[:column.index("</div>")]
            assert f'<h4 class="credits-h">{escape(catalogue["cr.title"])}</h4>' in column, (code, path)
            assert '<ul class="credits" lang="en" dir="ltr">' in column
            for c in CREDITS:
                assert (f'<li><b>{escape(c["name"])}</b>, {escape(c["designation"])}<br><span class="cr-role">{escape(c["role"])}</span>'
                        f'<br><span class="cr-mail">{c["email"]}</span></li>') in column, (code, c["name"])
            # the addresses as they are, kannan.k@cict.in: no [dot] or [at] left on the page
            assert "[dot]" not in page and "[at]" not in page, (code, path)


def test_long_words_wrap_on_a_phone():
    styles = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    assert "footer.site .langs ul { flex: 1 1 16rem; }" in styles
    assert "@media (max-width: 599px) { .nodal-attention .na-btn { white-space: normal; max-width: 100%; } }" in styles
    assert ".date-tile { min-width: 0; overflow-wrap: anywhere; }" in styles

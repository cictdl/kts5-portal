"""
The chapter list of the Thirukkural browser: one chapter a line beside the couplets, and a layout
that the style sheet can change on phones (no column widths written into the page).

    python -m pytest tests -q
"""
import re

from conftest import ROOT


def test_the_list_has_every_chapter_with_its_number(client):
    page = client.get("/thirukkural?ch=49&lang=ta").get_data(as_text=True)
    items = re.findall(r'<a href="[^"]*" class="(on)?"><span class="no">(\d+)\.</span><span class="ta" lang="ta">[^<]+</span></a>', page)
    assert [int(n) for _on, n in items] == list(range(1, 134))
    assert [n for on, n in items if on] == ["49"]


def test_the_layout_is_left_to_the_style_sheet(client):
    page = client.get("/thirukkural?lang=en").get_data(as_text=True)
    assert 'class="two-col kural-layout"' in page
    assert "grid-template-columns" not in page


def test_the_style_sheet_keeps_the_names_whole():
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    rule = re.search(r"\n\.chapter-list \{([^}]*)\}", css).group(1)
    assert "max-height" in rule and "overflow-y: auto" in rule and "columns" not in rule
    assert re.search(r"@media \(max-width: 899px\) \{ \.two-col\.kural-layout \{ grid-template-columns: minmax\(0, 1fr\); \} \}", css)

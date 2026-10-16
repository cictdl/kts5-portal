"""
The seminars and workshops of CICT in the Digital repository (version 1.2.83): a page of its own (/seminars-workshops) from
data/cict_events.json, year by year, newest first, with filters by year, by kind and by words; each event links to CICT's
own announcements, invitations, recordings and reports. A card at the top of the repository and the sitemap lead to it.

    python -m pytest tests -q
"""
import json
import re
from pathlib import Path

from markupsafe import escape

from conftest import make_app

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "data" / "cict_events.json").read_text(encoding="utf-8"))
EVENTS = DATA["events"]
DAY = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def _client():
    return make_app(ADMIN_PASSWORD=None).test_client()


def _page(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def test_the_data():
    from kts.public import EV_LINKS, EV_MODES, EV_TYPES
    assert len(EVENTS) >= 150
    ids = [e["id"] for e in EVENTS]
    assert len(ids) == len(set(ids)) and all(re.fullmatch(r"[a-z0-9-]+", i) for i in ids)
    for e in EVENTS:
        assert e["type"] in EV_TYPES, e["id"]
        assert DAY.match(e["start"]) and "2005" <= e["start"][:4] <= "2026", e["id"]
        if e.get("end"):
            assert DAY.match(e["end"]) and e["end"] >= e["start"], e["id"]
        assert e.get("title") or e.get("title_ta"), e["id"]
        assert not e.get("mode") or e["mode"] in EV_MODES, e["id"]
        assert e.get("serial") is None or isinstance(e["serial"], int), e["id"]
        for link in e.get("links", []):
            assert link["kind"] in EV_LINKS and link["url"].startswith("https://"), (e["id"], link)
        for text in [e.get("title_ta") or ""] + list(e.get("people") or []):
            assert "‌" not in text, e["id"]                      # no stray marks of the OCR


def test_the_page_in_every_language():
    from kts.i18n import CATALOG
    client = _client()
    for code, catalogue in CATALOG.items():
        page = _page(client, f"/seminars-workshops?lang={code}&y=all")
        assert f"<h1>{escape(catalogue['ev.title'])}</h1>" in page, code
        assert str(escape(catalogue["ev.count"].replace("{n}", str(len(EVENTS))))) in page, code
        assert page.count('<li class="ev" id="') == len(EVENTS), code
    page = _page(client, "/seminars-workshops?lang=en&y=all")
    # newest first, a heading for each year
    years = re.findall(r'<section class="ev-year" id="y(\d{4})">', page)
    assert years == sorted(set(years), reverse=True) and years[0] == max(e["start"][:4] for e in EVENTS)
    # the links open CICT's documents in a new tab
    for e in EVENTS[:20]:
        for link in e.get("links", []):
            assert f'href="{escape(link["url"])}" target="_blank" rel="noopener"' in page, e["id"]


def test_the_page_opens_on_the_latest_year():
    client = _client()
    latest = max(e["start"][:4] for e in EVENTS)
    page = _page(client, "/seminars-workshops?lang=en")
    assert re.findall(r'<section class="ev-year" id="y(\d{4})">', page) == [latest]
    assert page.count('<li class="ev" id="') == sum(e["start"][:4] == latest for e in EVENTS)
    # a pill for every year with its count, and one for all of them
    years = sorted({e["start"][:4] for e in EVENTS}, reverse=True)
    for y in years:
        assert f'<a href="/seminars-workshops?y={y}" class="{"on" if y == latest else ""}">{y} <span class="muted">' \
               f'{sum(e["start"][:4] == y for e in EVENTS)}</span></a>' in page, y
    assert f'<a href="/seminars-workshops?y=all" class="">All <span class="muted">{len(EVENTS)}</span></a>' in page
    # words or a kind look in every year
    assert len(re.findall(r'<section class="ev-year"', _page(client, "/seminars-workshops?lang=en&k=workshop"))) > 1
    assert _page(client, "/seminars-workshops?lang=en&y=1999").count('<li class="ev"') == page.count('<li class="ev"')


def test_the_filters():
    client = _client()
    year = EVENTS[0]["start"][:4]
    page = _page(client, f"/seminars-workshops?lang=en&y={year}")
    assert page.count('<li class="ev" id="') == sum(e["start"][:4] == year for e in EVENTS)
    assert re.findall(r'<section class="ev-year" id="y(\d{4})">', page) == [year]
    page = _page(client, "/seminars-workshops?lang=en&k=workshop")
    assert page.count('<li class="ev" id="') == sum(e["type"] == "workshop" for e in EVENTS)
    page = _page(client, "/seminars-workshops?lang=en&q=brahmi")
    found = page.count('<li class="ev" id="')
    fields = ("title", "title_ta", "venue", "with", "dept")
    assert found == sum("brahmi" in (" ".join(e.get(f) or "" for f in fields) + " " + " ".join(e.get("people") or [])).casefold()
                        for e in EVENTS) and found >= 1
    page = _page(client, "/seminars-workshops?lang=ta&q=zzzzzz")
    assert '<li class="ev"' not in page


def test_the_dates_as_the_portal_writes_them():
    from kts.public import _ev_when
    assert _ev_when({"start": "2026-10-07", "end": "2026-10-13"}, False) == "07–13 Oct 2026"
    assert _ev_when({"start": "2026-10-07", "end": "2026-10-13"}, True) == "07-10-2026 – 13-10-2026"
    assert _ev_when({"start": "2025-12-29", "end": "2026-01-02"}, False) == "29 Dec 2025 – 02 Jan 2026"
    assert _ev_when({"start": "2026-03-08", "end": ""}, False) == "08 Mar 2026"
    assert _ev_when({"start": "2012-02"}, False) == "Feb 2012" and _ev_when({"start": "2012-02"}, True) == "02-2012"
    assert _ev_when({"start": "2010"}, True) == "2010"


def test_the_repository_and_the_sitemap_lead_to_it():
    from kts.i18n import CATALOG
    client = _client()
    for code, catalogue in CATALOG.items():
        page = _page(client, f"/resources?lang={code}")
        assert (f'<a class="card accent res-card" href="/seminars-workshops"><span class="cat">{escape(catalogue["ev.type_workshop"])} · '
                f'{escape(catalogue["ev.type_seminar"])}</span><h3>{escape(catalogue["ev.title"])}</h3>') in page, code
    page = _page(client, "/sitemap?lang=en")
    assert 'href="/seminars-workshops"' in page


def test_long_lists_of_speakers_fold():
    client = _client()
    e = max(EVENTS, key=lambda e: len(e.get("people") or []))
    assert len(e["people"]) > 8
    page = _page(client, f"/seminars-workshops?lang=en&y={e['start'][:4]}")
    item = page[page.index(f'<li class="ev" id="{e["id"]}">'):]
    item = item[:item.index("</li>")]
    assert f'<details class="ev-more"><summary>+{len(e["people"]) - 8}</summary>' in item
    assert item.count("<bdi>") >= len(e["people"])


def test_links_are_named_by_their_site():
    for e in EVENTS:
        kinds = [l["kind"] for l in e.get("links", [])]
        assert kinds.count("post") <= 2 and kinds.count("video") <= 6, e["id"]
        for l in e.get("links", []):
            if l["kind"] == "post":
                assert l.get("label") in ("X", "Facebook", "Instagram", "LinkedIn", "Threads", "Telegram"), (e["id"], l)

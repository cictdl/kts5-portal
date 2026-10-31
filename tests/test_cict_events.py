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
# the events shown: from 2020 on (1.2.87); those of 2005-2019 stay in the file
EVENTS = [e for e in DATA["events"] if e["start"][:4] >= "2020"]
DAY = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def _client():
    return make_app(ADMIN_PASSWORD=None).test_client()


def _page(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def test_the_data():
    from kts.public import EV_LINKS, EV_MODES, EV_TYPES
    assert len(EVENTS) >= 150 and len(DATA["events"]) > len(EVENTS)
    ids = [e["id"] for e in EVENTS]
    assert len(ids) == len(set(ids)) and all(re.fullmatch(r"[a-z0-9-]+", i) for i in ids)
    for e in DATA["events"]:
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


SITES = ("X", "Facebook", "Instagram", "YouTube", "LinkedIn", "Threads", "Telegram")


def test_links_are_named_by_their_site():
    # a post is on social media and names its site; a link to social media is a video, photographs or a post (1.2.128)
    from kts.public import _ev_site
    for e in EVENTS:
        urls = [l["url"].rstrip("/") for l in e.get("links", [])]
        assert len(urls) == len(set(urls)), e["id"]
        for l in e.get("links", []):
            if l["kind"] == "post":
                assert l.get("label") in SITES, (e["id"], l)
            if _ev_site(l["url"]):
                assert l["kind"] in ("video", "photos", "post") and l.get("label") in SITES, (e["id"], l)


def test_the_photographs_and_videos_of_an_event_stand_apart():
    # the links to social media in a row of their own, videos first, each named by its kind and site; six are shown and the
    # others open on a click (1.2.128); CICT's own documents stay buttons
    from kts.public import _ev_site
    client = _client()
    page = _page(client, "/seminars-workshops?lang=en&y=all")
    many = [e for e in EVENTS if sum(1 for l in e.get("links", []) if _ev_site(l["url"])) > 6]
    for e in EVENTS:
        start = page.index(f'<li class="ev" id="{e["id"]}">')
        item = page[start:page.index("</li>", start)]
        media = [l for l in e.get("links", []) if _ev_site(l["url"])]
        docs = [l for l in e.get("links", []) if not _ev_site(l["url"])]
        assert item.count('class="ev-chip"') == len(media) and item.count('class="btn xs secondary"') == len(docs), e["id"]
        if media:
            row = item[item.index('<div class="ev-media small">'):]
            assert row.startswith('<div class="ev-media small"><b>Photos and videos on social media:</b> ')
            kinds = [k for k in __import__("re").findall(r'</span> (Video|Photographs|Social media post) · <bdi>', row)]
            order = {"Video": 0, "Photographs": 1, "Social media post": 2}
            assert kinds == sorted(kinds, key=order.get), e["id"]
            assert ("<summary>+" in row) == (len(media) > 6), e["id"]
        else:
            assert "ev-media" not in item, e["id"]
    if many:
        e = many[0]
        start = page.index(f'<li class="ev" id="{e["id"]}">')
        item = page[start:page.index("</li>", start)]
        n = sum(1 for l in e["links"] if _ev_site(l["url"]))
        assert f'<details class="ev-more"><summary>+{n - 6}</summary>' in item
    # in Tamil, the row has its Tamil heading
    assert "சமூக ஊடகங்களில் புகைப்படங்களும் காணொளிகளும்:" in _page(client, "/seminars-workshops?lang=ta&y=all")


def test_the_main_menu_and_the_home_page_lead_to_it():
    from kts.i18n import CATALOG
    client = _client()
    years = sorted(e["start"][:4] for e in EVENTS)
    for code, catalogue in CATALOG.items():
        page = _page(client, f"/?lang={code}")
        menu = page.split('id="primary-menu"')[1].split("</nav>")[0]
        resources = menu[menu.index('<li class="has-sub"><a href="/resources"'):]
        resources = resources[:resources.index("</ul></li>")]
        assert f'<li><a href="/resources">{escape(catalogue["res.title"])}</a></li>' in resources, code
        assert f'<li><a href="/seminars-workshops">{escape(catalogue["ev.title"])}</a></li>' in resources, code
        card = page[page.index('<a class="card accent ev-home-card" href="/seminars-workshops">'):]
        card = card[:card.index("</a>")]
        assert f'<h2 id="ev-home-title">{escape(catalogue["ev.title"])}' in card, code
        assert (f'<span class="ev-home-n"><bdi dir="ltr">{years[0]}–{years[-1]}</bdi> · '
                f'{escape(catalogue["ev.count"].replace("{n}", str(len(EVENTS))))}</span>') in card, code
    # the menu marks the page as the one open
    page = _page(client, "/seminars-workshops?lang=en")
    assert '<li class="has-sub"><a href="/resources" class="active" aria-haspopup="true">' in page


def test_the_years_before_2020_are_not_shown():
    from kts.public import EV_SHOWN_FROM
    assert EV_SHOWN_FROM == "2020"
    hidden = [e for e in DATA["events"] if e["start"][:4] < "2020"]
    assert hidden
    client = _client()
    page = _page(client, "/seminars-workshops?lang=en&y=all")
    assert page.count('<li class="ev" id="') == len(EVENTS)
    for e in hidden[:50]:
        assert f'id="{e["id"]}"' not in page, e["id"]
    for y in sorted({e["start"][:4] for e in hidden}):
        assert f'?y={y}"' not in page and f'id="y{y}"' not in page, y
        # a year that is not shown opens the latest year
        assert _page(client, f"/seminars-workshops?lang=en&y={y}").count('<li class="ev"') == \
            sum(e["start"][:4] == max(x["start"][:4] for x in EVENTS) for e in EVENTS)
    home = _page(client, "/?lang=en")
    assert '<span class="ev-home-n"><bdi dir="ltr">2020–' in home


def test_month_by_month_in_each_year():
    # 1.2.106: in each year a row of its months with their counts, then a heading for each month, newest first; every
    # event under the month in which it began
    from kts.i18n import CATALOG
    client = _client()
    page = _page(client, "/seminars-workshops?lang=en&y=all")
    for year in sorted({e["start"][:4] for e in EVENTS}, reverse=True):
        start = page.index(f'<section class="ev-year" id="y{year}">')
        end = page.find('<section class="ev-year"', start + 1)
        section = page[start:end if end > 0 else len(page)]
        months = re.findall(r'<section class="ev-month" id="m(\d{4}-\d{2})"', section)
        expected = sorted({e["start"][:7] for e in EVENTS if e["start"][:4] == year}, reverse=True)
        assert months == expected, year
        for key in months:
            block = section[section.index(f'id="m{key}"'):]
            block = block[:block.index("</ol>")]
            ids = re.findall(r'<li class="ev" id="([^"]+)">', block)
            assert ids and all(next(e for e in EVENTS if e["id"] == i)["start"][:7] == key for i in ids), key
            n = len(ids)
            name = CATALOG["en"][f"month.{int(key[5:])}"]
            assert (f'<h3 class="ev-month-h" id="m{key}-h">{name} {year} <span class="muted ev-n">'
                    f'{"1 event" if n == 1 else f"{n} events"}</span></h3>') in block, key
            if len(months) > 1:
                assert f'<a href="#m{key}">{name} <span class="muted">{n}</span></a>' in section, key
    # the event titles are headings below the months
    assert page.count('<h4 class="ev-title">') == len(EVENTS) and '<h3 class="ev-title">' not in page
    # in Tamil the months are named in Tamil
    tamil = _page(client, "/seminars-workshops?lang=ta&y=2026")
    assert '<h3 class="ev-month-h" id="m2026-10-h">அக்டோபர் 2026 <span class="muted ev-n">' in tamil
    assert '<a href="#m2026-09">செப்டம்பர் <span class="muted">' in tamil


def test_the_names_of_the_months_in_every_language():
    from kts.i18n import CATALOG
    for code, catalogue in CATALOG.items():
        names = [catalogue[f"month.{i}"] for i in range(1, 13)]
        assert len(set(names)) == 12 and all(n.strip() == n and n for n in names), code
        if code != "en":
            assert not any(n == CATALOG["en"][f"month.{i + 1}"] for i, n in enumerate(names)), code


def test_the_workshop_and_the_note_added_on_27_october():
    # 1.2.113: the workshop "Heritage of Tamil Medicine" (no. 144 of the series) from CICT's inaugural invitation, the
    # newest event; the Tamil note on KTS 5.0 of CICT's Tamil list beside the English one
    e = DATA["events"][0]
    assert e["id"] == "2026-10-27-heritage-of-tamil-medicine" and e["serial"] == 144 and e["end"] == "2026-11-05"
    assert DATA["updated"] == "2026-10-31"  # the social media pass of 1.2.131
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = _page(client, "/seminars-workshops?lang=en&y=2026")
    assert page.index("Heritage of Tamil Medicine") < page.index("Seminar Commemorating Tirumular Day")
    assert 'href="https://cict.in/cict2023/wp-content/uploads/2026/10/26.10.2026.jpeg"' in page
    assert "Prof. Dr. K. Balagurusamy MD(S)" in page
    assert "தமிழ் மருத்துவ மரபுகள்" in _page(client, "/seminars-workshops?lang=ta&y=2026")
    kts = next(x for x in DATA["events"] if x["id"] == "2026-10-kashi-tamil-sangamam-5-0-thirukkural")
    assert [l["label"] for l in kts["links"] if l["kind"] == "report"] == ["cict.in", "cict.in · தமிழ்"]
    assert "<bdi>cict.in · தமிழ்</bdi>" in page

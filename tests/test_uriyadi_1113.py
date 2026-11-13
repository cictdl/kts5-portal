"""
குறள் உறியடி · Kural Uriyadi, CICT's game of the missing word of a kural, served by the portal itself (/static/uriyadi/), and the
students' game Valluvar's Pond as an entry of the repository (1.2.184; CICT, 13 November 2026: "Kural Uriyadi add in the KTS portal"
and, of https://adhavan18.github.io/valluvar-pond/, "add this also").

The game carries its own copy of the couplets and the translations (a page of static files reads no other data of the portal): the
tests of the couplets and of the translations fail when data/kurals changes, and the game's data is then to be built again
(build/build_data.py of the game, and VERSION of static/uriyadi/sw.js raised).

Its couplets lie in static/uriyadi/corpus/ since 1.2.185: the web server (IIS, web.config) answers 404 for every address with a
part named "data", and the game of 1.2.184, with static/uriyadi/data/, could not read them on the live site. The last test keeps
every static file clear of the names and the extensions the web server hides.

    python -m pytest tests/test_uriyadi_1113.py -q
"""
import json
import re

from conftest import ROOT, make_app

GAME = ROOT / "static" / "uriyadi"
CORPUS = GAME / "corpus"
URL = "/static/uriyadi/index.html"
POND = "https://adhavan18.github.io/valluvar-pond/"
TAMIL = re.compile(r"[^஀-௿]")


def _rows(app):
    from kts.db import query
    with app.app_context():
        return {r["url"]: dict(r) for r in query("SELECT * FROM resources")}


def test_the_two_entries_of_the_repository():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    rows = _rows(app)
    game, pond = rows[URL], rows[POND]
    assert (game["title"], game["category"], game["featured"], game["published"]) == ("குறள் உறியடி · Kural Uriyadi", "app", 1, 1)
    assert (pond["title"], pond["category"], pond["featured"], pond["published"]) == ("வள்ளுவர் குளம் · Valluvar's Pond", "app", 0, 1)
    # the students' game is said to be theirs
    assert "made by students" in pond["description"] and "not an official release of CICT" in pond["description"]
    assert "about 42 MB" in pond["description"]
    r = client.get(f"/resources/{game['id']}")
    assert r.status_code == 302 and r.headers["Location"] == URL
    r = client.get(f"/resources/{pond['id']}")
    assert r.status_code == 302 and r.headers["Location"] == POND
    page = client.get("/resources?cat=app&lang=en").get_data(as_text=True)
    assert "குறள் உறியடி · Kural Uriyadi" in page and "வள்ளுவர் குளம் · Valluvar&#39;s Pond" in page
    # on the home page: CICT's own game among the six featured entries, the students' game in the repository only
    home = client.get("/?lang=en").get_data(as_text=True)
    assert f'href="/resources/{game["id"]}"' in home and f'href="/resources/{pond["id"]}"' not in home


def test_the_game_is_served_by_the_portal_itself():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get(URL)
    assert page.status_code == 200 and page.mimetype == "text/html"
    html = page.get_data(as_text=True)
    assert "<title>குறள் உறியடி · Kural Uriyadi</title>" in html
    # the policy of the portal stands on the page, and nothing is loaded from another host
    assert "script-src 'self'" in page.headers["Content-Security-Policy"]
    assert re.findall(r'<script src="([^"]+)"></script>', html) == ["app.js"]
    assert "<script>" not in html and "<style" not in html and not re.search(r"\son[a-z]+=", html)
    for host in ("googleapis", "gstatic", "jsdelivr", "http://", "https://"):
        assert host not in html, host
    # the files the service worker keeps for the next visit are all there
    sw = client.get("/static/uriyadi/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.mimetype
    shell = re.search(r"const SHELL_URLS = \[(.*?)\];", sw.get_data(as_text=True), re.S).group(1)
    urls = re.findall(r"'\./([^']+)'", shell)
    assert "index.html" in urls and "app.js" in urls and "corpus/meta.json" in urls and len(urls) >= 10
    for name in urls + ["assets/apple-touch-icon.png", "assets/icon-maskable-512.png", "corpus/ch/001.json", "corpus/tr/en.json"]:
        r = client.get("/static/uriyadi/" + name)
        assert r.status_code == 200 and len(r.data) > 300, name
        r.close()
    manifest = json.loads(client.get("/static/uriyadi/manifest.json").get_data(as_text=True))
    assert manifest["start_url"] == "./index.html" and manifest["scope"] == "./"
    assert all((GAME / icon["src"]).is_file() for icon in manifest["icons"])
    # every font of the stylesheet is in the folder; the script reaches other hosts only by links the player opens
    css = (GAME / "assets" / "fonts.css").read_text(encoding="utf-8")
    fonts = re.findall(r"url\(([^)]+)\)", css)
    assert len(fonts) >= 40 and all((GAME / "assets" / f).is_file() for f in fonts) and "http" not in css
    script = (GAME / "app.js").read_text(encoding="utf-8")
    assert re.findall(r"https?://[^'\"\s)]+", script) == ["https://cictdl.github.io/index.html/kural-app/#/k/"]
    assert "fetch(url)" in script and "eval(" not in script and "innerHTML" not in script


def test_the_couplets_of_the_game_are_those_of_the_portal():
    meta = json.loads((CORPUS / "meta.json").read_text(encoding="utf-8"))
    assert len(meta["chapters"]) == 133 and [c["n"] for c in meta["chapters"]] == list(range(1, 134))
    k108 = sorted(int(r["n"]) for r in json.loads((ROOT / "data" / "kural108.json").read_text(encoding="utf-8")))
    assert meta["k108"] == k108 and len(k108) == 108
    seen = 0
    for n in range(1, 134):
        portal = json.loads((ROOT / "data" / "kurals" / f"{n:03d}.json").read_text(encoding="utf-8"))
        game = json.loads((CORPUS / "ch" / f"{n:03d}.json").read_text(encoding="utf-8"))
        assert game["n"] == n and (meta["chapters"][n - 1]["start"], meta["chapters"][n - 1]["end"]) == (portal["start"], portal["end"])
        assert [k["n"] for k in game["kurals"]] == [int(k["n"]) for k in portal["kurals"]]
        for mine, theirs in zip(game["kurals"], portal["kurals"]):
            seen += 1
            lines = [theirs["l1"].strip(), theirs["l2"].strip()]
            assert mine["l"] == lines, mine["n"]
            # the words: those of the two lines, four and three, without their marks
            words = [(TAMIL.sub("", tok), i) for i, line in enumerate(lines, 1) for tok in line.split()]
            assert [(w[0], w[1]) for w in mine["w"]] == words and len(words) == 7, mine["n"]
            assert all(len(w) == 4 and w[0] for w in mine["w"]), mine["n"]
    assert seen == 1330


def test_the_translations_of_the_game_are_those_of_the_portal():
    meta = json.loads((CORPUS / "meta.json").read_text(encoding="utf-8"))
    codes = [s["code"] for s in meta["streams"]]
    assert len(codes) == 26 and codes[:2] == ["tac", "en"] and {"hi", "bn", "ur", "ksn", "mei", "sat"} <= set(codes)
    assert sorted(p.stem for p in (CORPUS / "tr").glob("*.json")) == sorted(codes)
    game = {code: json.loads((CORPUS / "tr" / f"{code}.json").read_text(encoding="utf-8")) for code in codes}
    for n in range(1, 134):
        for k in json.loads((ROOT / "data" / "kurals" / f"{n:03d}.json").read_text(encoding="utf-8"))["kurals"]:
            for code in codes:
                t = (k.get("tr") or {}).get(code)
                if t:
                    want = [str(x or "").strip() for x in (t if isinstance(t, list) else [t])]
                    assert game[code].get(str(k["n"])) == want, (code, k["n"])
                else:
                    assert str(k["n"]) not in game[code], (code, k["n"])
    for s in meta["streams"]:
        assert s["count"] == len(game[s["code"]]) >= 1300, s["code"]


def test_no_static_file_has_an_address_the_web_server_hides():
    """IIS answers 404 for an address with a hidden part (hiddenSegments: data, lib, kts, templates ...) or a refused extension,
    wherever it stands in the address. The other tests ask the application itself and cannot see it: found on the live site on
    13 November 2026, where /static/uriyadi/data/... was not to be read (1.2.185)."""
    import xml.etree.ElementTree as ET
    hidden, refused = set(), set()
    for name in ("web.config", "deploy/web.config.template"):
        tree = ET.parse(ROOT / name)
        hidden |= {e.get("segment").lower() for e in tree.iter("add") if e.get("segment")}
        refused |= {e.get("fileExtension").lower() for e in tree.iter("add") if e.get("fileExtension") and e.get("allowed") == "false"}
    assert {"data", "kts", "lib", "uploads", "instance"} <= hidden and ".py" in refused
    files = [p for p in (ROOT / "static").rglob("*") if p.is_file()]
    assert len(files) > 400
    bad = [str(p.relative_to(ROOT)) for p in files
           if {part.lower() for part in p.relative_to(ROOT).parts} & hidden or p.suffix.lower() in refused]
    assert not bad, bad[:10]
    # and the addresses the game asks for by name: in corpus/ and assets/, never in data/
    script = (GAME / "app.js").read_text(encoding="utf-8") + (GAME / "sw.js").read_text(encoding="utf-8")
    asked = set(re.findall(r"[`'](?:\./)?(corpus|assets|data)/", script))
    assert asked == {"corpus", "assets"}, asked
    assert (CORPUS / "meta.json").is_file() and not (GAME / "data").exists()

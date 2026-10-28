"""
The Tolkappiyam recordings (version 1.2.116): 29 files, the introduction, the பாயிரம் and the 27 இயல்கள் of the three
அதிகாரங்கள், that other sites and apps stream from the portal (static/audio/tolkappiyam-055ece6df3/). The folder is
unlisted: no page, script, sitemap or search result names it, and search engines are asked not to list its files.

    python -m pytest tests -q
"""
import re

from conftest import ROOT, make_app

FOLDER = ROOT / "static" / "audio" / "tolkappiyam-055ece6df3"
URL = "/static/audio/tolkappiyam-055ece6df3/"
NAMES = [
    "001-munnurai.mp3",
    "002-payiram.mp3",
    "003-eluttu-noon-marabu.mp3",
    "004-eluttu-mozhi-marabu.mp3",
    "005-eluttu-pirappiyal.mp3",
    "006-eluttu-punariyal.mp3",
    "007-eluttu-thokai-marabu.mp3",
    "008-eluttu-urubiyal.mp3",
    "009-eluttu-uyir-mayangiyal.mp3",
    "010-eluttu-pulli-mayangiyal.mp3",
    "011-eluttu-kutriyalugarap-punariyal.mp3",
    "012-col-kilaviyakkam.mp3",
    "013-col-vetrumaiyiyal.mp3",
    "014-col-vetrumai-mayangiyal.mp3",
    "015-col-vili-marabu.mp3",
    "016-col-peyariyal.mp3",
    "017-col-vinaiyiyal.mp3",
    "018-col-itaiyiyal.mp3",
    "019-col-uriyiyal.mp3",
    "020-col-ecchaviyal.mp3",
    "021-porul-akathinaiyiyal.mp3",
    "022-porul-purathinaiyiyal.mp3",
    "023-porul-kalaviyal.mp3",
    "024-porul-karpiyal.mp3",
    "025-porul-poruliyal.mp3",
    "026-porul-meyppaattiyal.mp3",
    "027-porul-uvamaviyal.mp3",
    "028-porul-cheyyuliyal.mp3",
    "029-porul-marabiyal.mp3",
]


def test_the_29_recordings():
    assert sorted(p.name for p in FOLDER.iterdir()) == NAMES and len(NAMES) == 29
    for p in FOLDER.iterdir():
        # an MP3 file with its tag, 1.3 to 10.5 MB
        assert p.read_bytes()[:3] == b"ID3" and 1_000_000 < p.stat().st_size < 11_000_000, p.name


def test_they_stream_from_the_portal():
    from kts import UNLISTED
    assert UNLISTED == (URL,)
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for name in NAMES:
        r = client.head(URL + name)
        assert r.status_code == 200 and r.mimetype == "audio/mpeg", name
        assert r.headers["Content-Length"] == str((FOLDER / name).stat().st_size), name
        assert r.headers["Accept-Ranges"] == "bytes" and r.headers["X-Robots-Tag"] == "noindex", name
        r.close()
    # a part, as a player asks for it when the listener moves ahead
    r = client.get(URL + "028-porul-cheyyuliyal.mp3", headers={"Range": "bytes=5000000-5000099"})
    assert r.status_code == 206 and r.data == (FOLDER / "028-porul-cheyyuliyal.mp3").read_bytes()[5_000_000:5_000_100]
    r.close()
    # the other files of the portal stay as they were
    r = client.get("/static/audio/ta/0001.mp3")
    assert r.status_code == 200 and "X-Robots-Tag" not in r.headers
    r.close()


def test_no_page_names_the_folder():
    word = FOLDER.name.encode()
    for base in ("templates", "data", "static"):
        for p in (ROOT / base).rglob("*"):
            if p.is_file() and p.suffix in (".html", ".json", ".js", ".css", ".txt", ".xml", ".svg", ".webmanifest"):
                assert word not in p.read_bytes(), p
    client = make_app(ADMIN_PASSWORD=None).test_client()
    sitemap = client.get("/sitemap.xml").get_data(as_text=True)
    pages = [re.sub(r"^https?://[^/]+", "", u) for u in re.findall(r"<loc>([^<]+)</loc>", sitemap)]
    assert len(pages) > 10
    for path in pages + ["/robots.txt", "/search?q=tolkappiyam", "/search?q=தொல்காப்பியம்", "/search?q=mp3"]:
        r = client.get(path)
        assert r.status_code == 200 and FOLDER.name not in r.get_data(as_text=True), path
        r.close()
    assert FOLDER.name not in sitemap

"""
Thiruvalluvar on stamps and coins of India, an album of the gallery (1.2.183; CICT, 12 November 2026: "place in the gallery with
captions and also the coins of Thiruvalluvar"): the stamps of 1960 and 2010 and the coins of 1995, with their captions.

    python -m pytest tests/test_gallery_valluvar_1112.py -q
"""
import json

from conftest import ROOT, make_app

ALBUM = "Thiruvalluvar on stamps and coins of India"


def _seeds():
    return [s for s in json.loads((ROOT / "data" / "gallery.json").read_text(encoding="utf-8")) if s["key"].startswith("valluvar-")]


def test_the_seeds_and_their_files():
    seeds = _seeds()
    assert [s["key"] for s in seeds] == ["valluvar-stamp-1960", "valluvar-stamp-2010", "valluvar-coin-1995-rs1", "valluvar-coin-1995-rs2",
                                         "valluvar-coin-1995-rs5"]
    assert {s["album"] for s in seeds} == {ALBUM}
    assert [s["taken_on"] for s in seeds] == ["1960-02-15", "2010-06-27", "", "", ""]
    assert "15 naye paise, issued on 15 February 1960" in seeds[0]["caption"]
    assert "₹5, issued on 27 June 2010" in seeds[1]["caption"] and "Coimbatore from 23 to 27 June 2010" in seeds[1]["caption"]
    for s, value in zip(seeds[2:], ("₹1", "₹2", "₹5")):
        assert f"Saint Thiruvalluvar on the {value} coin of the Government of India for the 8th World Tamil Conference" in s["caption"]
        assert "Image: SPMCIL" in s["caption"]
    for s in seeds:
        assert len(s["caption"]) <= 300
        data = (ROOT / "data" / "gallery" / s["file"]).read_bytes()
        assert data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) < 400_000, s["file"]
        assert b"EXIF" not in data[:64], s["file"]


def test_the_album_on_the_gallery():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/gallery?lang=en").get_data(as_text=True)
    assert f"<bdi>{ALBUM}</bdi>" in page
    album = client.get("/gallery?lang=en&album=" + ALBUM.replace(" ", "+")).get_data(as_text=True)
    assert album.count('<figure class="photo">') == 5 and "5 photographs" in album
    # the stamp of 2010 first, then that of 1960 with its date, then the coins in the order of their value
    at = [album.index(f"/files/gallery/{f}") for f in ("thiruvalluvar-stamp-2010-wctc.webp", "thiruvalluvar-stamp-1960.webp",
                                                         "thiruvalluvar-coin-1995-rs1.webp", "thiruvalluvar-coin-1995-rs2.webp",
                                                         "thiruvalluvar-coin-1995-rs5.webp")]
    assert at == sorted(at) and "15 Feb 1960" in album and "27 Jun 2010" in album
    for s in _seeds():
        r = client.get(f"/files/gallery/{s['file']}")
        assert r.status_code == 200 and r.data == (ROOT / "data" / "gallery" / s["file"]).read_bytes()
        r.close()

"""
வள்ளுவர் குளம் · Valluvar's Pond plays inside the portal (1.2.186; CICT, 13 November 2026, of
https://adhavan18.github.io/valluvar-pond/: "add the game also"). The students' game stays on the site of its makers: a page of the
portal, /static/valluvar-pond/index.html, shows it in a frame, as the README of the game invites a website to do. Nothing of the game
is kept on the portal, so that none of its code runs as the portal's own.

    python -m pytest tests/test_pond_1113.py -q
"""
import re
import sqlite3

from conftest import ROOT, make_app
from test_repository import _restart

PAGE = "/static/valluvar-pond/index.html"
HOST = "https://adhavan18.github.io"
GAME = HOST + "/valluvar-pond/"
FOLDER = ROOT / "static" / "valluvar-pond"


def _row(app, url=PAGE):
    from kts.db import query
    with app.app_context():
        r = query("SELECT * FROM resources WHERE url = ?", (url,), one=True)
        return dict(r) if r else None


def test_the_page_shows_the_game_in_a_frame_from_the_site_of_its_makers():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get(PAGE)
    assert page.status_code == 200 and page.mimetype == "text/html"
    html = page.get_data(as_text=True)
    assert "<title>வள்ளுவர் குளம் · Valluvar's Pond</title>" in html
    # this page alone may hold a frame of the makers' site; the rest of its policy is the portal's
    policy = page.headers["Content-Security-Policy"]
    assert f"frame-src https://www.youtube-nocookie.com {HOST};" in policy
    assert "script-src 'self';" in policy and "default-src 'self';" in policy and "frame-ancestors 'self'" in policy
    for path in ("/?lang=en", "/static/uriyadi/index.html", "/resources?lang=en", "/static/yappu/app/index.html"):
        other = client.get(path).headers["Content-Security-Policy"]
        assert "frame-src https://www.youtube-nocookie.com;" in other and "adhavan18" not in other, path
    # no script in the page itself; the frame is made by pond.js when the player presses Play
    assert re.findall(r'<script src="([^"]+)"></script>', html) == ["pond.js"]
    assert "<script>" not in html and "<style" not in html and "<iframe" not in html and not re.search(r"\son[a-z]+=", html)
    assert f'data-src="{GAME}"' in html and 'id="play"' in html and 'href="../../"' in html
    # said to be the students' own, and where it runs from
    assert "A student project by adhavan18 and Md-Shameem-Dev" in html and "not an official release of the Central Institute" in html
    assert "from the site of its makers (adhavan18.github.io)" in html and "about 42 MB" in html
    assert re.findall(r'https?://[^"\s<)]+', html) == [GAME] * 3      # the frame, the link, the link without scripts
    script = client.get("/static/valluvar-pond/pond.js")
    assert script.status_code == 200 and "javascript" in script.mimetype
    js = script.get_data(as_text=True)
    # the frame runs the game and keeps its own score; it opens no window, sends no form and cannot move this page
    assert "frame.setAttribute('sandbox', 'allow-scripts allow-same-origin');" in js
    for token in ("allow-top-navigation", "allow-popups", "allow-forms", "allow-modals", "http"):
        assert token not in js, token
    assert "frame.src = stage.dataset.src;" in js and "innerHTML" not in js and "eval(" not in js
    css = client.get("/static/valluvar-pond/pond.css")
    assert css.status_code == 200 and css.mimetype == "text/css" and b"http" not in css.data
    # nothing of the game itself lies on the portal
    assert sorted(p.name for p in FOLDER.iterdir()) == ["index.html", "pond.css", "pond.js"]


def test_the_entry_of_the_repository_leads_to_the_page_and_is_featured():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    row = _row(app)
    assert row is not None and _row(app, GAME) is None
    assert (row["title"], row["category"], row["featured"], row["sort_order"], row["published"]) == \
        ("வள்ளுவர் குளம் · Valluvar's Pond", "app", 1, 12, 1)
    assert "made by students" in row["description"] and "not an official release of CICT" in row["description"]
    assert "plays here in a frame, from the site of its makers" in row["description"] and "about 42 MB" in row["description"]
    r = client.get(f"/resources/{row['id']}")
    assert r.status_code == 302 and r.headers["Location"] == PAGE
    apps = client.get("/resources?cat=app&lang=en").get_data(as_text=True)
    assert "வள்ளுவர் குளம் · Valluvar&#39;s Pond" in apps


def _as_1_2_184(app, featured=0, sort_order=16):
    """The database of the live site before 1.2.186: the entry leads to the makers' site, came after the first entries."""
    conn = sqlite3.connect(str(app.config["DATABASE"]))
    conn.execute("UPDATE resources SET created_at = '2026-10-05T10:00:00+00:00'")
    conn.execute("UPDATE resources SET url = ?, description = 'As it came with 1.2.184.', featured = ?, sort_order = ?, "
                 "created_at = '2026-11-13T06:30:00+00:00' WHERE url = ?", (GAME, featured, sort_order, PAGE))
    conn.execute("UPDATE resources SET created_at = '2026-11-13T06:30:00+00:00' WHERE url = '/static/uriyadi/index.html'")
    conn.execute("DELETE FROM settings WHERE key = 'migrate.resource.pond_page'")
    conn.commit()
    conn.close()


def test_the_entry_of_1_2_184_is_moved_to_the_page_once():
    app = make_app(ADMIN_PASSWORD=None)
    _as_1_2_184(app)
    assert _row(app) is None and _row(app, GAME)["featured"] == 0
    again = _restart(app)
    row = _row(again)
    assert _row(again, GAME) is None and (row["featured"], row["sort_order"]) == (1, 12)
    assert "plays here in a frame, from the site of its makers" in row["description"]
    # on the home page with CICT's own: the study material, Kural Uriyadi, Kural Bridge, the two apps, and the game of the students
    home = again.test_client().get("/?lang=en").get_data(as_text=True)
    block = home[home.index('<div class="section-head"><h2>Featured'):]
    six = re.findall(r'href="/resources/(\d+)"', block[:block.index("</section>")])
    uriyadi = _row(again, "/static/uriyadi/index.html")
    assert len(set(six)) == 6 and str(row["id"]) in six and str(uriyadi["id"]) in six
    # once: an entry put back by hand later is left as it is
    conn = sqlite3.connect(str(again.config["DATABASE"]))
    conn.execute("UPDATE resources SET url = ?, featured = 0, sort_order = 16 WHERE url = ?", (GAME, PAGE))
    conn.commit()
    conn.close()
    third = _restart(again)
    assert _row(third) is None and _row(third, GAME)["featured"] == 0


def test_an_entry_the_console_has_changed_is_not_moved():
    app = make_app(ADMIN_PASSWORD=None)
    _as_1_2_184(app, featured=1, sort_order=3)      # featured by hand in the Console
    again = _restart(app)
    row = _row(again, GAME)
    assert _row(again) is None and (row["featured"], row["sort_order"], row["description"]) == (1, 3, "As it came with 1.2.184.")

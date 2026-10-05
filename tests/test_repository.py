"""
Entries of the repository that every installation carries (data/resources.json).

    python -m pytest tests -q
"""
import json
import re

from conftest import ROOT, make_app

SEEDS = json.loads((ROOT / "data" / "resources.json").read_text(encoding="utf-8"))
PLAY = "https://play.google.com/store/apps/details?id=in.cict.kural"
WEB = "https://cictdl.github.io/index.html/kural-app/"
CORPUS = "https://www.digitalarchives.cict.in/#ground-truth"
ARCHIVES = "https://www.digitalarchives.cict.in/#archives"
RUN = "https://www.digitalarchives.cict.in/kural-run.html"
CROSSWORD = "https://cictdl.github.io/index.html/kural-app/kattam/index.html"
YAPPU = "/static/yappu/app/index.html"
GUIDE = "/static/yappu/yappu-quick-guide.pdf"
BRIDGE = "https://cictdl.github.io/index.html/kural-app/bridge/"
QUIZ = "/quiz"
# the 44 parts of the Thirukkural in Indian Sign Language, on the YouTube channel of CICT (version 1.2.12)
SIGN = [s["url"] for s in SEEDS if s["category"] == "video_sign"]
# Thirukkural Isai Tamil, the musical version in six volumes on cict.in (version 1.2.13)
ISAI = [f"https://cict.in/audios/thirukural-{n}.mp3" for n in range(1, 7)]
# five Thirukkural lectures of Dr. Divya Sripada from the YouTube channel of CICT (version 1.2.14)
LECTURES = [f"https://www.youtube.com/watch?v={v}" for v in ("POU5PhXJRMU", "8k-U9tRG99E", "0VZagb_EtWA", "ZUaP1sFK-WQ", "-yZ9t9C7QA8")]
ALL = [PLAY, WEB, CORPUS, ARCHIVES, RUN, CROSSWORD, YAPPU, GUIDE, BRIDGE, QUIZ] + SIGN + ISAI + LECTURES


def _restart(app):
    """The portal started again on the same database and the same folders."""
    return make_app(**{name: app.config[name] for name in ("INSTANCE_DIR", "DATABASE", "UPLOAD_DIR")})


def _rows(app):
    from kts.db import query
    with app.app_context():
        return [dict(r) for r in query("SELECT * FROM resources ORDER BY id")]


def test_the_seed_file_is_complete():
    assert [s["url"] for s in SEEDS] == ALL
    assert [s["category"] for s in SEEDS] == ["app", "app", "corpus", "corpus", "app", "app", "app", "study", "app", "app"] + ["video_sign"] * 44 + ["music"] * 6 + ["video_kural"] * 5
    for s in SEEDS:
        assert s["key"] and s["title"] and s["description"]
    assert len({s["key"] for s in SEEDS}) == len(SEEDS)


def test_a_new_installation_carries_the_app():
    app = make_app(ADMIN_PASSWORD=None)
    rows = _rows(app)
    assert [r["url"] for r in rows] == ALL
    assert all(r["published"] == 1 for r in rows)
    # seven chosen for the home page, which shows six in the order of sort_order: Kural Bridge first,
    # the Digital Archives in the repository only; the two of the prosody app and the classroom quiz
    # are in the repository only, the quiz first of them
    assert [r["featured"] for r in rows] == [1, 1, 1, 1, 1, 1, 0, 0, 1, 0] + [0] * 44 + [0] * 6 + [0] * 5
    client = app.test_client()
    page = client.get("/resources").get_data(as_text=True)
    for s in SEEDS:
        assert s["title"] in page
    home = client.get("/").get_data(as_text=True)
    assert "Tirukkural Multilingual (Android)" in home and "Kural Bridge" in home
    # the card on the home page ends at a word, not inside one
    assert "with the In<" not in home and "Institute's published translations into the 22 languages" not in home
    r = client.get(f"/resources/{rows[0]['id']}")
    assert r.status_code == 302 and r.headers["Location"] == PLAY
    r = client.get(f"/resources/{rows[1]['id']}")
    assert r.status_code == 302 and r.headers["Location"] == WEB
    for row, url in zip(rows, ALL):
        r = client.get(f"/resources/{row['id']}")
        assert r.status_code == 302 and r.headers["Location"] == url
    # the names keep their diacritics
    assert "Kathiraivēṟpiḷḷai" in page and "Yāpparuṅkalakkārikai" in page
    # the corpus has a tab of its own
    assert "Thirukkural Palm-Leaf" in client.get("/resources?cat=corpus").get_data(as_text=True)
    assert "Thirukkural Palm-Leaf" not in client.get("/resources?cat=app").get_data(as_text=True)


def test_the_app_is_listed_in_every_language():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    for lang in ("ta", "hi", "ur", "sat"):
        page = client.get(f"/resources?lang={lang}").get_data(as_text=True)
        assert "Tirukkural Multilingual (Android)" in page, lang


def test_an_entry_is_put_in_once():
    app = make_app(ADMIN_PASSWORD=None)
    again = _restart(_restart(app))
    assert [r["url"] for r in _rows(again)] == ALL


def test_a_deleted_entry_does_not_come_back():
    from kts.db import execute
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        execute("DELETE FROM resources WHERE url = ?", (PLAY,))
    again = _restart(app)
    assert [r["url"] for r in _rows(again)] == ALL[1:]


def test_an_entry_added_by_hand_is_not_doubled():
    import sqlite3
    from kts.db import utcnow
    # a database of before the seed, in which an administrator had entered the Play link himself
    app = make_app(ADMIN_PASSWORD=None)
    conn = sqlite3.connect(str(app.config["DATABASE"]))
    conn.execute("DELETE FROM resources")
    conn.execute("DELETE FROM settings WHERE key LIKE 'seed.resource.%'")
    conn.execute("INSERT INTO resources(title, category, url, created_at, updated_at) VALUES(?,?,?,?,?)",
                 ("Our app", "app", PLAY, utcnow(), utcnow()))
    conn.commit()
    conn.close()
    again = _restart(app)
    rows = _rows(again)
    assert [r["url"] for r in rows] == ALL
    assert rows[0]["title"] == "Our app"


def test_entries_added_later_reach_a_database_that_has_the_first_ones():
    # the live site: its database got the first four entries with version 1.1.0, the next two come later
    import sqlite3
    app = make_app(ADMIN_PASSWORD=None)
    conn = sqlite3.connect(str(app.config["DATABASE"]))
    later = ["kural-run", "kural-crossword", "yappu-kalam", "yappu-quick-guide", "kural-bridge", "classroom-quiz"] + \
        [f"kural-sign-{n:02d}" for n in range(1, 45)] + [f"kural-isai-{n}" for n in range(1, 7)] + \
        [f"yt-{url.rsplit('=', 1)[1]}" for url in LECTURES]
    gone = [RUN, CROSSWORD, YAPPU, GUIDE, BRIDGE, QUIZ] + SIGN + ISAI + LECTURES
    conn.execute("DELETE FROM resources WHERE url IN (%s)" % ", ".join("?" * len(gone)), gone)
    conn.execute("DELETE FROM settings WHERE key IN (%s)" % ", ".join("?" * len(later)), ["seed.resource." + k for k in later])
    conn.commit()
    conn.close()
    assert [r["url"] for r in _rows(app)] == ALL[:4]
    again = _restart(app)
    rows = _rows(again)
    assert [r["url"] for r in rows] == ALL
    assert [r["title"] for r in rows[4:6]] == ["குறள் ஓட்டம் · Kural Run", "குறள் குறுக்கெழுத்து · Kural Crossword"]
    # shown with the featured entries first, each group in the order of sort_order
    page = again.test_client().get("/resources?lang=en").get_data(as_text=True)
    order = [page.find(s["title"]) for s in sorted(SEEDS, key=lambda s: (-s["featured"], s["sort_order"]))]
    assert all(o > 0 for o in order) and order == sorted(order)


def test_the_prosody_app_is_served_by_the_portal_itself():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    rows = {r["url"]: r for r in _rows(app)}
    r = client.get(f"/resources/{rows[YAPPU]['id']}")
    assert r.status_code == 302 and r.headers["Location"] == YAPPU
    page = client.get(YAPPU)
    assert page.status_code == 200 and page.mimetype == "text/html"
    html = page.get_data(as_text=True)
    assert "யாப்புக் கலம்" in html
    # nothing is loaded from another host, and the policy of the portal stands on the page
    assert "script-src 'self'" in page.headers["Content-Security-Policy"]
    for host in ("googleapis", "gstatic", "jsdelivr", "http://", "https://"):
        assert host not in html, host
    import re
    scripts = re.findall(r'<script src="([^"]+)"></script>', html)
    assert scripts == ["yappu.js", "lessons.js", "faq.js", "checks.js", "app.js", "game.js"]
    assert "<script>" not in html and not re.search(r"\son[a-z]+=", html)
    for name in scripts:
        r = client.get("/static/yappu/app/" + name)
        assert r.status_code == 200 and len(r.data) > 1000, name
        r.close()
    r = client.get(GUIDE)
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data[:5] == b"%PDF-"
    assert "Content-Security-Policy" not in r.headers
    r.close()
    sheet = client.get("/static/yappu/reference/sheet.html").get_data(as_text=True)
    assert "googleapis" not in sheet and "<script" not in sheet


def test_an_address_of_the_portal_keeps_its_prefix():
    app = make_app(ADMIN_PASSWORD=None, URL_PREFIX="/kts5")
    rid = {r["url"]: r["id"] for r in _rows(app)}[GUIDE]
    r = app.test_client().get(f"/kts5/resources/{rid}")
    assert r.status_code == 302 and r.headers["Location"] == "/kts5" + GUIDE


def test_the_videos_in_sign_language_have_a_tab_of_their_own():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    assert len(SIGN) == 44 and len(set(SIGN)) == 44
    assert all(re.fullmatch(r"https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}", url) for url in SIGN)
    page = client.get("/resources?lang=en").get_data(as_text=True)
    assert 'href="/resources?cat=video_sign&amp;l=&amp;q=" class="">Thirukkural in sign language <span class="muted">44</span></a>' in page
    # the tab of the Thirukkural lectures holds five (1.2.14); that of Thiruvalluvar stands once it holds a video
    assert 'href="/resources?cat=video_kural&amp;l=&amp;q=" class="">Thirukkural videos <span class="muted">5</span></a>' in page
    assert "cat=video_valluvar" not in page
    lectures = client.get("/resources?cat=video_kural&lang=en").get_data(as_text=True)
    assert lectures.count('<div class="card res-card">') == 5
    assert lectures.index("Leadership lessons from Thirukural") < lectures.index("Part 01 : Goal setting") \
        < lectures.index("Part 02 : Goal setting") < lectures.index("part 01 : Importance of the Right Communications")
    tab = client.get("/resources?cat=video_sign&lang=en").get_data(as_text=True)
    assert tab.count('<div class="card res-card">') == 44
    assert tab.index("Part 1 ") < tab.index("Part 2 ") < tab.index("Part 44")
    assert "சைகைமொழியில் திருக்குறள் — பகுதி 1 · Thirukkural in Indian Sign Language, Part 1" in tab
    rid = {r["url"]: r["id"] for r in _rows(app)}[SIGN[0]]
    r = client.get(f"/resources/{rid}")
    assert r.status_code == 302 and r.headers["Location"] == SIGN[0]
    # the tab names in the language of the page
    assert "res.cat_video_sign" not in client.get("/resources?lang=ta").get_data(as_text=True)


def test_the_musical_thirukkural_has_its_six_volumes_under_music():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    page = client.get("/resources?lang=en").get_data(as_text=True)
    assert 'href="/resources?cat=music&amp;l=&amp;q=" class="">Music <span class="muted">6</span></a>' in page
    tab = client.get("/resources?cat=music&lang=en").get_data(as_text=True)
    assert tab.count('<div class="card res-card">') == 6
    for n in range(1, 7):
        assert f"திருக்குறள் இசைத் தமிழ் — தொகுதி {n} · Thirukkural Isai Tamil, Volume {n}" in tab
    assert tab.index("Volume 1") < tab.index("Volume 6") and "volume 1 of 6 (MP3, 41.1 MB)" in tab
    rows = {r["url"]: r for r in _rows(app)}
    assert all(rows[url]["lang"] == "ta" for url in ISAI)
    r = client.get(f"/resources/{rows[ISAI[0]]['id']}")
    assert r.status_code == 302 and r.headers["Location"] == ISAI[0]


def test_the_classroom_quiz_is_in_the_resources():
    app = make_app(ADMIN_PASSWORD=None)
    client = app.test_client()
    page = client.get("/resources?lang=en").get_data(as_text=True)
    assert "வகுப்பறை வினாடி வினா · Classroom Quiz" in page
    # in the repository, first of the entries that are not on the home page; not on the home page
    assert page.find("Classroom Quiz") > page.find("Digital Archives") and page.find("Classroom Quiz") < page.find("Yappu Kalam")
    assert "Classroom Quiz" not in client.get("/?lang=en").get_data(as_text=True)
    rid = {r["url"]: r["id"] for r in _rows(app)}[QUIZ]
    r = client.get(f"/resources/{rid}")
    assert r.status_code == 302 and r.headers["Location"] == QUIZ
    assert client.get(QUIZ).status_code == 200
    # under a path prefix the address keeps it
    own = make_app(ADMIN_PASSWORD=None, URL_PREFIX="/kts5")
    rid = {r["url"]: r["id"] for r in _rows(own)}[QUIZ]
    assert own.test_client().get(f"/kts5/resources/{rid}").headers["Location"] == "/kts5" + QUIZ

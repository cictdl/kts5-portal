"""
The video guide to the portal (version 1.2.128): four videos on CICT's YouTube channel, each shown by a poster kept on the
portal. Off every page since 1.2.148 (the user: "remove ▶ Video guide to the KTS 5.0 portal in all pages"); its data, posters and
macros stay for a later use, and the player of the portal (portal.js, the policy) for the other videos.

    python -m pytest tests -q
"""
import json

from PIL import Image

from conftest import ROOT, make_app

DATA = json.loads((ROOT / "data" / "guide_videos.json").read_text(encoding="utf-8"))
IDS = {1: "V3JtCOfqIzo", 2: "Xmtf4A6oH7U", 3: "CxoeFOP-xBg", 4: "gYW8YlyL2Ro"}


def _page(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def test_the_four_videos_and_their_posters_kept():
    assert DATA["channel"] == "https://www.youtube.com/@CICT_Online"
    assert [(v["n"], v["youtube"]) for v in DATA["videos"]] == sorted(IDS.items())
    for v in DATA["videos"]:
        path = ROOT / "static" / v["poster"]
        assert path.stat().st_size < 40_000, path
        with Image.open(path) as im:
            assert im.format == "JPEG" and im.size == (640, 360), path


def test_no_page_shows_the_video_guide():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("home.hub", "1")   # the hub too, when shown
    client = app.test_client()
    for path in ("/?lang=en", "/how-to-take-part?lang=en", "/how-to-take-part/institutions?lang=en", "/register?lang=en",
                 "/institutions/register?lang=en", "/institution/login?lang=en", "/nodal-institutions?lang=en", "/resources?lang=en",
                 "/console/login", "/?lang=ta", "/how-to-take-part?lang=hi"):
        page = _page(client, path)
        assert "gv-block" not in page and "gv-poster" not in page and "video-guide" not in page, path
        assert "Video guide" not in page and "video guide" not in page, path
        for vid in IDS.values():
            assert vid not in page, (path, vid)
    with app.app_context():
        set_setting("reg.open", "0")
    assert "gv-block" not in _page(client, "/register?lang=en")


def test_the_player_and_the_policy():
    # the player of the portal stays, for the other videos: YouTube's no-cookie player only, after a poster is pressed
    client = make_app(ADMIN_PASSWORD=None).test_client()
    policy = client.get("/?lang=en").headers["Content-Security-Policy"]
    assert "img-src 'self' data:;" in policy and "frame-src https://www.youtube-nocookie.com;" in policy
    js = (ROOT / "static" / "js" / "portal.js").read_text(encoding="utf-8")
    assert 'document.querySelectorAll("a[data-yt]")' in js and "/^[A-Za-z0-9_-]{11}$/.test(id)" in js
    page = _page(client, "/?lang=en")
    assert "/static/js/portal.js?v=24" in page

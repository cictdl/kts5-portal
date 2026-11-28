"""
KTS 5.0 and the Thirukkural from the YouTube channels of the Ministry of Education and of CICT (1.2.239). CICT, 28 November 2026:
"https://www.youtube.com/@Eduminofindia/videos https://www.youtube.com/@Eduminofindia/shorts update KTS 5.0 related to KTS 5.0",
then "https://www.youtube.com/@cicttamil/shorts https://www.youtube.com/@cicttamil/videos update KTS 5.0 and Thirukkural".

The Gallery has a tab of the videos of KTS 5.0 (played on the page, as the shorts are); the shorts have CICT's channel too; "KTS 5.0
in the news" has the Ministry's five new posts, and CICT's link on the cards of the films its channel carries too; the programme
page has 48 Thirukkural reels of CICT more; the Resources have the lecture on Tolstoy.

    python -m pytest tests/test_youtube_1128.py -q
"""
import json
import re
from html import unescape

from conftest import ROOT, make_app
from test_reserve_1111 import LANGS

VIDEOS = json.loads((ROOT / "data" / "videos.json").read_text(encoding="utf-8"))
SHORTS = json.loads((ROOT / "data" / "shorts.json").read_text(encoding="utf-8"))
NEWS = json.loads((ROOT / "data" / "news.json").read_text(encoding="utf-8"))
REELS = json.loads((ROOT / "data" / "reels.json").read_text(encoding="utf-8"))
INAUGURATION = "AiCjCUD29Ng"
MOE_SHORTS = ["ca4ne3gYbzo", "t6W-fqXFVOw"]                                              # episode 3; the run at BHU
CICT_SHORTS = ["qINX6FfPX6k", "ZwGl0axOgz4", "rlwg0tcxhNI", "W2QYqLm9FT0", "Y4uc1HR7yYM"]
# CICT's channel carries these films of the Ministry too: the card of each has both links
BOTH = {"social-2026-11-20-61": "qINX6FfPX6k", "social-2026-11-22-70": "ZwGl0axOgz4", "social-2026-11-20-60": "rlwg0tcxhNI",
        "social-2026-11-16-54": "W2QYqLm9FT0", "social-2026-11-21-66": "Y4uc1HR7yYM"}
# the reels of CICT that their own descriptions give to the Thirukkural or Thiruvalluvar, in the order of the channel: 45 of
# 4 July 2025 to 21 August 2026 (IST), then those of 25, 27 and 28 November 2026
NEW_REELS = [
    "D8yBBYJEcpE", "CUCcf-CFHwk", "cz02Z55pXz8", "wuJ8XQc0mXM", "-SmwKksNhGE", "P83dK1C4PME",
    "24czeUTvvDo", "9rPNGXsFDSg", "WGOF9cunwlg", "f6h2HsbHCDs", "Jrme9WFPZOM", "U9g_9zqOzt4",
    "jCNA4SsDLwE", "rCvp-Rqn8j8", "gp_rXu_bpnU", "QZ7Z_dmvxk0", "5v1ZO2x46jE", "_8-85shJ18o",
    "WhC6ral7484", "VXE57ZBZJcY", "AxGGFPqi1rA", "WvKkV4Z4uSI", "DoeFXfT6y7c", "k2OHSgJUbhQ",
    "6jPa36o3Kjo", "w614VV4oyIA", "kF2DrSFmaOw", "uWun_-T-p60", "vyX6CpkNxQg", "ITo0lqcKOVs",
    "dIW_q5Ar2B0", "mLpKjHxNp4M", "bZNYzM8Tc4M", "iMyeZaxJzIg", "5gO-4MGPMdg", "26Co9iPjBR0",
    "-6N7oBOxzD8", "66zMeUHuYeY", "zAt-_RqECU4", "rEWCcWgKDx8", "p-aa1uHxxzI", "GsHP_Mb-l_I",
    "yz5cs8R-7Ik", "Yz54GJ39__I", "wbsMUI4Ht0s",
    "LExTrpZOyhY", "8BBDWGriM9o", "AnvLzmBGpBg"]


def test_the_videos_and_their_covers():
    from PIL import Image
    assert [(v["id"], v["channel"]) for v in VIDEOS] == [(INAUGURATION, "moe"), ("FEZvrEEosEc", "moe"), ("wUcojpF_Io0", "moe"),
                                                         ("3HpDc4LbnfU", "cict")]
    for v in VIDEOS:
        assert set(v) == {"id", "channel", "date", "time", "seconds", "title", "lang"} and re.fullmatch(r"[A-Za-z0-9_-]{11}", v["id"])
        assert re.fullmatch(r"[012]\d:[0-5]\d", v["time"]) and v["seconds"] > 0 and v["title"] == v["title"].strip() and v["lang"] == "en"
        path = ROOT / "static" / "img" / "videos" / f"{v['id']}.webp"
        data = path.read_bytes()
        assert data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) < 60_000 and b"EXIF" not in data and b"XMP " not in data
        with Image.open(path) as im:
            assert im.size == (480, 270)
    assert sorted(p.stem for p in (ROOT / "static" / "img" / "videos").glob("*")) == sorted(v["id"] for v in VIDEOS)
    first = VIDEOS[0]      # the recording of the inauguration: 28 November 2026, from 12:30 PM, 1 hour 43 minutes
    assert (first["date"], first["time"], first["seconds"], first["title"]) == ("2026-11-28", "12:30", 6188, "LIVE: Inauguration of Kashi Tamil Sangamam 5.0")
    assert not {v["id"] for v in VIDEOS} & {s["id"] for s in SHORTS}


def test_the_page_of_the_videos():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    r = client.get("/gallery/videos?lang=en")
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    main = page[page.index("<main"):page.index("</main>")]
    assert "<title>KTS 5.0 videos on YouTube" in page
    assert '<h2 class="gv-h" id="videos-h"><span aria-hidden="true">▶</span> KTS 5.0 videos on YouTube</h2>' in main
    assert "from the YouTube channels of the Ministry of Education and of CICT. Press ▶ to play one here" in main
    tabs = main[main.index('<div class="res-tabs">'):main.index("</div>", main.index('<div class="res-tabs">'))]
    assert '<a href="/gallery/videos" class="on"><span aria-hidden="true">▶ </span>KTS 5.0 videos on YouTube <span class="muted">4</span></a>' in tabs
    assert '<a href="/gallery" class="">All albums</a>' in tabs and '<a href="/gallery/shorts" class="">' in tabs
    assert tabs.index('href="/gallery/videos"') < tabs.index('href="/gallery/shorts"')
    heads = re.findall(r'<h3 id="videos-(moe|cict)-h"[^>]*><span lang="en" dir="ltr">([^<]+)</span>(.*?)</h3>', main)
    assert [h[:2] for h in heads] == [("moe", "Ministry of Education, Government of India"), ("cict", "Central Institute of Classical Tamil")]
    # the number of a channel's videos where there are several (not "1 videos")
    assert "<bdi>3 videos</bdi>" in heads[0][2] and "<bdi>" not in heads[1][2] and "1 videos" not in main
    assert 'href="https://www.youtube.com/@Eduminofindia/videos"' in main and 'href="https://www.youtube.com/@cicttamil/videos"' in main
    assert re.findall(r'data-yt="([A-Za-z0-9_-]{11})"', main) == [v["id"] for v in VIDEOS]
    for v in VIDEOS:
        assert f'<img src="/static/img/videos/{v["id"]}.webp" alt="" width="480" height="270" loading="lazy">' in main
        assert main.count(f'href="https://www.youtube.com/watch?v={v["id"]}"') == 2            # the cover and "Watch on YouTube"
    # the lengths as YouTube writes them: the inauguration 1:43:08, the others in minutes
    assert re.findall(r'<span class="gv-len" dir="ltr">([^<]+)</span>', main) == ["1:43:08", "0:49", "3:31", "3:31"]
    assert '<span class="gv-name" lang="en" dir="auto">LIVE: Inauguration of Kashi Tamil Sangamam 5.0</span>' in unescape(main)
    assert "<bdi>28 Nov 2026</bdi>" in main and '<a href="/gallery" class="active">' in page      # the menu: the Gallery
    # nothing of YouTube loads with the page: no frame, no script, no picture of theirs; the cards are those of the videos (16:9)
    assert "<iframe" not in page and "youtube-nocookie" not in page and "ytimg" not in page and "youtube.com/embed" not in page
    assert "photo-grid" not in main and main.count('<div class="gv-card vd-card">') == 4 and "sh-card" not in main
    # three in a row on a wide page (the one rule inline); the frame of a video is 16:9
    assert main.count('<div class="gv-grid vd-grid" style="grid-template-columns:repeat(auto-fill,minmax(min(100%,260px),1fr))">') == 2
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    assert ".gv-poster { position: relative; display: block; aspect-ratio: 16 / 9;" in css
    # a video that plays takes the row, but no more width than lets the whole player be seen in the window (the review of 1.2.239:
    # 1179 x 663 pixels on a wide page, its controls under the fold of a laptop); the style sheet is of version 59
    assert ".gv-card.gv-playing { grid-column: 1 / -1; max-width: min(100%, max(260px, calc((100vh - 170px) * 16 / 9))); }" in css
    assert ".sh-grid .gv-card.gv-playing { grid-column: auto; }" in css                    # a short plays in its own place, as before
    assert '<link rel="stylesheet" href="/static/css/portal.css?v=59">' in page
    assert "https://www.youtube-nocookie.com" in r.headers["Content-Security-Policy"]


def test_the_three_latest_videos_on_the_gallery():
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/gallery?lang=en").get_data(as_text=True)
    main = page[page.index("<main"):page.index("</main>")]
    start = main.index('<section class="gv-block sh-block vd-strip"')
    strip = main[start:main.index("</section>", start)]
    latest = sorted(VIDEOS, key=lambda v: (v["date"], v["time"]), reverse=True)[:3]
    assert [v["id"] for v in latest] == [INAUGURATION, "FEZvrEEosEc", "wUcojpF_Io0"]
    assert re.findall(r'data-yt="([A-Za-z0-9_-]{11})"', strip) == [v["id"] for v in latest]
    assert '<a href="/gallery/videos">All 4 videos →</a>' in strip
    assert main.index("vd-strip") < main.index("sh-strip") < main.index("photo-grid")           # above the shorts and the photographs
    album = client.get("/gallery?lang=en&album=KTS+5.0+in+the+news").get_data(as_text=True)
    assert "vd-strip" not in album and 'href="/gallery/videos"' in album                        # an album: the tab only
    # the arrows of "All ... videos" and "All ... shorts" follow the direction of reading: to the left in Urdu and Kashmiri
    for code in ("ur", "ks"):
        other = client.get(f"/gallery?lang={code}").get_data(as_text=True)
        links = re.findall(r'<p class="small gv-all"><a href="/gallery/(videos|shorts)">([^<]+)</a></p>', other)
        assert [kind for kind, _text in links] == ["videos", "shorts"] and all(text.endswith(" ←") for _kind, text in links), code
    assert '<a href="/gallery/shorts">All 74 shorts →</a>' in main


def test_the_shorts_with_the_channel_of_cict():
    assert len(SHORTS) == 74 and [s["channel"] for s in SHORTS] == ["moe"] * 25 + ["cict"] * 5 + ["kts"] * 44
    assert [s["id"] for s in SHORTS[:2]] == MOE_SHORTS and [s["id"] for s in SHORTS[25:30]] == CICT_SHORTS
    assert all((s["date"], s["lang"]) == ("2026-11-20", "en") for s in SHORTS[25:30])
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/gallery/shorts?lang=en").get_data(as_text=True)
    main = page[page.index("<main"):page.index("</main>")]
    heads = re.findall(r'<h3 id="shorts-(moe|cict|kts)-h"[^>]*><span lang="en" dir="ltr">([^<]+)</span>.*?<bdi>(\d+) shorts</bdi>', main)
    assert heads == [("moe", "Ministry of Education, Government of India", "25"), ("cict", "Central Institute of Classical Tamil", "5"),
                     ("kts", "Kashi Tamil Sangamam", "44")]
    assert 'href="https://www.youtube.com/@cicttamil/shorts"' in main
    assert "from the YouTube channels of the Ministry of Education, of CICT and of Kashi Tamil Sangamam. Press ▶" in main
    assert re.findall(r'data-yt="([A-Za-z0-9_-]{11})"', main) == [s["id"] for s in SHORTS]
    assert '<a href="/gallery/videos" class=""><span aria-hidden="true">▶ </span>KTS 5.0 videos on YouTube <span class="muted">4</span></a>' in main


def test_the_news_page():
    by_key = {x["key"]: x for x in NEWS}
    assert len(NEWS) == 168 and len(by_key) == 168
    new = [by_key[k] for k in ("social-2026-11-25-102", "social-2026-11-27-103", "social-2026-11-27-104", "social-2026-11-27-105",
                               "social-2026-11-28-106")]
    ids = ["wUcojpF_Io0", "t6W-fqXFVOw", "ca4ne3gYbzo", "FEZvrEEosEc", INAUGURATION]
    for x, vid in zip(new, ids):
        assert x["kind"] == "social" and x["source"] == "Ministry of Education" and x["gov"] is True and x["quote_lang"] == "en"
        url = x["links"][0]["url"]
        assert url == (f"https://www.youtube.com/shorts/{vid}" if vid in MOE_SHORTS else f"https://www.youtube.com/watch?v={vid}")
        assert x["links"][0] == {"site": "YouTube", "account": "Eduminofindia", "date": x["date"], "kind": "video", "url": url}
        assert x["versions"] == [{"lang": "en", "title": x["title"], "url": url, "time": x["versions"][0]["time"]}]
        assert x["title"].startswith("The Ministry of Education") and x["title"][-1] not in ".!" and "#" not in x["title"]
        assert x["quote"] and "#" not in x["quote"] and "http" not in x["quote"]
    assert [x["versions"][0]["time"] for x in new] == ["12:25 PM", "2:22 PM", "2:32 PM", "7:32 PM", "12:30 PM"]
    # the film of 25 November is on CICT's channel too (20 November): both links on its card; the others have the Ministry's alone
    assert new[0]["links"][1] == {"site": "YouTube", "account": "cicttamil", "date": "2026-11-20", "kind": "video",
                                  "url": "https://www.youtube.com/watch?v=3HpDc4LbnfU"}
    assert all(len(x["links"]) == 1 for x in new[1:])
    for key, vid in BOTH.items():
        links = by_key[key]["links"]
        assert by_key[key]["source"] == "Ministry of Education" and [l["account"] for l in links] == ["Eduminofindia", "cicttamil"], key
        assert links[1] == {"site": "YouTube", "account": "cicttamil", "date": "2026-11-20", "kind": "video",
                            "url": f"https://www.youtube.com/shorts/{vid}"}
    # every short and every video on one card
    for row in SHORTS + VIDEOS:
        assert sum(1 for x in NEWS if row["id"] in json.dumps(x)) == 1, row["id"]
    # the days in order, each day in the order of its hours
    import datetime as dt
    assert [x["date"] for x in NEWS] == sorted(x["date"] for x in NEWS)
    for day in ("2026-11-25", "2026-11-27", "2026-11-28"):
        times = [dt.datetime.strptime(x["versions"][0]["time"], "%I:%M %p") for x in NEWS if x["date"] == day and x["versions"][0].get("time")]
        assert times == sorted(times), day
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/in-the-news?lang=en").get_data(as_text=True)
    for vid in ids[:1] + ids[3:]:
        assert f'href="https://www.youtube.com/watch?v={vid}"' in page
    for vid in MOE_SHORTS + CICT_SHORTS:
        assert f'href="https://www.youtube.com/shorts/{vid}"' in page
    assert 'title="@cicttamil" href="https://www.youtube.com/shorts/qINX6FfPX6k"' in page
    assert "The Ministry of Education live: the inauguration of Kashi Tamil Sangamam 5.0" in page


def test_the_reels_of_cict_on_the_thirukkural():
    tamil = [r for r in REELS if r["lang"] == "Tamil"]
    assert len(NEW_REELS) == len(set(NEW_REELS)) == 48
    assert len(REELS) == 104 and len({r["id"] for r in REELS}) == 104 and len({r["lang"] for r in REELS}) == 29
    assert len(tamil) == 55 and REELS[-55:] == tamil                                       # Tamil the last group, as before
    assert [r["id"] for r in tamil[:45]] == NEW_REELS[:45] and [r["id"] for r in tamil[-3:]] == NEW_REELS[45:]
    assert [r["id"] for r in tamil[45:52]] == ["JHEHNq387oU", "bYlR7k8UvrY", "9gaYo2DnHCs", "3L-0ullP87g", "-41h8VnAqpQ", "pX3Xgj79HFk",
                                               "B7KjNFCdv5Q"]                             # the seven of 1.2.214 between them
    for r in tamil:
        assert set(r) == {"id", "lang", "native", "presenter", "topic", "topic_en"} and r["presenter"] == "CICT" and r["native"] == "தமிழ்"
        # each is given to the Thirukkural or Thiruvalluvar by its own description on YouTube
        assert re.search("திருக்குற|திருவள்ளுவ", r["topic"]) and re.search("Thirukkural|Thiruvalluvar", r["topic_en"]), r["id"]
        assert re.search(r"[஀-௿]", r["topic"]) and not re.search(r"[஀-௿]", r["topic_en"])
        assert r["topic"] == r["topic"].strip() and r["topic"][-1] != "." and r["topic_en"][-1] != "." and len(r["topic_en"]) <= 90
        assert "Tirukku" not in r["topic_en"] and "Tiruva" not in r["topic_en"]            # the names as the portal writes them
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/programme?lang=en").get_data(as_text=True)
    assert "104 short videos in 29 languages" in page
    for vid in NEW_REELS:
        assert f'href="https://www.youtube.com/shorts/{vid}"' in page
    assert '<bdi lang="ta">திருக்குறளின் கடவுள் வாழ்த்து</bdi> <span class="muted small" lang="en" dir="ltr">· The invocation to the divine in the Thirukkural</span>' in page
    assert '<bdi lang="ta">உதடுகள் ஒட்டாத திருக்குறள் எது?</bdi>' in page and "Which Thirukkural couplet can be recited without the lips touching?" in page
    tamil_card = page.split("<bdi>தமிழ்</bdi>")[1].split("</ul>")[0]
    assert tamil_card.count("youtube.com/shorts/") == 55
    # a language with many reels takes the whole row of the cards, its list in columns (a card of 55 lines would be many screens tall)
    css = (ROOT / "static" / "css" / "portal.css").read_text(encoding="utf-8")
    assert ".reels .reel:has(li:nth-child(17)) { grid-column: 1 / -1; }" in css
    assert ".reels .reel:has(li:nth-child(17)) ul { columns: 3 280px; column-gap: 28px; }" in css and ".reels .reel li { break-inside: avoid; }" in css
    assert '<div class="grid grid-3 reels"' in page and page.count('<div class="card reel">') == 29
    assert max(len([r for r in REELS if r["lang"] == lang]) for lang in {r["lang"] for r in REELS} - {"Tamil"}) == 13      # Hindi: a card as before


def test_the_lecture_on_tolstoy_in_the_resources():
    rows = json.loads((ROOT / "data" / "resources.json").read_text(encoding="utf-8"))
    at = [r["key"] for r in rows].index("yt-Ndy43J7kukw")
    row = rows[at]
    assert row == {"key": "yt-Ndy43J7kukw", "title": "Profound influence of Thirukkural on Tolstoy | P.Marudhanayagam", "category": "video_kural",
                   "lang": "", "description": "A lecture by Prof. P. Marudhanayagam on the YouTube channel of the Central Institute of "
                   "Classical Tamil (செம்மொழி வலையொளி).", "url": "https://www.youtube.com/watch?v=Ndy43J7kukw", "featured": 0, "sort_order": 415}
    assert rows[at - 1]["key"] == "yt-CH0s6N_pfc0" and rows[at - 1]["sort_order"] == 414      # after his other lectures on the Thirukkural
    assert sum(1 for r in rows if r["category"] == "video_kural") == 23 and len(rows) == 159
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get("/resources?lang=en&cat=video_kural").get_data(as_text=True)
    assert "<bdi>Profound influence of Thirukkural on Tolstoy | P.Marudhanayagam</bdi>" in page
    assert '<span dir="ltr">www.youtube.com/watch?v=Ndy43J7kukw</span>' in page and page.count('<div class="card res-card">') == 23


def test_the_texts_in_23_languages():
    from kts.i18n import CATALOG
    en = CATALOG["en"]
    assert en["vd.title"] == "KTS 5.0 videos on YouTube" and en["vd.count"] == "{n} videos" and en["vd.all"] == "All {n} videos"
    assert en["vd.lead"] == ("Videos of Kashi Tamil Sangamam 5.0 from the YouTube channels of the Ministry of Education and of CICT. "
                             "Press ▶ to play one here; nothing of YouTube loads before that.")
    assert en["sh.lead"] == ("Short videos of Kashi Tamil Sangamam 5.0 from the YouTube channels of the Ministry of Education, of CICT and of "
                             "Kashi Tamil Sangamam. Press ▶ to play one here; nothing of YouTube loads before that.")
    assert sorted(CATALOG) == sorted(LANGS) and len(en) == 1561
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for code in LANGS:
        c = CATALOG[code]
        keys = list(c)
        assert keys[keys.index("sh.all") + 1:][:4] == ["vd.title", "vd.lead", "vd.count", "vd.all"], code
        assert c["vd.count"].count("{n}") == 1 and c["vd.all"].count("{n}") == 1 and "▶" in c["vd.lead"] and "▶" in c["sh.lead"], code
        assert "{" not in c["vd.title"] + c["vd.lead"] + c["sh.lead"] and c["vd.title"][-1] not in ".।॥؟۔", code
        assert "CICT" in c["vd.lead"] and "CICT" in c["sh.lead"] and "YouTube" in c["vd.title"], code
        assert c["vd.title"] != c["sh.title"] and c["vd.count"] != c["sh.count"] and c["vd.all"] != c["sh.all"], code
        assert code == "en" or all(c[k] != en[k] for k in ("vd.title", "vd.lead", "sh.lead")), code
        page = client.get(f"/gallery/videos?lang={code}").get_data(as_text=True)
        assert unescape(c["vd.title"]) in unescape(page) and unescape(c["vd.count"].replace("{n}", "3")) in unescape(page), code

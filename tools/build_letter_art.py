"""
The infographic of the Nodal Institution's sample letter (portal 1.2.137), one picture for each of the 23 languages, into
static/img/letter/<code>.png: the road for a Participating Institution - the timeline of the Ministry's letter of 31 October
2026, the four steps, the stipend. The texts are the interface strings nl.art_* (data/i18n) and the month names; the dates
those of DEFAULT_SETTINGS (kts/db.py). Rendered by headless Microsoft Edge over its DevTools protocol, as the posters are
(tools/build_posters.py), 2000 x 1340 pixels; the working files go to the temporary folder kts5-letter-art.

    python tools/build_letter_art.py en ta ur     # a few languages
    python tools/build_letter_art.py all          # the 23
"""
import base64
import html
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
import conftest  # noqa: E402  (temporary folders before config)

from kts import i18n as portal_i18n  # noqa: E402
from kts import letters as L  # noqa: E402
from kts.db import DEFAULT_SETTINGS  # noqa: E402

APP = conftest.make_app(ADMIN_PASSWORD=None)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
OUT = Path(tempfile.gettempdir()) / "kts5-letter-art"
DEST = ROOT / "static" / "img" / "letter"
W, H = 2000, 1340

esc = html.escape


def texts(lang):
    """The texts of the picture in the language, their placeholders filled with the dates of the settings."""
    with APP.app_context():
        v = L.values("Tamil Nadu", lang, get=DEFAULT_SETTINGS.get)
        v["portal"] = "kts.cict.in"
        t = {k: L.fill(k, lang, v) for k in portal_i18n.CATALOG["en"] if k.startswith("nl.art_")}
        get = DEFAULT_SETTINGS.get
        day = lambda key: L.day_text(L._day(key, get), lang, year=False)  # noqa: E731
        by = lambda s: portal_i18n.text("nl.by", lang).replace("{date}", s)  # noqa: E731
        select_end, hei_end = L._day("hei.select_end", get), L._day("hei.end", get)
        sel = f"{hei_end.day + 1}–{day('hei.select_end')}" if select_end and hei_end else day("hei.select_end")
        # the verification (node 4) has no date in the Ministry's letter of 31 October 2026: none on the picture (1.2.155)
        dates = [sel, by(day("camp.to")), day("reg.end"), "",
                 day("kts.start"), day("kts.end"), by(day("orientation.by")),
                 f"{day('internship.start')} – {day('papers.due')}"]
    return t, dates


def page(lang):
    t, dates = texts(lang)
    rtl = portal_i18n.LANG_INFO[lang]["dir"] == "rtl"
    nodes = []
    step = (W - 2 * 170) / 7
    for i in range(8):
        x = 170 + i * step
        pos = f"right:{W - x:.0f}px" if rtl else f"left:{x:.0f}px"
        side = "above" if i % 2 == 0 else "below"
        colour = "#E07B0F" if i < 4 else "#1C3F94"
        nodes.append(f'<div class="node {side}" style="{pos}"><i class="dot" style="background:{colour}"></i>'
                     f'<div class="txt"><div class="desc">{esc(t[f"nl.art_n{i + 1}"])}</div><div class="when">{esc(dates[i])}</div></div></div>')
    cards = "".join(f'<div class="card"><div class="ct"><b class="n">{n}</b><span>{esc(t[f"nl.art_c{n}_t"])}</span></div>'
                    f'<div class="cb">{esc(t[f"nl.art_c{n}"])}</div></div>' + ('<i class="arrow"></i>' if n < 4 else "") for n in range(1, 5))
    return f"""<!doctype html><html lang="{lang}" dir="{'rtl' if rtl else 'ltr'}"><head><meta charset="utf-8"><style>
html,body{{margin:0;padding:0}} body{{width:{W}px;height:{H}px;overflow:hidden;background:#fff;color:#222;
  font-family:'Segoe UI','Nirmala UI','Noto Sans','Noto Sans Ol Chiki','Noto Nastaliq Urdu',sans-serif;position:relative}}
.title{{background:#1C3F94;color:#fff;font-size:44px;font-weight:700;height:86px;line-height:86px;padding:0 40px;white-space:nowrap;overflow:hidden}}
.tl{{position:absolute;top:86px;left:0;right:0;height:650px}}
.tl .line{{position:absolute;left:170px;right:170px;top:340px;height:8px;background:#1C3F94}}
.node{{position:absolute;width:290px;margin-{'right' if rtl else 'left'}:-145px;text-align:center}}
.node .dot{{position:absolute;left:50%;top:0;width:40px;height:40px;margin-left:-20px;border-radius:50%;border:5px solid #fff;box-sizing:border-box}}
.node.above{{top:324px}} .node.above .txt{{position:absolute;bottom:52px;left:0;right:0}}
.node.below{{top:324px}} .node.below .txt{{position:absolute;top:66px;left:0;right:0}}
.node.above .txt{{display:flex;flex-direction:column}} .node.above .desc{{order:1}} .node.above .when{{order:2;margin-top:6px}}
.node.below .when{{margin-bottom:6px}}
.when{{font-size:34px;font-weight:700;color:#222;line-height:1.15}} .desc{{font-size:28px;color:#555;line-height:1.25}}
.cards{{position:absolute;top:768px;left:60px;right:60px;display:flex;align-items:stretch;gap:0}}
.card{{flex:1 1 0;background:#F3F1EC;border:2px solid #DDD8CC;border-radius:22px;padding:22px 24px 18px;height:356px;box-sizing:border-box;overflow:hidden}}
.ct{{display:flex;align-items:center;gap:18px;font-size:33px;font-weight:700;color:#1C3F94;line-height:1.15}}
.ct .n{{flex:0 0 60px;width:60px;height:60px;border-radius:50%;background:#E07B0F;color:#fff;text-align:center;line-height:60px;font-size:34px}}
.cb{{font-size:26px;line-height:1.28;margin-top:16px;color:#222}}
.arrow{{flex:0 0 36px;align-self:center;width:0;height:0;border-top:18px solid transparent;border-bottom:18px solid transparent;
  border-{'right' if rtl else 'left'}:20px solid #1C3F94;margin:0 8px}}
.band{{position:absolute;top:1156px;left:60px;right:60px;height:116px;background:#1B7F3B;border-radius:22px;color:#fff;display:flex;align-items:center;gap:30px;padding:0 40px;box-sizing:border-box}}
.band b{{font-size:54px;white-space:nowrap}} .band span{{font-size:29px;line-height:1.25}}
.foot{{position:absolute;bottom:14px;{'left' if rtl else 'right'}:60px;font-size:25px;color:#555}}
</style></head><body>
<div class="title">{esc(t["nl.art_title"])}</div>
<div class="tl"><div class="line"></div>{''.join(nodes)}</div>
<div class="cards">{cards}</div>
<div class="band"><b>₹10,000</b><span>{esc(t["nl.art_stipend"])}</span></div>
<div class="foot">{esc(t["nl.art_foot"])}</div>
<script>
// a long language: the text of a card or of a node shrinks, a pixel at a time, until it fits its box (never below 17px)
(function () {{
  const shrink = (el, fits) => {{ let size = parseFloat(getComputedStyle(el).fontSize); while (!fits() && size > 17) {{ size -= 1; el.style.fontSize = size + 'px'; }} }};
  document.querySelectorAll('.card').forEach(c => {{ const b = c.querySelector('.cb'), h = c.querySelector('.ct span');
    shrink(h, () => h.getBoundingClientRect().height <= 84);
    shrink(b, () => c.scrollHeight <= c.clientHeight + 1); }});
  document.querySelectorAll('.node.above').forEach(n => {{ const d = n.querySelector('.desc'), w = n.querySelector('.when');
    shrink(d, () => n.querySelector('.txt').getBoundingClientRect().top >= 94);
    shrink(w, () => n.querySelector('.txt').getBoundingClientRect().top >= 94); }});
  document.querySelectorAll('.node.below').forEach(n => {{ const d = n.querySelector('.desc'), w = n.querySelector('.when');
    shrink(d, () => n.querySelector('.txt').getBoundingClientRect().bottom <= 764);
    shrink(w, () => n.querySelector('.txt').getBoundingClientRect().bottom <= 764); }});
  const band = document.querySelector('.band span'); shrink(band, () => document.querySelector('.band').scrollHeight <= document.querySelector('.band').clientHeight + 1);
  const title = document.querySelector('.title'); shrink(title, () => title.scrollWidth <= title.clientWidth + 1);
}})();
</script>
</body></html>"""


# ---- headless Edge over its DevTools protocol (as tools/build_posters.py) ------------------------------------------------------
_EDGE = {}


def _call(method, **params):
    e = _EDGE
    e["n"] += 1
    e["ws"].send(json.dumps({"id": e["n"], "method": method, "params": params}))
    while True:
        msg = json.loads(e["ws"].recv())
        if msg.get("id") == e["n"]:
            if "error" in msg:
                raise RuntimeError(f"{method}: {msg['error']}")
            return msg.get("result", {})


def _close():
    proc, prof = _EDGE.get("proc"), _EDGE.get("prof")
    if proc:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(.5)
    if prof:
        shutil.rmtree(prof, ignore_errors=True)


def _edge():
    if "ws" in _EDGE:
        return
    import atexit
    import urllib.request

    import websocket
    port = 9363
    OUT.mkdir(parents=True, exist_ok=True)
    prof = tempfile.mkdtemp(prefix="edgeart-", dir=OUT)
    proc = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--no-first-run", "--mute-audio", f"--remote-debugging-port={port}",
                             f"--user-data-dir={prof}", f"--window-size={W},{H}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _EDGE.update(proc=proc, prof=prof, n=0)
    atexit.register(_close)
    tabs = None
    for _ in range(150):
        try:
            tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
            break
        except OSError:
            time.sleep(.2)
    tab = next(t for t in tabs if t["type"] == "page")
    _EDGE["ws"] = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=180, suppress_origin=True)
    _call("Network.enable")
    _call("Network.setCacheDisabled", cacheDisabled=True)
    _call("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)


def render(lang):
    _edge()
    h = OUT / f"{lang}.html"
    h.write_text(page(lang), encoding="utf-8")
    _call("Page.navigate", url=h.resolve().as_uri())
    for _ in range(100):
        if _call("Runtime.evaluate", expression="document.readyState", returnByValue=True)["result"].get("value") == "complete":
            break
        time.sleep(.1)
    time.sleep(1.5)
    # every text inside its box: the cards, the nodes above the line, the band
    check = _call("Runtime.evaluate", returnByValue=True, expression="""(() => {
        const bad = [];
        document.querySelectorAll('.card').forEach((c, i) => { if (c.scrollHeight > c.clientHeight + 2) bad.push('card ' + (i + 1) + ' overflows by ' + (c.scrollHeight - c.clientHeight)); });
        document.querySelectorAll('.node.above .txt').forEach((n, i) => { const r = n.getBoundingClientRect(); if (r.top < 90) bad.push('node ' + (2 * i + 1) + ' reaches the title'); });
        document.querySelectorAll('.node.below .txt').forEach((n, i) => { const r = n.getBoundingClientRect(); if (r.bottom > 770) bad.push('node ' + (2 * i + 2) + ' reaches the cards'); });
        const b = document.querySelector('.band'); if (b.scrollHeight > b.clientHeight + 2) bad.push('band overflows');
        const f = document.querySelector('.foot').getBoundingClientRect(); if (f.top < 1274) bad.push('footer meets the band');
        return bad; })()""")["result"]["value"]
    data = _call("Page.captureScreenshot", format="png", clip={"x": 0, "y": 0, "width": W, "height": H, "scale": 1})["data"]
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / f"{lang}.png").write_bytes(base64.b64decode(data))
    return check


if __name__ == "__main__":
    codes = [c for c, *_ in portal_i18n.LANGUAGES] if "all" in sys.argv[1:] else sys.argv[1:]
    report = {}
    for code in codes:
        problems = render(code)
        report[code] = problems
        print(code, "ok" if not problems else "; ".join(problems))
    (OUT / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    _close()

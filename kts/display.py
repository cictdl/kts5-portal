"""
Live banners for screens (version 1.2.61): pages that a screen at an airport, a railway station or a campus
opens and keeps open. Each shows the time in IST from the portal's own clock (so a screen with a wrong
clock still shows the right time), a Thirukkural couplet that changes on a schedule, the same on every
screen at the same moment, and the countdown to Kashi Tamil Sangamam 5.0.

* /display lists the banners with their links (Programme › Public displays leads to it).
* /display/<kind> is a banner: full screen, no menu, fitting any screen shape. Other sites may show it in
  a frame of their own (the players of the screens do), since it has nothing to click.
* /display/now.json gives the time of the portal and the couplet of the moment; the banner's script asks
  for it when the couplet is due to change, and keeps showing the last one when the network is down.

The couplet of the moment: the time is cut into slots of `every` minutes (15 unless the link says
otherwise, 1 to 60); each slot takes the next couplet of the banner's set, in an order that is the same
everywhere. ?n= fixes one couplet; ?local= adds a third language to Tamil, Hindi and English.
"""
import random
import time
from datetime import datetime
from functools import lru_cache

from flask import Blueprint, abort, current_app, jsonify, render_template, request

from . import kural as K
from .db import all_settings
from .utils import IST, qr_data_uri

bp = Blueprint("display", __name__)

# the banners, in the order of the list; the set of couplets of each
KINDS = ("welcome", "kural", "languages", "platform", "countdown", "thanks")
SETS = {
    "welcome": tuple(range(81, 91)),       # Hospitality (விருந்தோம்பல்)
    "platform": tuple(range(481, 491)),    # Knowing the fitting time (காலமறிதல்)
    "countdown": tuple(range(391, 401)),   # Learning (கல்வி): Thirukkural Payilvom
    "thanks": tuple(range(101, 111)),      # Gratitude (செய்ந்நன்றியறிதல்)
}
DEFAULT_EVERY = {"welcome": 10, "kural": 15, "languages": 15, "platform": 10, "countdown": 15, "thanks": 10}
LANG_SECONDS = 8                            # each translation on the "languages" banner
WEEKDAYS = {
    "ta": ("திங்கள்", "செவ்வாய்", "புதன்", "வியாழன்", "வெள்ளி", "சனி", "ஞாயிறு"),
    "hi": ("सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"),
}


@lru_cache(maxsize=1)
def _all_order():
    """All 1,330 couplets in one fixed order, the same on every screen."""
    order = list(range(1, 1331))
    random.Random("kts5-display").shuffle(order)
    return tuple(order)


def pool(kind):
    return SETS.get(kind) or _all_order()


def _int(value, low, high, default):
    try:
        return min(max(int(value), low), high)
    except (TypeError, ValueError):
        return default


def options(kind, args):
    """The options of a banner's link: every (minutes), local (a third language), n (a fixed couplet)."""
    every = _int(args.get("every"), 1, 60, DEFAULT_EVERY[kind])
    local = args.get("local") or ""
    if local not in K.ORIENTATION_LANGS or local in ("ta", "hi", "en"):
        local = ""
    n = _int(args.get("n"), 1, 1330, 0)
    return {"every": every, "local": local, "n": n}


def moment(kind, opts, now=None):
    """The slot of the time and the couplet it shows: (couplet number, slot, seconds until the next slot)."""
    now = now if now is not None else time.time()
    span = opts["every"] * 60
    slot = int(now // span)
    left = span - (now - slot * span)
    if opts["n"]:
        return opts["n"], slot, left
    couplets = pool(kind)
    return couplets[slot % len(couplets)], slot, left


@lru_cache(maxsize=2048)
def _qr(n):
    return qr_data_uri(f"{current_app.config['BASE_URL']}/thirukkural/{n}")


def _lines(k, code):
    """The lines of a translation as a screen shows them: without the stray * of the source (bold or footnote marks)."""
    return [" ".join(line.replace("*", " ").split()) for line in (K.lines(k, code) or [])]


def couplet(n, local="", streams=False):
    """What a banner shows of a couplet: Tamil, Hindi and English (and a third language), or every stream."""
    k = K.kural(n)
    out = {"n": n, "ta": K.lines(k, "ta"), "hi": _lines(k, "hi"), "en": _lines(k, "en"),
           "chapter_ta": k["chapter_name"], "chapter_en": k["chapter_name_en"], "chapter": k["adhigaram"],
           "url": f"{current_app.config['BASE_URL']}/thirukkural/{n}", "qr": _qr(n), "local": None}
    if local:
        info = K.lang_info(local) or {}
        out["local"] = {"code": local, "tag": K.lang_tag(local), "name": info.get("native", local),
                        "dir": info.get("dir", "ltr"), "lines": _lines(k, local)}
    if streams:
        out["streams"] = []
        for code in K.ORIENTATION_LANGS:
            if code == "ta":
                continue
            info = K.lang_info(code) or {}
            lines = _lines(k, code)
            if lines:
                out["streams"].append({"code": code, "tag": K.lang_tag(code), "name": info.get("native", code),
                                       "en_name": info.get("name", code), "dir": info.get("dir", "ltr"), "lines": lines})
    return out


def _kts_dates(settings):
    """The start of Kashi Tamil Sangamam 5.0 (ISO, IST), its last day, and the two as words: 28 Nov – 12 Dec 2026."""
    from .public import kts_at
    start = kts_at(settings)
    last = (settings.get("kts.end") or "")[:10]
    try:
        end = datetime.fromisoformat(last)
        words = f"{start:%d %b} – {end:%d %b %Y}" if start else ""
    except ValueError:
        words = f"{start:%d %b %Y}" if start else ""
    return (start.isoformat() if start else ""), last, words


@bp.route("/display")
def index():
    settings = all_settings()
    base = current_app.config["BASE_URL"]
    return render_template("display/index.html", kinds=KINDS, base=base, every=DEFAULT_EVERY, settings=settings,
                           langs=[(c, (K.lang_info(c) or {}).get("native", c)) for c in K.ORIENTATION_LANGS if c not in ("ta", "hi", "en")])


@bp.route("/display/<kind>")
def screen(kind):
    if kind not in KINDS:
        abort(404)
    settings = all_settings()
    opts = options(kind, request.args)
    n, slot, left = moment(kind, opts)
    start, end, words = _kts_dates(settings)
    now = datetime.now(IST)
    return render_template("display/screen.html", kind=kind, opts=opts, k=couplet(n, opts["local"], kind == "languages"),
                           slot=slot, left=int(left), kts_start=start, kts_end=end, kts_words=words, now=now,
                           weekday_ta=WEEKDAYS["ta"][now.weekday()], weekday_hi=WEEKDAYS["hi"][now.weekday()],
                           lang_seconds=LANG_SECONDS)


@bp.route("/display/now.json")
def now_json():
    kind = request.args.get("kind") or "kural"
    if kind not in KINDS:
        abort(404)
    opts = options(kind, request.args)
    n, slot, left = moment(kind, opts)
    return jsonify({"epoch_ms": int(time.time() * 1000), "slot": slot, "next_ms": int(left * 1000),
                    "kural": couplet(n, opts["local"], kind == "languages")})


@bp.after_app_request
def _screens(resp):
    """The banners may be shown in the frame of a screen's player; nothing on them is to be clicked. Never cached."""
    path = request.path
    if path.startswith("/display/") and resp.status_code == 200:
        resp.headers["Cache-Control"] = "no-store"
        if path != "/display/now.json":
            resp.headers.pop("X-Frame-Options", None)
            csp = resp.headers.get("Content-Security-Policy", "")
            if csp:
                resp.headers["Content-Security-Policy"] = csp.replace("frame-ancestors 'self'", "frame-ancestors *")
    return resp

"""
Classroom quiz: a live Thirukkural quiz for a class, as at the presentation that a selected student
gives in his or her college. The host shows the quiz on the projector (/quiz/host/<code>); the
students join on their phones at /quiz with the six digits of the code and a name, and answer each
question within its time. A correct answer earns 1,000 points at once and 500 at the last moment;
the answer, the couplet and a leaderboard follow each question, a podium the last one.

The questions are made from the corpus when the quiz is created, in the language that the host
chooses (one of the 23 of the test), in the kinds of the question generator of the test: complete
the couplet, the chapter, the section, general knowledge. They are never those of the question
bank of the test.

Live updates: the screens ask for the state every second or two. No socket: behind IIS, Waitress
would hold one of its threads for every phone. Times are milliseconds of the server clock, and a
screen counts down from what the server says remains.

Who hosts: CICT staff signed in to the console, and, once the merit list is published, the selected
students signed in to the candidate portal (setting quiz.candidates). Anybody with the code joins as
a player, without an account; the name a player gives is shown to the class and is deleted with the
answers after KEEP_DAYS days.
"""
import json
import random
import re
import secrets
import sqlite3
import time
import unicodedata

from flask import (Blueprint, Response, abort, current_app, jsonify, redirect, render_template, request, session,
                   url_for)

from . import kural as K
from .admin import bp as console
from .auth import current_user, has_perm, login_required
from .db import all_settings, audit, execute, get_db, query, utcnow
from .i18n import CATALOG, LANG_INFO, STREAM_UI, corpus_lang, get_lang, t
from .utils import client_ip, csrf_token, csv_bytes, limiter, qr_data_uri

bp = Blueprint("quiz", __name__, url_prefix="/quiz")

READY_MS = 5000            # the question alone on the screen before its options appear
ROOM_HOURS = 6             # a quiz that its host never ended closes this long after it was made
KEEP_DAYS = 30             # then the names and answers of its players are deleted; the line of the list stays
COUNTS = (5, 10, 15, 20)   # questions in a quiz
SECONDS = (20, 30, 45, 60)  # time for one question
NAME_MAX = 24
# the four options: colour and shape, so that the answer is told by the shape as well
SHAPES = ("▲", "◆", "●", "■")
# characters kept in a name besides letters, marks, numbers, punctuation and spaces: the joiners
# that the Indian scripts need
JOINERS = {"‌", "‍"}


def _now_ms():
    return int(time.time() * 1000)


# ---- the questions ----------------------------------------------------------------------------

def quiz_languages():
    """(code, label) of the languages of the test: Tamil first, then as in the corpus."""
    return [(L["code"], K.lang_label(L["code"])) for L in K.languages() if L["code"] in K.ORIENTATION_LANGS]


def _shuffle(rng, options, right):
    order = list(range(len(options)))
    rng.shuffle(order)
    return [options[i] for i in order], order.index(right)


def _scope(scope):
    """(kind, kurals) of a scope: all, pal1 to pal3, ch1 to ch133; None for anything else."""
    kurals = list(K.corpus()["kurals"].values())
    if scope == "all":
        return "all", kurals
    m = re.fullmatch(r"pal([123])", scope or "")
    if m:
        return "pal", [k for k in kurals if k["pal_num"] == int(m.group(1))]
    m = re.fullmatch(r"ch(\d{1,3})", scope or "")
    if m and 1 <= int(m.group(1)) <= 133:
        return "chapter", list(K.chapter(int(m.group(1)))["kurals"])
    return None


def _stem_tag(lang):
    """lang and dir of the wording of a stem: that of the interface language in the script of the stream."""
    ui = STREAM_UI.get(lang) or "en"
    return K.lang_tag(ui), LANG_INFO.get(ui, LANG_INFO["en"])["dir"]


def _question(kind, stem, quote, options, answer, kural_no, lang):
    tag, direction = _stem_tag(lang)
    info = K.lang_info(lang) or {}
    return {"kind": kind, "stem": stem, "stem_tag": tag, "stem_dir": direction, "quote": quote,
            "options": options, "answer": answer, "kural": kural_no,
            "tag": K.lang_tag(lang), "dir": info.get("dir", "ltr")}


def _complete(k, lang, rng):
    if not K.has_two_lines(k, lang):
        return None
    same = [o for o in K.chapter(k["adhigaram"])["kurals"] if o["n"] != k["n"] and K.has_two_lines(o, lang)]
    if len(same) < 3:
        near = [o for o in K.corpus()["kurals"].values()
                if o["n"] != k["n"] and abs(o["adhigaram"] - k["adhigaram"]) <= 2 and K.has_two_lines(o, lang)]
        same += [o for o in near if o not in same]
    if len(same) < 3:
        return None
    first, second = K.lines(k, lang)
    options = [second] + [K.lines(o, lang)[1] for o in rng.sample(same, 3)]
    if len(set(options)) < 4:
        return None
    options, answer = _shuffle(rng, options, 0)
    return _question("complete", K._stem("complete", lang), [first + " …"], options, answer, k["n"], lang)


def _chapter(k, lang, rng, pal=None):
    text = K.lines(k, lang)
    if not text:
        return None
    ch = K.chapter(k["adhigaram"])
    others = [c for c in K.chapters() if c["adhigaram"] != ch["adhigaram"] and (pal is None or c["palNum"] == pal)]
    options = [K.chapter_label(ch, lang)] + [K.chapter_label(c, lang) for c in rng.sample(others, 3)]
    options, answer = _shuffle(rng, options, 0)
    return _question("chapter", K._stem("chapter", lang), text, options, answer, k["n"], lang)


def _section(k, lang, rng):
    text = K.lines(k, lang)
    if not text:
        return None
    options = [K.pal_label(1, lang), K.pal_label(2, lang), K.pal_label(3, lang), K._stem("none", lang).replace("\n", " / ")]
    options, answer = _shuffle(rng, options, k["pal_num"] - 1)
    return _question("section", K._stem("section", lang), text, options, answer, k["n"], lang)


def make_questions(lang, count, scope, rng):
    """
    `count` questions in `lang` from the couplets of `scope`, or fewer when the corpus has not
    enough text in that language. The whole Thirukkural: 40% complete the couplet, 30% the chapter,
    15% the section, 15% general knowledge (in English for a language without a set of its own,
    as in the test). One section: 60% complete, 40% the chapter, its options from the same section.
    One chapter: complete the couplet only. No couplet comes twice.
    """
    found = _scope(scope)
    if found is None or lang not in K.ORIENTATION_LANGS:
        return []
    kind, kurals = found
    pal = kurals[0]["pal_num"] if kind == "pal" else None
    if kind == "all":
        shares = [("complete", .40), ("chapter", .30), ("section", .15), ("gk", .15)]
    elif kind == "pal":
        shares = [("complete", .60), ("chapter", .40)]
    else:
        shares = [("complete", 1.0)]
    wanted, left = {}, count
    for name, share in shares[:-1]:
        wanted[name] = round(count * share)
        left -= wanted[name]
    wanted[shares[-1][0]] = left

    pool = list(kurals)
    rng.shuffle(pool)
    used, made = set(), {name: [] for name, _ in shares}
    makers = {"complete": lambda k: _complete(k, lang, rng), "chapter": lambda k: _chapter(k, lang, rng, pal),
              "section": lambda k: _section(k, lang, rng)}

    def fill(name, target):
        for k in pool:
            if len(made[name]) >= target:
                return
            if k["n"] in used:
                continue
            q = makers[name](k)
            if q is not None:
                used.add(k["n"])
                made[name].append(q)

    for name, _share in shares:
        if name == "gk":
            gk = K.GK.get(lang) or K.GK["en"]
            gk_lang = lang if lang in K.GK else "en"
            for stem, options, right in rng.sample(gk, min(wanted["gk"], len(gk))):
                options, answer = _shuffle(rng, list(options), right)
                made["gk"].append(_question("gk", stem, [], options, answer, None, gk_lang))
        else:
            fill(name, wanted[name])
    # a kind that fell short is made up by the others, in the order of their shares
    short = count - sum(len(v) for v in made.values())
    for name, _share in shares:
        if short <= 0:
            break
        if name != "gk":
            before = len(made[name])
            fill(name, before + short)
            short -= len(made[name]) - before
    out = [q for name, _share in shares for q in made[name]]
    rng.shuffle(out)
    return out[:count]


def points(elapsed_ms, limit_ms):
    """1,000 for a correct answer at once, 500 at the last moment."""
    elapsed_ms = min(max(elapsed_ms, 0), limit_ms)
    return round(1000 * (1 - elapsed_ms / limit_ms / 2))


def _kural_info(n, lang):
    k = K.kural(n)
    ch = K.chapter(k["adhigaram"])
    return {"n": n, "ta": [k["l1"], k["l2"]], "tr": K.lines(k, lang) if lang != "ta" else [],
            "chapter": K.chapter_label(ch, lang)}


# ---- rooms --------------------------------------------------------------------------------------

def _host():
    """(kind, id, name) of the visitor as a host: staff of the console, or a selected student."""
    user = current_user()
    if user is not None and not user["must_change_password"] and has_perm(user, "quiz.host"):
        return "staff", user["id"], user["name"]
    cid = session.get("cand_id")
    if cid:
        settings = all_settings()
        if settings.get("quiz.candidates") == "1" and settings.get("merit.published") == "1":
            cand = query("SELECT id, full_name FROM applications WHERE id = ? AND status = 'selected'", (cid,), one=True)
            if cand is not None:
                return "candidate", cand["id"], cand["full_name"]
    return None


def may_host_candidate(cand, settings):
    """True for a student who may host a quiz: selected, the merit list published, hosting open."""
    return (settings.get("quiz.on") == "1" and settings.get("quiz.candidates") == "1"
            and settings.get("merit.published") == "1" and cand["status"] == "selected")


def _alive_since():
    return _now_ms() - ROOM_HOURS * 3600 * 1000


def _open_room(code):
    """The quiz of a code that players may join and play in now."""
    return query("SELECT * FROM quiz_rooms WHERE code = ? AND ended_at IS NULL AND created_ms > ? ORDER BY id DESC LIMIT 1",
                 (code, _alive_since()), one=True)


def _hosted(code):
    """The quiz of this code that the visitor hosts; 404 for any other."""
    host = _host()
    if host is None or not re.fullmatch(r"\d{6}", code or ""):
        abort(404)
    room = query("SELECT * FROM quiz_rooms WHERE code = ? AND host_kind = ? AND host_id = ? ORDER BY id DESC LIMIT 1",
                 (code, host[0], host[1]), one=True)
    if room is None:
        abort(404)
    return room


def _stage(room, now):
    """lobby, ready (the question without its options), question, reveal, board or end."""
    if room["ended_at"] is not None or room["created_ms"] <= now - ROOM_HOURS * 3600 * 1000:
        return "end"
    if room["phase"] == "question":
        if now < room["q_start_ms"]:
            return "ready"
        return "question" if now < room["q_end_ms"] else "reveal"
    return room["phase"]


def _players(room_id):
    return query("SELECT COUNT(*) AS n FROM quiz_players WHERE room_id = ? AND removed = 0", (room_id,), one=True)["n"]


def _standings(room_id, limit):
    return query("SELECT id, name, score, right_count FROM quiz_players WHERE room_id = ? AND removed = 0 "
                 "ORDER BY score DESC, time_ms ASC, id ASC LIMIT ?", (room_id, limit))


def _rank(player):
    """Place of a player: those with more points, or as many points sooner, stand before."""
    return query("SELECT COUNT(*) AS n FROM quiz_players WHERE room_id = ? AND removed = 0 AND "
                 "(score > ? OR (score = ? AND (time_ms < ? OR (time_ms = ? AND id < ?))))",
                 (player["room_id"], player["score"], player["score"], player["time_ms"], player["time_ms"], player["id"]),
                 one=True)["n"] + 1


def _new_code():
    for _ in range(50):
        code = str(secrets.randbelow(900000) + 100000)
        if _open_room(code) is None:
            return code
    abort(503)


def _forget_old():
    """The players and answers of quizzes older than KEEP_DAYS days; the quizzes stay in the list."""
    old = _now_ms() - KEEP_DAYS * 86400 * 1000
    conn = get_db()
    conn.execute("DELETE FROM quiz_answers WHERE room_id IN (SELECT id FROM quiz_rooms WHERE created_ms < ?)", (old,))
    conn.execute("DELETE FROM quiz_players WHERE room_id IN (SELECT id FROM quiz_rooms WHERE created_ms < ?)", (old,))
    conn.commit()


def _ui_of(lang):
    """The interface language of a stream, when one is written in its script."""
    ui = STREAM_UI.get(lang)
    return ui if ui in LANG_INFO else None


def _strings():
    return {key[5:]: t(key) for key in CATALOG["en"] if key.startswith("quiz.")}


def _join_url(room):
    base = current_app.config["BASE_URL"].rstrip("/")
    ui = _ui_of(room["lang"])
    return f"{base}/quiz?code={room['code']}" + (f"&lang={ui}" if ui else "")


def _closed():
    return all_settings().get("quiz.on") != "1"


# ---- players ------------------------------------------------------------------------------------

def _clean_name(value):
    name = " ".join("".join(ch for ch in (value or "") if ch in JOINERS or not unicodedata.category(ch).startswith("C")).split())
    return name if 0 < len(name) <= NAME_MAX else None


def _player():
    token = session.get("quiz_player")
    if not token:
        return None
    return query("SELECT * FROM quiz_players WHERE token = ?", (token,), one=True)


@bp.route("/", methods=["GET", "POST"])
def join():
    error = None
    code = re.sub(r"\D", "", request.values.get("code") or "")[:6]
    name = request.form.get("name") or ""
    if request.method == "POST" and not _closed():
        ip = client_ip()
        name_ok = _clean_name(name)
        if limiter.blocked("quiz_code", ip, 30, 10 * 60) or not limiter.allow("quiz_join", ip, 600, 3600):
            error = t("reg.err_rate")
        elif name_ok is None:
            error = t("quiz.err_name")
        else:
            room = _open_room(code) if len(code) == 6 else None
            if room is None or _stage(room, _now_ms()) == "end":
                limiter.hit("quiz_code", ip, 10 * 60)
                error = t("quiz.err_code")
            elif _players(room["id"]) >= int(all_settings().get("quiz.max_players") or 200):
                error = t("quiz.err_full")
            else:
                taken = {r["name"].casefold() for r in query("SELECT name FROM quiz_players WHERE room_id = ?", (room["id"],))}
                shown, n = name_ok, 1
                while shown.casefold() in taken:
                    n += 1
                    shown = f"{name_ok} {n}"
                token = secrets.token_urlsafe(18)
                execute("INSERT INTO quiz_players(room_id, token, name, joined_at) VALUES(?,?,?,?)",
                        (room["id"], token, shown, utcnow()))
                execute("UPDATE quiz_rooms SET players = players + 1 WHERE id = ?", (room["id"],))
                session["quiz_player"] = token
                ui = _ui_of(room["lang"])
                # a player who chose no language reads the quiz in the language of its questions
                if ui and not session.get("lang") and not request.cookies.get("lang"):
                    return redirect(url_for("quiz.play", lang=ui))
                return redirect(url_for("quiz.play"))
    mine = _player()
    room = query("SELECT * FROM quiz_rooms WHERE id = ?", (mine["room_id"],), one=True) if mine else None
    back = room["code"] if room is not None and not mine["removed"] and _stage(room, _now_ms()) != "end" else None
    return render_template("quiz/join.html", error=error, code=code, name=name, back=back, closed=_closed(),
                           host=_host() is not None)


@bp.route("/play")
def play():
    player = _player()
    if player is None:
        return redirect(url_for("quiz.join"))
    room = query("SELECT * FROM quiz_rooms WHERE id = ?", (player["room_id"],), one=True)
    data = {"mode": "play", "state": url_for("quiz.state"), "answer": url_for("quiz.answer"), "csrf": csrf_token(),
            "join": url_for("quiz.join"), "strings": _strings(), "shapes": SHAPES, "ready_ms": READY_MS}
    return render_template("quiz/play.html", data=data, room=room, player=player)


@bp.route("/leave", methods=["POST"])
def leave():
    session.pop("quiz_player", None)
    return redirect(url_for("quiz.join"))


def _public_question(q):
    return {key: q[key] for key in ("kind", "stem", "stem_tag", "stem_dir", "quote", "options", "tag", "dir")}


@bp.route("/api/state")
def state():
    player = _player()
    if player is None:
        return jsonify({"stage": "gone"})
    if player["removed"]:
        return jsonify({"stage": "removed"})
    room = query("SELECT * FROM quiz_rooms WHERE id = ?", (player["room_id"],), one=True)
    now = _now_ms()
    stage = _stage(room, now)
    questions = json.loads(room["questions"])
    out = {"stage": stage, "index": room["q_index"], "total": len(questions), "code": room["code"],
           "me": {"name": player["name"], "score": player["score"]}}
    if stage == "ready":
        out["ready_ms"] = room["q_start_ms"] - now
    elif stage == "question":
        mine = query("SELECT choice FROM quiz_answers WHERE player_id = ? AND q_index = ?", (player["id"], room["q_index"]), one=True)
        out.update(question=_public_question(questions[room["q_index"]]), remaining_ms=room["q_end_ms"] - now,
                   limit_ms=room["q_end_ms"] - room["q_start_ms"], answered=None if mine is None else mine["choice"])
    elif stage in ("reveal", "board"):
        q = questions[room["q_index"]]
        mine = query("SELECT choice, correct, points FROM quiz_answers WHERE player_id = ? AND q_index = ?",
                     (player["id"], room["q_index"]), one=True)
        out["result"] = {"answered": mine is not None, "correct": bool(mine and mine["correct"]),
                         "points": mine["points"] if mine else 0, "answer": q["options"][q["answer"]],
                         "answer_index": q["answer"], "tag": q["tag"], "dir": q["dir"]}
    if stage in ("reveal", "board", "end"):
        out.update(rank=_rank(player), players=_players(room["id"]))
    if stage == "end":
        out["top"] = [{"name": r["name"], "score": r["score"]} for r in _standings(room["id"], 3)]
    return jsonify(out)


@bp.route("/api/answer", methods=["POST"])
def answer():
    player = _player()
    if player is None or player["removed"]:
        return jsonify({"ok": False, "reason": "gone"}), 404
    payload = request.get_json(silent=True) or {}
    index, choice = payload.get("q"), payload.get("choice")
    if type(index) is not int or type(choice) is not int or not 0 <= choice <= 3:
        return jsonify({"ok": False, "reason": "bad"}), 400
    room = query("SELECT * FROM quiz_rooms WHERE id = ?", (player["room_id"],), one=True)
    now = _now_ms()
    if _stage(room, now) != "question" or room["q_index"] != index:
        return jsonify({"ok": False, "reason": "late"}), 409
    q = json.loads(room["questions"])[index]
    right = q["answer"] == choice
    elapsed = now - room["q_start_ms"]
    gained = points(elapsed, room["q_end_ms"] - room["q_start_ms"]) if right else 0
    conn = get_db()
    try:
        conn.execute("INSERT INTO quiz_answers(room_id, player_id, q_index, choice, correct, points, ms) VALUES(?,?,?,?,?,?,?)",
                     (room["id"], player["id"], index, choice, int(right), gained, elapsed))
        conn.execute("UPDATE quiz_players SET score = score + ?, right_count = right_count + ?, time_ms = time_ms + ? WHERE id = ?",
                     (gained, int(right), elapsed if right else 0, player["id"]))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        return jsonify({"ok": False, "reason": "twice"}), 409
    # everybody has answered: the question ends now
    answered = query("SELECT COUNT(*) AS n FROM quiz_answers a JOIN quiz_players p ON p.id = a.player_id "
                     "WHERE a.room_id = ? AND a.q_index = ? AND p.removed = 0", (room["id"], index), one=True)["n"]
    if answered >= _players(room["id"]):
        execute("UPDATE quiz_rooms SET q_end_ms = ? WHERE id = ? AND q_index = ? AND q_end_ms > ?", (now, room["id"], index, now))
    return jsonify({"ok": True})


# ---- the host ---------------------------------------------------------------------------------------

@bp.route("/host", methods=["GET", "POST"])
def host_new():
    host = _host()
    if host is None or _closed():
        return render_template("quiz/host_new.html", host=None, closed=_closed())
    error = None
    ui_stream = corpus_lang()
    langs = quiz_languages()
    codes = [code for code, _label in langs]
    default_lang = ui_stream if ui_stream in codes else (get_lang() if get_lang() in codes else "en")
    if host[0] == "candidate":
        pref = query("SELECT pref_lang FROM applications WHERE id = ?", (host[1],), one=True)["pref_lang"]
        default_lang = pref if pref in codes else default_lang
    form = {"lang": request.form.get("lang") or default_lang, "scope": request.form.get("scope") or "all",
            "count": request.form.get("count") or "10", "seconds": request.form.get("seconds") or "30"}
    if request.method == "POST":
        try:
            count, seconds = int(form["count"]), int(form["seconds"])
        except ValueError:
            count = seconds = 0
        lang = form["lang"]
        questions = []
        if lang in codes and count in COUNTS and seconds in SECONDS and _scope(form["scope"]) is not None:
            questions = make_questions(lang, count, form["scope"], random.Random(secrets.randbits(64)))
        if not questions:
            error = t("quiz.no_questions")
        else:
            _forget_old()
            now = _now_ms()
            # one quiz at a time for a host: a new one ends the one before
            execute("UPDATE quiz_rooms SET phase = 'end', ended_at = ? WHERE host_kind = ? AND host_id = ? AND ended_at IS NULL",
                    (utcnow(), host[0], host[1]))
            code = _new_code()
            room_id = execute("INSERT INTO quiz_rooms(code, host_kind, host_id, host_name, lang, scope, seconds, questions, "
                              "created_at, created_ms) VALUES(?,?,?,?,?,?,?,?,?,?)",
                              (code, host[0], host[1], host[2], lang, form["scope"], seconds,
                               json.dumps(questions, ensure_ascii=False), utcnow(), now))
            audit("quiz_created", "quiz_room", room_id, detail={"code": code, "lang": lang, "questions": len(questions),
                                                                "host": f"{host[0]}:{host[1]}"},
                  user=current_user() if host[0] == "staff" else None, ip=client_ip())
            return redirect(url_for("quiz.host_screen", code=code))
    mine = query("SELECT * FROM quiz_rooms WHERE host_kind = ? AND host_id = ? AND ended_at IS NULL AND created_ms > ? "
                 "ORDER BY id DESC LIMIT 1", (host[0], host[1], _alive_since()), one=True)
    lang_now = corpus_lang()
    chapters = [(ch["adhigaram"], K.chapter_label(ch, lang_now)) for ch in K.chapters()]
    pals = [(n, K.pal_label(n, lang_now)) for n in (1, 2, 3)]
    return render_template("quiz/host_new.html", host=host, closed=False, error=error, form=form, langs=langs,
                           chapters=chapters, pals=pals, counts=COUNTS, seconds=SECONDS, mine=mine)


@bp.route("/host/<code>")
def host_screen(code):
    room = _hosted(code)
    join_url = _join_url(room)
    shown = re.sub(r"^https?://", "", current_app.config["BASE_URL"].rstrip("/")) + "/quiz"
    data = {"mode": "host", "state": url_for("quiz.host_state", code=code), "action": url_for("quiz.host_action", code=code),
            "csrf": csrf_token(), "strings": _strings(), "shapes": SHAPES, "ready_ms": READY_MS}
    return render_template("quiz/host.html", data=data, room=room, qr=qr_data_uri(join_url), shown=shown,
                           scope_label=_scope_label(room["scope"]), total=len(json.loads(room["questions"])))


def _scope_label(scope):
    lang = corpus_lang()
    m = re.fullmatch(r"(pal|ch)(\d+)", scope)
    if m is None:
        return t("quiz.scope_all")
    n = int(m.group(2))
    return K.pal_label(n, lang) if m.group(1) == "pal" else f"{n}. {K.chapter_label(K.chapter(n), lang)}"


@bp.route("/host/<code>/state")
def host_state(code):
    room = _hosted(code)
    now = _now_ms()
    stage = _stage(room, now)
    questions = json.loads(room["questions"])
    index = room["q_index"]
    out = {"stage": stage, "index": index, "total": len(questions), "players": _players(room["id"])}
    if stage == "lobby":
        out["names"] = [{"id": r["id"], "name": r["name"]} for r in
                        query("SELECT id, name FROM quiz_players WHERE room_id = ? AND removed = 0 ORDER BY id LIMIT 400", (room["id"],))]
    if stage in ("ready", "question", "reveal"):
        out["question"] = _public_question(questions[index])
        out["answered"] = query("SELECT COUNT(*) AS n FROM quiz_answers a JOIN quiz_players p ON p.id = a.player_id "
                                "WHERE a.room_id = ? AND a.q_index = ? AND p.removed = 0", (room["id"], index), one=True)["n"]
    if stage == "ready":
        out["ready_ms"] = room["q_start_ms"] - now
    elif stage == "question":
        out.update(remaining_ms=room["q_end_ms"] - now, limit_ms=room["q_end_ms"] - room["q_start_ms"])
    elif stage == "reveal":
        q = questions[index]
        counts = [0, 0, 0, 0]
        for r in query("SELECT a.choice, COUNT(*) AS n FROM quiz_answers a JOIN quiz_players p ON p.id = a.player_id "
                       "WHERE a.room_id = ? AND a.q_index = ? AND p.removed = 0 GROUP BY a.choice", (room["id"], index)):
            counts[r["choice"]] = r["n"]
        out.update(answer=q["answer"], counts=counts, last=index + 1 >= len(questions))
        if q["kural"]:
            out["kural"] = _kural_info(q["kural"], room["lang"])
    elif stage == "board":
        gained = {r["player_id"]: r["points"] for r in
                  query("SELECT player_id, points FROM quiz_answers WHERE room_id = ? AND q_index = ?", (room["id"], index))}
        out["board"] = [{"name": r["name"], "score": r["score"], "gained": gained.get(r["id"], 0)} for r in _standings(room["id"], 5)]
        out["last"] = index + 1 >= len(questions)
    elif stage == "end":
        out["board"] = [{"name": r["name"], "score": r["score"], "right": r["right_count"]} for r in _standings(room["id"], 10)]
    return jsonify(out)


def _ask(room, index, now):
    """Question `index` on the screens: alone for READY_MS, then with its options for the time of the quiz."""
    start = now + READY_MS
    execute("UPDATE quiz_rooms SET phase = 'question', q_index = ?, q_start_ms = ?, q_end_ms = ? WHERE id = ? AND q_index = ?",
            (index, start, start + room["seconds"] * 1000, room["id"], room["q_index"]))


def _finish(room):
    execute("UPDATE quiz_rooms SET phase = 'end', ended_at = ? WHERE id = ? AND ended_at IS NULL", (utcnow(), room["id"]))


@bp.route("/host/<code>/action", methods=["POST"])
def host_action(code):
    room = _hosted(code)
    payload = request.get_json(silent=True) or {}
    action, at = payload.get("action"), payload.get("index")
    now = _now_ms()
    stage = _stage(room, now)
    total = len(json.loads(room["questions"]))
    # the screen says which question it showed: a second click, or a second screen, does nothing twice
    current = at == room["q_index"]
    if action == "start" and stage == "lobby":
        if _players(room["id"]) == 0:
            return jsonify({"ok": False, "reason": "nobody"}), 409
        _ask(room, 0, now)
    elif action == "skip" and stage in ("ready", "question") and current:
        execute("UPDATE quiz_rooms SET q_start_ms = MIN(q_start_ms, ?), q_end_ms = ? WHERE id = ? AND q_index = ?",
                (now, now, room["id"], room["q_index"]))
    elif action == "board" and stage == "reveal" and current:
        execute("UPDATE quiz_rooms SET phase = 'board' WHERE id = ? AND q_index = ?", (room["id"], room["q_index"]))
    elif action == "next" and stage in ("reveal", "board") and current:
        if room["q_index"] + 1 < total:
            _ask(room, room["q_index"] + 1, now)
        else:
            _finish(room)
    elif action == "end" and stage != "end":
        _finish(room)
        audit("quiz_ended", "quiz_room", room["id"], detail={"code": room["code"], "players": _players(room["id"])},
              user=current_user() if room["host_kind"] == "staff" else None, ip=client_ip())
    elif action == "remove" and type(payload.get("player")) is int:
        execute("UPDATE quiz_players SET removed = 1 WHERE id = ? AND room_id = ?", (payload["player"], room["id"]))
    else:
        return jsonify({"ok": False, "reason": "stage"}), 409
    return jsonify({"ok": True})


def _csv_text(value):
    """A name as a spreadsheet shows it: never read as a formula."""
    value = str(value)
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


@bp.route("/host/<code>/results.csv")
def host_results(code):
    room = _hosted(code)
    total = len(json.loads(room["questions"]))
    rows = [(i, _csv_text(r["name"]), r["score"], f"{r['right_count']}/{total}")
            for i, r in enumerate(_standings(room["id"], 10000), start=1)]
    body = csv_bytes(["Place", "Name", "Points", "Correct answers"], rows)
    return Response(body, mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="quiz-{room["code"]}-{room["created_at"][:10]}.csv"'})


# ---- the console ------------------------------------------------------------------------------------

@console.route("/quizzes")
@login_required("quiz.host")
def quizzes():
    user = current_user()
    everyone = has_perm(user, "apps.view")
    sql = "SELECT * FROM quiz_rooms"
    args = ()
    if not everyone:
        sql += " WHERE host_kind = 'staff' AND host_id = ?"
        args = (user["id"],)
    rooms = query(sql + " ORDER BY id DESC LIMIT 300", args)
    hosts = {}
    ids = [r["host_id"] for r in rooms if r["host_kind"] == "candidate"]
    if ids:
        marks = ",".join("?" * len(ids))
        hosts = {r["id"]: r["app_no"] for r in query(f"SELECT id, app_no FROM applications WHERE id IN ({marks})", ids)}
    now = _now_ms()
    lines = [{"room": r, "stage": _stage(r, now), "questions": len(json.loads(r["questions"])),
              "app_no": hosts.get(r["host_id"]) if r["host_kind"] == "candidate" else None} for r in rooms]
    return render_template("console/quizzes.html", lines=lines, everyone=everyone, settings=all_settings())

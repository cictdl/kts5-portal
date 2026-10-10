"""
The practice test for students (version 1.2.54): practice.questions questions in practice.minutes
minutes, in any of the 23 languages of the test, on the very screen of the online test (the same
page, timer and saving), so that a student meets it before the institution's assessment.

* The questions are made afresh for each attempt from CICT's Thirukkural (kural.generate_questions:
  complete the couplet, name the chapter, name the section), never taken from the question bank:
  the general-knowledge questions, of which there are few, are left out, and so is any couplet that
  the bank asks in the same way in that language. A practice question is therefore never a question
  of the assessments.
* Nothing is written in the database and nobody signs in: the attempt (the language, the seed of its
  questions, the questions picked, the deadline and the answers) is kept in the visitor's session,
  and the questions are made again from the seed at each page. At the end the student sees the
  score and, for each question, the right answer and a link to the couplet.
"""
import json
import secrets
from datetime import timedelta

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from . import kural as K
from .db import all_settings, query
from .i18n import get_lang, t
from .utils import client_ip, limiter, now_ist, parse_iso

bp = Blueprint("practice", __name__)

KEY = "practice"
KINDS = ("complete", "chapter", "section")
GRACE_SECONDS = 45       # as the test: a paper that comes in within this after the time is up counts


def _numbers(settings):
    def num(key, default, low, high):
        try:
            return min(max(int(settings.get(key) or default), low), high)
        except ValueError:
            return default
    return num("practice.questions", 10, 3, 30), num("practice.minutes", 6, 1, 60)


def make(lang, n, seed):
    """
    The questions of a practice paper: n questions of the kinds of KINDS, none asked in the same way of
    the same couplet by the question bank in this language. Gives the generated rows (kural_no, qtype,
    text, opt_a..opt_d, correct).
    """
    taken = {(r["qtype"], r["kural_no"]) for r in query(
        "SELECT DISTINCT qtype, kural_no FROM questions WHERE lang = ? AND kural_no IS NOT NULL", (lang,))}
    out, seen = [], set()
    for round_ in range(4):
        for r in K.generate_questions(lang, 40, f"{seed}-{round_}"):
            key = (r["qtype"], r["kural_no"])
            if r["qtype"] not in KINDS or key in taken or key in seen:
                continue
            seen.add(key)
            out.append(r)
            if len(out) == n:
                return out
    return out


def rows_for(lang, seed, picks):
    """The rows of the questions picked at the start of an attempt, made again from its seed, in their order."""
    found = {}
    for round_ in range(4):
        for r in K.generate_questions(lang, 40, f"{seed}-{round_}"):
            found.setdefault((r["qtype"], r["kural_no"]), r)
        if all(tuple(p) in found for p in picks):
            break
    return [found[tuple(p)] for p in picks if tuple(p) in found]


def _attempt():
    a = session.get(KEY)
    return a if isinstance(a, dict) and a.get("lang") in K.ORIENTATION_LANGS and a.get("seed") else None


def _questions(a):
    rows = rows_for(a["lang"], a["seed"], a.get("picks") or [])
    return [{"no": i, "id": i, "text": r["text"], "options": [(L, r[f"opt_{L.lower()}"]) for L in "ABCD"],
             "correct": r["correct"], "kural_no": r["kural_no"]} for i, r in enumerate(rows, 1)]


def _remaining(a):
    return int((parse_iso(a["deadline"]) - now_ist()).total_seconds())


def _finish(a, answers=None):
    """Mark the attempt over and keep its result in the session."""
    if a.get("done"):
        return a
    questions = _questions(a)
    given = dict(a.get("answers") or {})
    for qid, letter in (answers or {}).items():
        if str(qid) in {str(q["id"]) for q in questions} and letter in ("A", "B", "C", "D"):
            given[str(qid)] = letter
    a["answers"] = given
    a["correct"] = sum(1 for q in questions if given.get(str(q["id"])) == q["correct"])
    a["late"] = _remaining(a) < 0
    a["done"] = True
    session[KEY] = a
    return a


@bp.route("/practice")
def home():
    settings = all_settings()
    n, minutes = _numbers(settings)
    lang = get_lang()
    return render_template("public/practice.html", settings=settings, n=n, minutes=minutes, on=settings.get("practice.on") == "1",
                           langs=[(K.lang_info(c) or {}) | {"code": c} for c in K.ORIENTATION_LANGS],
                           chosen=lang if lang in K.ORIENTATION_LANGS else "en", attempt=_attempt())


@bp.route("/practice/start", methods=["POST"])
def start():
    settings = all_settings()
    if settings.get("practice.on") != "1":
        abort(404)
    lang = request.form.get("lang") or "en"
    if lang not in K.ORIENTATION_LANGS:
        abort(400)
    if not limiter.allow("practice", client_ip(), current_app.config["RATE_PRACTICE_PER_HOUR"], 3600):
        flash(t("reg.err_rate"), "error")
        return redirect(url_for("practice.home"))
    n, minutes = _numbers(settings)
    seed = secrets.token_hex(6)
    picks = [[r["qtype"], r["kural_no"]] for r in make(lang, n, seed)]
    a = {"lang": lang, "seed": seed, "picks": picks, "n": len(picks), "answers": {},
         "deadline": (now_ist() + timedelta(minutes=minutes)).isoformat()}
    if not picks:
        flash(t("prac.closed"), "error")
        return redirect(url_for("practice.home"))
    session[KEY] = a
    return redirect(url_for("practice.paper"))


@bp.route("/practice/paper")
def paper():
    a = _attempt()
    if a is None:
        return redirect(url_for("practice.home"))
    if a.get("done"):
        return redirect(url_for("practice.result"))
    if _remaining(a) < -GRACE_SECONDS:
        _finish(a)
        return redirect(url_for("practice.result"))
    info = K.lang_info(a["lang"]) or {}
    return render_template("candidate/exam_paper.html", questions=_questions(a), answers=a.get("answers") or {},
                           remaining=max(0, _remaining(a)), qlang=a["lang"], qdir=info.get("dir", "ltr"),
                           who=t("prac.who"), heading=t("prac.title"),
                           save_url=url_for("practice.save"), submit_url=url_for("practice.submit"))


@bp.route("/practice/save", methods=["POST"])
def save():
    a = _attempt()
    if a is None or a.get("done"):
        return jsonify({"ok": False, "reason": "closed"}), 409
    if _remaining(a) < -GRACE_SECONDS:
        _finish(a)
        return jsonify({"ok": False, "reason": "expired"}), 409
    payload = request.get_json(silent=True) or {}
    answers = dict(a.get("answers") or {})
    valid = {str(i) for i in range(1, a["n"] + 1)}
    for qid, letter in (payload.get("answers") or {}).items():
        if qid in valid and letter in ("A", "B", "C", "D", ""):
            if letter:
                answers[qid] = letter
            else:
                answers.pop(qid, None)
    a["answers"] = answers
    session[KEY] = a
    return jsonify({"ok": True, "saved": len(answers), "remaining": max(0, _remaining(a))})


@bp.route("/practice/submit", methods=["POST"])
def submit():
    a = _attempt()
    if a is None:
        return redirect(url_for("practice.home"))
    sent = {}
    try:
        sent = json.loads(request.form.get("answers") or "{}")
    except ValueError:
        pass
    _finish(a, sent if isinstance(sent, dict) else {})
    return redirect(url_for("practice.result"))


@bp.route("/practice/result")
def result():
    a = _attempt()
    if a is None:
        return redirect(url_for("practice.home"))
    if not a.get("done"):
        if _remaining(a) >= -GRACE_SECONDS:
            return redirect(url_for("practice.paper"))
        a = _finish(a)
    info = K.lang_info(a["lang"]) or {}
    return render_template("public/practice_result.html", a=a, questions=_questions(a), answers=a.get("answers") or {},
                           qlang=a["lang"], qdir=info.get("dir", "ltr"))

"""
Candidate portal: sign in with the application number, view the
acknowledgement and admit card, take the timed online test, see the result.
"""
import json
import random
from datetime import timedelta
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)

from . import kural as K
from .auth import candidate_required
from .db import all_settings, audit, execute, query, utcnow
from .i18n import t
from .utils import client_ip, exam_window, limiter, now_ist, parse_iso, qr_data_uri

bp = Blueprint("candidate", __name__, url_prefix="/candidate")


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if not limiter.allow("cand_login", client_ip(), current_app.config["RATE_LOGIN_PER_15MIN"], 15 * 60):
            error = t("reg.err_rate")
        else:
            app_no = (request.form.get("app_no") or "").strip().upper()
            dob = (request.form.get("dob") or "").strip()
            last4 = (request.form.get("last4") or "").strip()
            row = query("SELECT * FROM applications WHERE app_no = ? AND dob = ? AND substr(mobile, -4) = ?",
                        (app_no, dob, last4), one=True)
            if row is None:
                error = t("status.not_found")
                audit("candidate_login_failed", "application", None, detail=app_no, ip=client_ip())
            else:
                session.pop("uid", None)
                session["cand_id"] = row["id"]
                session.permanent = True
                audit("candidate_login", "application", row["id"], ip=client_ip())
                return redirect(url_for("candidate.home"))
    return render_template("candidate/login.html", error=error, settings=all_settings())


@bp.route("/logout", methods=["POST"])
def logout():
    session.pop("cand_id", None)
    return redirect(url_for("public.home"))


def _exam_session(cand):
    return query("SELECT * FROM exam_sessions WHERE application_id = ?", (cand["id"],), one=True)


@bp.route("/")
@candidate_required
def home():
    cand = g.candidate
    settings = all_settings()
    start, end, is_open = exam_window(settings)
    exam = _exam_session(cand)
    sessions = query("SELECT * FROM events WHERE published = 1 AND kind = 'orientation' AND lang = ? ORDER BY starts_at",
                     (cand["pref_lang"],))
    materials = query("SELECT * FROM resources WHERE published = 1 AND (lang = ? OR lang = '') "
                      "AND category IN ('video', 'study', 'translation', 'audio') ORDER BY sort_order LIMIT 12",
                      (cand["pref_lang"],))
    merit = query("SELECT * FROM merit_list WHERE application_id = ?", (cand["id"],), one=True) \
        if settings.get("merit.published") == "1" else None
    return render_template("candidate/home.html", cand=cand, settings=settings, start=start, end=end,
                           is_open=is_open, exam=exam, sessions=sessions, materials=materials, merit=merit,
                           lang_name=K.lang_info(cand["pref_lang"])["name"])


@bp.route("/acknowledgement")
@candidate_required
def ack():
    cand = g.candidate
    return render_template("public/register_done.html", app=cand, printable=True,
                           qr=qr_data_uri(f"{current_app.config['BASE_URL']}/status?app={cand['app_no']}"),
                           lang_name=K.lang_info(cand["pref_lang"])["name"], settings=all_settings())


@bp.route("/admit-card")
@candidate_required
def admit_card():
    cand = g.candidate
    settings = all_settings()
    if cand["status"] not in ("verified", "selected", "waitlisted", "not_selected"):
        flash(t("exam.not_eligible"), "warning")
        return redirect(url_for("candidate.home"))
    start, end, _ = exam_window(settings)
    return render_template("candidate/admit_card.html", cand=cand, settings=settings, start=start, end=end,
                           qr=qr_data_uri(cand["app_no"]), lang_name=K.lang_info(cand["pref_lang"])["name"])


@bp.route("/photo")
@candidate_required
def photo():
    cand = g.candidate
    if not cand["photo_path"]:
        abort(404)
    return send_from_directory(Path(current_app.config["UPLOAD_DIR"]), cand["photo_path"])


# ---- the test ---------------------------------------------------------------

def _build_paper(lang, n_questions, rng):
    """Pick n active questions in `lang`, topping up from English if short."""
    rows = query("SELECT id FROM questions WHERE active = 1 AND lang = ?", (lang,))
    ids = [r["id"] for r in rows]
    rng.shuffle(ids)
    ids = ids[:n_questions]
    if len(ids) < n_questions and lang != "en":
        extra = [r["id"] for r in query("SELECT id FROM questions WHERE active = 1 AND lang = 'en'")]
        rng.shuffle(extra)
        ids += extra[: n_questions - len(ids)]
    paper = []
    for qid in ids:
        order = ["A", "B", "C", "D"]
        rng.shuffle(order)
        paper.append({"q": qid, "order": order})
    return paper


@bp.route("/exam", methods=["GET", "POST"])
@candidate_required
def exam():
    cand = g.candidate
    settings = all_settings()
    start, end, is_open = exam_window(settings)
    exam = _exam_session(cand)
    if exam and exam["status"] != "in_progress":
        return redirect(url_for("candidate.result"))
    eligible = cand["status"] in ("verified", "selected", "waitlisted", "not_selected")
    if request.method == "POST":
        if not eligible:
            flash(t("exam.not_eligible"), "error")
            return redirect(url_for("candidate.home"))
        if not is_open and exam is None:
            flash(t("exam.not_open"), "error")
            return redirect(url_for("candidate.home"))
        if exam is None:
            n_q = int(settings.get("exam.questions", "25"))
            duration = int(settings.get("exam.duration_min", "30"))
            rng = random.Random(f"{cand['id']}-{utcnow()}")
            paper = _build_paper(cand["pref_lang"], n_q, rng)
            if not paper:
                flash("No questions are available for your language yet. Please contact the helpdesk.", "error")
                return redirect(url_for("candidate.home"))
            started = now_ist()
            deadline = started + timedelta(minutes=duration)
            execute("INSERT INTO exam_sessions(application_id, lang, paper_json, started_at, deadline_at, ip, user_agent) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (cand["id"], cand["pref_lang"], json.dumps(paper), started.isoformat(), deadline.isoformat(),
                     client_ip(), (request.user_agent.string or "")[:200]))
            audit("exam_started", "application", cand["id"], ip=client_ip())
        return redirect(url_for("candidate.paper"))
    return render_template("candidate/exam_start.html", cand=cand, settings=settings, start=start, end=end,
                           is_open=is_open, exam=exam, eligible=eligible)


def _load_paper(exam):
    paper = json.loads(exam["paper_json"])
    ids = [p["q"] for p in paper]
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    rows = {r["id"]: r for r in query(f"SELECT * FROM questions WHERE id IN ({marks})", ids)}
    out = []
    for i, p in enumerate(paper, start=1):
        q = rows.get(p["q"])
        if q is None:
            continue
        opts = [(letter, q[f"opt_{letter.lower()}"]) for letter in p["order"]]
        out.append({"no": i, "id": q["id"], "text": q["text"], "options": opts})
    return out


def _deadline_passed(exam):
    deadline = parse_iso(exam["deadline_at"])
    return now_ist() > deadline + timedelta(seconds=45)


def _finalise(exam, reason="submitted"):
    paper = json.loads(exam["paper_json"])
    answers = json.loads(exam["answers_json"] or "{}")
    ids = [p["q"] for p in paper]
    marks = ",".join("?" * len(ids))
    correct = {r["id"]: r["correct"] for r in query(f"SELECT id, correct FROM questions WHERE id IN ({marks})", ids)}
    settings = all_settings()
    per_q = float(settings.get("exam.marks_per_q", "4"))
    neg = float(settings.get("exam.negative", "0"))
    right = wrong = 0
    for qid in ids:
        ans = answers.get(str(qid))
        if not ans:
            continue
        if ans == correct.get(qid):
            right += 1
        else:
            wrong += 1
    score = right * per_q - wrong * neg
    started = parse_iso(exam["started_at"])
    ended = min(now_ist(), parse_iso(exam["deadline_at"]) + timedelta(seconds=45))
    taken = int((ended - started).total_seconds())
    execute("UPDATE exam_sessions SET status = ?, submitted_at = ?, score = ?, correct_count = ?, time_taken_sec = ? WHERE id = ?",
            (reason, ended.isoformat(), score, right, taken, exam["id"]))
    execute("UPDATE applications SET exam_score = ?, updated_at = ? WHERE id = ?", (score, utcnow(), exam["application_id"]))
    audit("exam_" + reason, "application", exam["application_id"], detail={"score": score, "right": right}, ip=client_ip())
    return score


@bp.route("/exam/paper")
@candidate_required
def paper():
    cand = g.candidate
    exam = _exam_session(cand)
    if exam is None:
        return redirect(url_for("candidate.exam"))
    if exam["status"] != "in_progress":
        return redirect(url_for("candidate.result"))
    if _deadline_passed(exam):
        _finalise(exam, "expired")
        return redirect(url_for("candidate.result"))
    questions = _load_paper(exam)
    answers = json.loads(exam["answers_json"] or "{}")
    remaining = int((parse_iso(exam["deadline_at"]) - now_ist()).total_seconds())
    return render_template("candidate/exam_paper.html", cand=cand, exam=exam, questions=questions,
                           answers=answers, remaining=max(0, remaining), lang=exam["lang"],
                           dir="rtl" if exam["lang"] in ("ur", "ksn") else "ltr")


@bp.route("/exam/save", methods=["POST"])
@candidate_required
def save():
    cand = g.candidate
    exam = _exam_session(cand)
    if exam is None or exam["status"] != "in_progress":
        return jsonify({"ok": False, "reason": "closed"}), 409
    if _deadline_passed(exam):
        _finalise(exam, "expired")
        return jsonify({"ok": False, "reason": "expired"}), 409
    payload = request.get_json(silent=True) or {}
    answers = json.loads(exam["answers_json"] or "{}")
    valid_ids = {str(p["q"]) for p in json.loads(exam["paper_json"])}
    for qid, letter in (payload.get("answers") or {}).items():
        if qid in valid_ids and letter in ("A", "B", "C", "D", ""):
            if letter:
                answers[qid] = letter
            else:
                answers.pop(qid, None)
    execute("UPDATE exam_sessions SET answers_json = ? WHERE id = ?", (json.dumps(answers), exam["id"]))
    remaining = int((parse_iso(exam["deadline_at"]) - now_ist()).total_seconds())
    return jsonify({"ok": True, "saved": len(answers), "remaining": max(0, remaining)})


@bp.route("/exam/submit", methods=["POST"])
@candidate_required
def submit():
    cand = g.candidate
    exam = _exam_session(cand)
    if exam is None:
        return redirect(url_for("candidate.exam"))
    if exam["status"] == "in_progress":
        payload = request.form.get("answers")
        if payload:
            try:
                answers = json.loads(exam["answers_json"] or "{}")
                valid_ids = {str(p["q"]) for p in json.loads(exam["paper_json"])}
                for qid, letter in json.loads(payload).items():
                    if qid in valid_ids and letter in ("A", "B", "C", "D"):
                        answers[qid] = letter
                execute("UPDATE exam_sessions SET answers_json = ? WHERE id = ?", (json.dumps(answers), exam["id"]))
                exam = _exam_session(cand)
            except ValueError:
                pass
        _finalise(exam, "expired" if _deadline_passed(exam) else "submitted")
    return redirect(url_for("candidate.result"))


@bp.route("/exam/result")
@candidate_required
def result():
    cand = g.candidate
    exam = _exam_session(cand)
    if exam is None:
        return redirect(url_for("candidate.exam"))
    if exam["status"] == "in_progress":
        return redirect(url_for("candidate.paper"))
    settings = all_settings()
    total = len(json.loads(exam["paper_json"]))
    return render_template("candidate/exam_done.html", cand=cand, exam=exam, settings=settings, total=total,
                           show_score=settings.get("exam.show_score") == "1",
                           max_score=total * float(settings.get("exam.marks_per_q", "4")))

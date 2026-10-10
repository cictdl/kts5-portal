"""
The check of the question bank (version 1.2.49).

From 15 October every institution's assessment draws its paper from the bank: exam.questions active
questions in the language the student chose, topped up from English when that language has too few
(candidate._build_paper). The check says, language by language, whether a full paper can be drawn,
and lists the active questions that should not be in a paper: a blank question or option, an answer
that is not A to D, two options alike, the same question twice. Those can be set aside (made
inactive) in one step; they stay in the bank and can be corrected and enabled again.

A question written wholly in another script (the general-knowledge questions that the generator
gives in English to the languages other than English, Tamil and Hindi, or a file imported under the
wrong code) is only pointed out: it can be drawn, but the student reads it in that script.
"""
import unicodedata

from . import kural as K
from .db import query

# Letters of each script: the script is that of most of the letters of a question.
SCRIPTS = {
    "Latin": [(0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F), (0x1E00, 0x1EFF)],
    "Devanagari": [(0x0900, 0x097F), (0xA8E0, 0xA8FF)],
    "Bengali": [(0x0980, 0x09FF)],
    "Gurmukhi": [(0x0A00, 0x0A7F)],
    "Gujarati": [(0x0A80, 0x0AFF)],
    "Odia": [(0x0B00, 0x0B7F)],
    "Tamil": [(0x0B80, 0x0BFF)],
    "Telugu": [(0x0C00, 0x0C7F)],
    "Kannada": [(0x0C80, 0x0CFF)],
    "Malayalam": [(0x0D00, 0x0D7F)],
    "Ol Chiki": [(0x1C50, 0x1C7F)],
    "Arabic": [(0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
}

# The script of the portal's translation in each language. The script of CICT's Thirukkural in that
# language, from which the generator takes the couplets, is allowed as well: Kashmiri and Santali
# in Devanagari, Konkani in Kannada.
INTERFACE_SCRIPT = {
    "en": "Latin", "as": "Bengali", "bn": "Bengali", "mni": "Bengali",
    "brx": "Devanagari", "doi": "Devanagari", "hi": "Devanagari", "kok": "Devanagari", "mai": "Devanagari",
    "mr": "Devanagari", "ne": "Devanagari", "sa": "Devanagari", "sd": "Devanagari",
    "gu": "Gujarati", "pa": "Gurmukhi", "or": "Odia", "ta": "Tamil", "te": "Telugu", "kn": "Kannada",
    "ml": "Malayalam", "sat": "Ol Chiki", "ur": "Arabic", "ks": "Arabic",
}

FIELDS = ("text", "opt_a", "opt_b", "opt_c", "opt_d")
LETTERS = ("A", "B", "C", "D")

# The kinds of problem: those that keep a question out of a paper, and the one that is only pointed out.
FAULTS = ("blank", "option", "answer", "same", "duplicate")
NOTES = ("script", "code")


def norm(value):
    """The words of a text, whatever the spaces and the case: for questions or options that are alike."""
    return " ".join((value or "").split()).casefold()


def allowed_scripts(lang):
    out = set()
    if lang in INTERFACE_SCRIPT:
        out.add(INTERFACE_SCRIPT[lang])
    info = K.lang_info(lang) or {}
    if info.get("script") in SCRIPTS:
        out.add(info["script"])
    return out


def scripts_in(text):
    """The number of letters of the text in each script."""
    counts = {}
    for ch in text or "":
        if not unicodedata.category(ch).startswith(("L", "M")):
            continue
        cp = ord(ch)
        for name, ranges in SCRIPTS.items():
            if any(a <= cp <= b for a, b in ranges):
                counts[name] = counts.get(name, 0) + 1
                break
    return counts


def script_of(text):
    """The script of most of the letters of the text, or None when it has no letters."""
    counts = scripts_in(text)
    return max(counts, key=counts.get) if counts else None


def faults_of(row):
    """The problems that keep this question out of a paper, as (kind, explanation)."""
    out = []
    if not norm(row["text"]):
        out.append(("blank", "The question is blank."))
    empty = [L for L, f in zip(LETTERS, FIELDS[1:]) if not norm(row[f])]
    if empty:
        out.append(("option", "Option " + ", ".join(empty) + (" is" if len(empty) == 1 else " are") + " blank."))
    if (row["correct"] or "").strip().upper() not in LETTERS:
        out.append(("answer", f"The correct answer “{row['correct'] or ''}” is not A, B, C or D."))
    seen = {}
    for L, f in zip(LETTERS, FIELDS[1:]):
        key = norm(row[f])
        if not key:
            continue
        if key in seen:
            out.append(("same", f"Options {seen[key]} and {L} are the same."))
        else:
            seen[key] = L
    return out


def _status(n, usable, en_usable, lang):
    """What a paper in this language holds: (status, explanation)."""
    if usable >= 2 * n:
        return "ready", f"Ready: {usable} questions for papers of {n}."
    if usable >= n:
        return "thin", (f"Enough for one paper of {n}, but papers will share most of their questions. "
                        f"At least {2 * n} are advised.")
    if lang == "en":
        if usable == 0:
            return "empty", "Empty: no paper can be drawn in English, and no language can be topped up."
        return "short", f"Short by {n - usable}: a paper in English would have only {usable} questions."
    topup = min(n - usable, en_usable)
    size = usable + topup
    if usable == 0:
        head = "Empty: "
        body = f"a paper would be wholly in English ({topup} questions)" if topup else "no paper can be drawn"
    else:
        head = f"Short by {n - usable}: "
        body = f"each paper gets {usable} in this language and {topup} in English" if topup else f"each paper gets only {usable}"
    tail = f"; only {size} of {n} questions in all." if size < n else "."
    return ("empty" if usable == 0 else "short"), head + body + tail


def report(n_questions):
    """
    The state of the bank: one row per language of the test (with the number of students who have
    signed up for an assessment in it) and the list of problems, faults first.
    """
    n = max(int(n_questions or 50), 1)
    langs = list(K.ORIENTATION_LANGS)
    signed = {r["lang"]: r["n"] for r in query("SELECT lang, COUNT(*) AS n FROM campus_students GROUP BY lang")}
    stats = {l: {"lang": l, "active": 0, "inactive": 0, "usable": 0, "faulty": 0, "other_script": 0,
                 "students": signed.get(l, 0)} for l in langs}
    first = {}
    problems = []
    rows = query("SELECT id, lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, active, source FROM questions ORDER BY id")
    for r in rows:
        st = stats.get(r["lang"])
        if not r["active"]:
            if st:
                st["inactive"] += 1
            continue
        if st is None:
            problems.append({"row": r, "kind": "code",
                             "why": f"“{r['lang']}” is not the code of a language of the test, so no student draws this question."})
            continue
        st["active"] += 1
        found = faults_of(r)
        key = (r["lang"], norm(r["text"]))
        if not found:
            if key in first:
                found.append(("duplicate", f"The same question as #{first[key]}."))
            else:
                first[key] = r["id"]
        if found:
            st["faulty"] += 1
            for kind, why in found:
                problems.append({"row": r, "kind": kind, "why": why})
            continue
        st["usable"] += 1
        # a stem in English around a couplet in the language is as the generator makes it; a question
        # without one letter of the language is pointed out
        counts = scripts_in(" ".join(r[f] or "" for f in FIELDS))
        allowed = allowed_scripts(r["lang"])
        if counts and allowed and not allowed & set(counts):
            st["other_script"] += 1
            problems.append({"row": r, "kind": "script",
                             "why": f"Written wholly in {max(counts, key=counts.get)} letters, none of them those of {K.lang_label(r['lang'])}."})
    en_usable = stats["en"]["usable"] if "en" in stats else 0
    for l in langs:
        st = stats[l]
        st["status"], st["say"] = _status(n, st["usable"], en_usable, l)
    order = {k: i for i, k in enumerate(FAULTS + NOTES)}
    problems.sort(key=lambda p: (order[p["kind"]], p["row"]["lang"], p["row"]["id"]))
    languages = [stats[l] for l in langs]
    count = {s: sum(1 for x in languages if x["status"] == s) for s in ("ready", "thin", "short", "empty")}
    faulty_ids = sorted({p["row"]["id"] for p in problems if p["kind"] in FAULTS})
    return {"n": n, "languages": languages, "problems": problems, "count": count, "faulty_ids": faulty_ids,
            "notes": sum(1 for p in problems if p["kind"] in NOTES), "ok": count["short"] + count["empty"] == 0 and not faulty_ids}


def summary(n_questions):
    """One line for the dashboard."""
    r = report(n_questions)
    parts = [f"{r['count']['ready'] + r['count']['thin']} of {len(r['languages'])} languages can fill a paper"]
    if r["count"]["short"] + r["count"]["empty"]:
        parts.append(f"{r['count']['short'] + r['count']['empty']} short")
    if r["faulty_ids"]:
        parts.append(f"{len(r['faulty_ids'])} faulty question(s)")
    return {"ok": r["ok"], "line": " · ".join(parts)}

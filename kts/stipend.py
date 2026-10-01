"""
Stipend: the bank details of the selected students.

A student of the final selected list gives the details of his or her own bank account
(/candidate/bank). The staff of CICT check every entry against the proof, approve it or return
it, and mark the payment (/console/stipend). The payment list is exported from there: every
download of the entries still to pay is a numbered payment list (table stipend_batches, with
the amount per student of that day), and 'paid' is marked for one such list, for the entries
that have not changed since it went out, at that amount. A list can be downloaded again without
making a new one, and a list that never went to the bank can be discarded.

The sign-in of a candidate is weak (application number, date of birth, four digits of the
mobile number: a classmate may know all three). The module is safe all the same:
  - an entry is locked once it is sent; only the staff can open it again;
  - nothing is paid without the approval of the staff against the proof, and an action of the
    staff from a page that shows an older state of the entry is refused;
  - every submission and every change of state is mailed to the registered address;
  - one account given for two applications is marked for the staff, and approved for one only;
  - the account and Aadhaar numbers are sealed in the database (kts/secure.py) and shown in full
    only on the page of one entry and in the export, to the roles with the permission
    "stipend", each time with a row in the audit log. Everywhere else, and in every mail, log
    line and message, stand the last four digits only.
"""
import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Response, abort, current_app, flash, g, redirect, render_template, request, url_for

from . import secure
from .admin import bp as console
from .auth import candidate_required, current_user, login_required
from .candidate import bp as candidates
from .db import DEFAULT_SETTINGS, all_settings, audit, audit_rows, execute, get_db, get_setting, query, utcnow
from .i18n import t
from .utils import (DOC_EXT, client_ip, csv_bytes, fmt_date, fmt_dt, limiter, now_ist, paginate, plain_english,
                    rupees, safe_int, save_upload, send_later, send_mail, valid_aadhaar, valid_account, valid_ifsc,
                    xlsx_bytes)

# the states of an entry, in the order in which it passes through them
STATES = ["submitted", "returned", "approved", "paid"]
ACCOUNT_TYPES = ["savings", "current"]
DECLARATIONS = ["declare_own", "declare_correct", "declare_consent"]
PROOF_MAX_BYTES = 2 * 1024 * 1024
# what one application sends from one address in an hour, right or wrong
SUBMISSIONS_PER_HOUR = 10
TEXT_MAX = 120
REMARK_MAX = 500
REFERENCE_MAX = 80
# the payment list: the entries that the staff have approved, and no others
EXPORTS = {"due": ("approved",), "paid": ("paid",), "all": ("approved", "paid")}
# the rows of the audit log that record a look at the full numbers, apart from the changes of state
LOOKS = ("bank_viewed", "bank_proof_opened")


# ---- what both sides need -----------------------------------------------------

def may_use(cand, settings, entry=None):
    """
    The form is for the students of the final selected list, once that list is published. A
    payment made before a student left that list stays on the page, as it stays in the record
    of the staff: the entry is shown, and nothing can be sent from it.
    """
    if entry is not None and entry["status"] == "paid":
        return True
    return cand["status"] == "selected" and settings.get("merit.published") == "1"


def amount(settings):
    """The stipend in whole rupees; the default when the setting holds no whole number above zero."""
    value = safe_int(str(settings.get("stipend.amount") or "").replace(",", "").strip())
    return value if value > 0 else safe_int(DEFAULT_SETTINGS["stipend.amount"])


def entry_of(application_id):
    return query("SELECT * FROM bank_details WHERE application_id = ?", (application_id,), one=True)


def _last_date(settings):
    """The last date of the form; None when none is set or it cannot be read."""
    try:
        return datetime.fromisoformat(settings.get("stipend.last_date") or "").date()
    except ValueError:
        return None


def page_state(settings, entry):
    """
    What the page of a selected student shows: the state of the entry ('submitted', 'returned',
    'approved', 'paid') or, without an entry, 'not_open', 'closed' or 'form'.
    """
    if entry is not None:
        return entry["status"]
    if settings.get("stipend.open") != "1":
        return "not_open"
    last = _last_date(settings)
    if last and now_ist().date() > last:
        return "closed"
    return "form"


def _may_send(settings, state):
    """
    The form is shown for a first entry and for an entry that the staff returned. A returned
    entry may be sent again after the last date as well. The switch stipend.open stops both.
    """
    return settings.get("stipend.open") == "1" and state in ("form", "returned")


def _remove(relpath):
    """Take a proof out of the upload folder: one of a request that is refused after all, or one that was replaced."""
    if relpath:
        try:
            (Path(current_app.config["UPLOAD_DIR"]) / relpath).unlink()
        except OSError:
            pass


def _ending(entry):
    return f"account ending in {entry['account_last4']}"


def _mail_text(a, lines):
    """A message to the registered address of the student. No number stands in it in full."""
    contact = get_setting("contact.email")
    return (f"Dear {a['full_name']},\n\n" + "\n\n".join(lines) + "\n\n"
            f"If you did not give these bank details yourself, or if anything in this message is not right, "
            f"write to CICT at once: {contact}\n\nCentral Institute of Classical Tamil, Chennai")


def _mail_paid(a, entry, paid, ref, on):
    return (a["email"], f"KTS 5.0: stipend paid for application {a['app_no']}",
            _mail_text(a, [f"The stipend of Rs. {paid} for your application {a['app_no']} has been paid by bank transfer "
                           f"to your {_ending(entry)}.", f"Date of payment: {fmt_date(on)}\nPayment reference: {ref}"]))


# ---- the student's side -------------------------------------------------------

def _line(value):
    """One line as it was typed: the marks of phone keyboards made plain, spaces in a row made one."""
    text, english = plain_english(value)
    return " ".join(text.split()), english


def _validate(form, settings):
    """(what is stored as it is, the two numbers that are sealed, the messages at the fields)"""
    data, errors = {}, {}
    for name in ("holder_name", "bank_name", "branch"):
        data[name], english = _line(form.get(name))
        if not data[name]:
            errors[name] = t("reg.err_required")
        elif not english:
            errors[name] = t("reg.err_english")
        elif len(data[name]) > TEXT_MAX:
            errors[name] = t("bank.err_long")
    # typed in any case, stored in capitals; letters of other scripts stay what they are
    typed = "".join((form.get("ifsc") or "").split())
    data["ifsc"] = typed.upper() if typed.isascii() else typed
    if not data["ifsc"]:
        errors["ifsc"] = t("reg.err_required")
    elif not valid_ifsc(data["ifsc"]):
        errors["ifsc"] = t("bank.err_ifsc")
    data["account_type"] = (form.get("account_type") or "").strip()
    if data["account_type"] not in ACCOUNT_TYPES:
        errors["account_type"] = t("reg.err_required")
    secret = {"account": (form.get("account") or "").strip(), "aadhaar": ""}
    if not secret["account"]:
        errors["account"] = t("reg.err_required")
    elif not valid_account(secret["account"]):
        errors["account"] = t("bank.err_account")
    elif (form.get("account_again") or "").strip() != secret["account"]:
        errors["account_again"] = t("bank.err_account_match")
    if settings.get("stipend.aadhaar") == "1":
        # spaces are allowed when typing: 1234 5678 9012
        secret["aadhaar"] = "".join((form.get("aadhaar") or "").split())
        if not secret["aadhaar"]:
            errors["aadhaar"] = t("reg.err_required")
        elif not valid_aadhaar(secret["aadhaar"]):
            errors["aadhaar"] = t("bank.err_aadhaar")
    for name in DECLARATIONS:
        if form.get(name) != "1":
            errors["declare"] = t("reg.err_declare")
    return data, secret, errors


def _seal(secret, replacing=None):
    """
    The numbers as the database keeps them. NoKey when there is no key, and also when the key in
    use opens none of the entries that were stored last: the key file is gone (a new key would be
    made in its place, and the file of the backup, put back later, would no longer open what was
    stored in between), or the file or the setting KTS_STIPEND_KEY holds another key than the
    entries were sealed with (entries of two keys could never be read together, and one account
    given twice would no longer be found). Once entries exist, the setting must hold the same key
    as instance/stipend.key, written as its 128 hex digits; under any other key no entry is taken.
    The entry stored last is tried and, when it fails, up to three stored before it: one damaged
    row must not close the form for everybody, and the staff can clear it by returning it. The
    entry that is being sent again (`replacing`) is no witness: what is sealed now takes its
    place. Another key opens none of them. When a single entry stands in the way, nothing tells
    a damaged row from another key, and the log names that entry instead of blaming the key.
    """
    tried = query("SELECT b.id, b.account_enc, a.app_no FROM bank_details b JOIN applications a ON a.id = b.application_id "
                  "WHERE b.id != ? ORDER BY b.id DESC LIMIT 4", (replacing["id"] if replacing is not None else 0,))
    opened = not tried
    for row in tried:
        try:
            # nothing is made here: unseal reads the key and makes none
            secure.unseal(row["account_enc"])
            opened = True
            break
        except secure.NoKey:
            break  # no key can be read: no row would open
        except ValueError:
            pass  # damaged, or sealed with another key: the next row tells which
    if not opened:
        if len(tried) == 1:
            current_app.logger.error("The bank details of application %s cannot be opened with the key of the stipend "
                                     "module (%s or %s), and no other entry can tell whether the key is another one or "
                                     "that entry is damaged. If the key is the one in use, return that entry to the "
                                     "student to be typed again; until then no bank details are accepted.",
                                     tried[0]["app_no"], secure.key_file(), secure.KEY_SETTING)
        else:
            current_app.logger.error("The key of the stipend module opens none of the bank details stored last "
                                     "(applications %s). Put back the key that was in use (%s or %s); until then no "
                                     "bank details are accepted.", ", ".join(r["app_no"] for r in tried),
                                     secure.key_file(), secure.KEY_SETTING)
        raise secure.NoKey("lost")
    return {"account_enc": secure.seal(secret["account"]),
            # zeros in front are no part of the number: 0012345 and 12345 are one account
            "account_hash": secure.lookup(secret["account"].lstrip("0")),
            "aadhaar_enc": secure.seal(secret["aadhaar"]) if secret["aadhaar"] else ""}


def _store(cand, entry, data, secret, sealed, proof, ip):
    """
    Write the entry: a new row, or the row that the staff returned. False when the entry was
    sent from another window in the meantime; that entry stands and nothing is written.
    """
    now = utcnow()
    values = [data["holder_name"], sealed["account_enc"], secret["account"][-4:], sealed["account_hash"], data["ifsc"],
              data["bank_name"], data["branch"], data["account_type"], sealed["aadhaar_enc"], secret["aadhaar"][-4:],
              proof[0], proof[1], proof[2], now, ip, now]
    conn = get_db()
    try:
        if entry is None:
            conn.execute("INSERT INTO bank_details(holder_name, account_enc, account_last4, account_hash, ifsc, bank_name, "
                         "branch, account_type, aadhaar_enc, aadhaar_last4, proof_path, proof_name, proof_size, "
                         "submitted_at, ip, updated_at, status, application_id, created_at) "
                         "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'submitted',?,?)", values + [cand["id"], now])
            stored = True
        else:
            cur = conn.execute("UPDATE bank_details SET holder_name=?, account_enc=?, account_last4=?, account_hash=?, ifsc=?, "
                               "bank_name=?, branch=?, account_type=?, aadhaar_enc=?, aadhaar_last4=?, proof_path=?, "
                               "proof_name=?, proof_size=?, submitted_at=?, ip=?, updated_at=?, status='submitted' "
                               "WHERE id = ? AND status = 'returned'", values + [entry["id"]])
            stored = cur.rowcount == 1
        conn.commit()
    except sqlite3.IntegrityError:
        # one row for each application: the other window was faster
        conn.rollback()
        stored = False
    return stored


@candidates.route("/bank", methods=["GET", "POST"])
@candidate_required
def bank():
    cand = g.candidate
    settings = all_settings()
    ask_aadhaar = settings.get("stipend.aadhaar") == "1"
    ctx = dict(cand=cand, settings=settings, data={}, errors={}, entry=None, masked={}, form=False,
               ask_aadhaar=ask_aadhaar, amount=rupees(amount(settings)), types=ACCOUNT_TYPES,
               last_date=_last_date(settings), proof_max=PROOF_MAX_BYTES)
    entry = entry_of(cand["id"])
    if not may_use(cand, settings, entry):
        # nothing of an entry is shown to a candidate who is not in the published list, apart from
        # a payment that was made before the student left it
        return render_template("candidate/bank.html", state="not_for_you", **ctx), 403 if request.method == "POST" else 200
    state = page_state(settings, entry)
    sending = _may_send(settings, state)
    if entry is not None:
        ctx.update(entry=entry, masked={"account": secure.mask_account(entry["account_last4"]),
                                        "aadhaar": secure.mask_aadhaar(entry["aadhaar_last4"])})
        if state == "returned":
            # what is no secret is filled in; the two numbers are typed again
            ctx["data"] = {name: entry[name] for name in ("holder_name", "ifsc", "bank_name", "branch", "account_type")}
    ctx.update(state=state, form=sending)

    if request.method == "POST":
        if not sending:
            # sent already, or the form is not open: nothing is changed
            if state in ("submitted", "approved", "paid"):
                flash(t("bank.locked"), "error")
            return redirect(url_for("candidate.bank"))
        ip = client_ip()
        data, secret, errors = _validate(request.form, settings)
        # the two numbers never go back into the page
        ctx.update(data=data, errors=errors)
        if not limiter.allow("bank", f"{cand['id']}|{ip}", SUBMISSIONS_PER_HOUR, 3600):
            # the limit is no mistake of the student: it is said at the top and no field is marked
            flash(t("reg.err_rate"), "error")
            ctx["errors"] = {}
            return render_template("candidate/bank.html", **ctx), 400
        upload = request.files.get("proof")
        replaced = upload is not None and bool(upload.filename)
        if not replaced and not (entry is not None and entry["proof_path"]):
            errors["proof"] = t("reg.err_idproof")
        proof = sealed = None
        if not errors:
            try:
                # before a file is stored: without a key nothing is kept
                sealed = _seal(secret, entry)
            except secure.NoKey:
                flash(t("bank.err_store"), "error")
                return render_template("candidate/bank.html", **ctx), 503
            if replaced:
                try:
                    proof = save_upload(upload, "bankproofs", DOC_EXT, PROOF_MAX_BYTES)
                except ValueError:
                    errors["proof"] = t("reg.err_idproof")
        if errors:
            flash(t("reg.err_fix"), "error")
            return render_template("candidate/bank.html", **ctx), 400

        kept = (entry["proof_path"], entry["proof_name"], entry["proof_size"]) if entry is not None else None
        try:
            stored = _store(cand, entry, data, secret, sealed, proof or kept, ip)
        except Exception:
            if proof:
                _remove(proof[0])
            raise
        if not stored:
            if proof:
                _remove(proof[0])
            flash(t("bank.locked"), "error")
            return redirect(url_for("candidate.bank"))
        if proof and kept and kept[0] != proof[0]:
            _remove(kept[0])
        last4 = secret["account"][-4:]
        audit("bank_submitted", "application", cand["id"],
              detail=f"{cand['app_no']}, account ending in {last4}" + (", sent again" if entry is not None else ""), ip=ip)
        send_mail(cand["email"], f"KTS 5.0: bank details submitted for application {cand['app_no']}",
                  _mail_text(cand, [f"Bank details for the stipend were submitted for your application {cand['app_no']} on "
                                    f"{fmt_dt(now_ist())} IST: account ending in {last4}, IFSC {data['ifsc']}, "
                                    f"{data['bank_name']}.",
                                    "CICT will check them against the proof that was uploaded. They cannot be changed "
                                    "in the portal after they are sent."]))
        return redirect(url_for("candidate.bank"))

    return render_template("candidate/bank.html", **ctx)


# ---- the console --------------------------------------------------------------

def _user():
    return current_user()


def _same_name(one, other):
    """True when two names are made of the same words, whatever their order, their case and their dots."""
    def words(value):
        return sorted(re.sub(r"[^A-Za-z]+", " ", value or "").upper().split())
    return words(one) == words(other)


def _numbers(entry):
    """(account number, Aadhaar number) in full; ValueError when they cannot be read with the key of this installation."""
    return secure.unseal(entry["account_enc"]), secure.unseal(entry["aadhaar_enc"]) if entry["aadhaar_enc"] else ""


def _holds_number(text, numbers):
    """
    True when a text written by the staff holds one of the numbers in full. Remark and payment
    reference go into a mail and onto the page of the student, where no full number may stand.
    A number counts also without its zeros in front (see _seal), when what is left is no
    shorter than an account number can be: bank files often drop those zeros. Groups of digits
    are read as one number whatever stands between them (spaces, hyphens, dots, slashes, commas,
    underscores or any other mark), as statements and passbooks print long numbers; letters
    keep two numbers apart, so that an IFSC and a branch code in one remark are not one number.
    """
    joined = re.sub(r"(?<=[0-9])[\W_]+(?=[0-9])", "", text)
    forms = {n for n in numbers if n} | {n.lstrip("0") for n in numbers if len(n.lstrip("0")) >= 9}
    return any(form in joined for form in forms)


def _version(entry):
    """
    What the page of one entry was made from. Every sending seals the numbers anew, with a new
    random nonce, and every step of the staff sets updated_at: an action from a page that shows
    an older entry is refused. A digest of a seal says nothing about the number.
    """
    return hashlib.sha256(f"{entry['account_enc']}|{entry['updated_at']}".encode()).hexdigest()[:20]


# no other entry with the same account is approved or paid: one stipend for one account
ALONE = ("NOT EXISTS (SELECT 1 FROM bank_details o WHERE o.account_hash = bank_details.account_hash "
         "AND o.id != bank_details.id AND o.status IN ('approved', 'paid'))")


def _move(entry, before, changes, args, unless=""):
    """
    Change an entry that is still in one of the states `before`, with the numbers it had when
    it was read (and, with `unless`, meets that condition as well). False when somebody else
    changed it in the meantime: nothing is written then.
    """
    conn = get_db()
    cur = conn.execute(f"UPDATE bank_details SET {changes}, updated_at = ? WHERE id = ? AND account_enc = ? AND status IN "
                       f"({','.join('?' * len(before))})" + (f" AND {unless}" if unless else ""),
                       list(args) + [utcnow(), entry["id"], entry["account_enc"]] + list(before))
    conn.commit()
    return cur.rowcount == 1


def _listed_in(entry):
    """
    The number of the payment list, not yet marked as paid or discarded, in which this entry went
    to the bank with the account it has now; None otherwise. Marked paid one by one, or undone
    after that, the entry still stands in that list (the file at the bank holds this account);
    returned and sent again since the list went out, it does not: the staff answered for that
    list when they returned it. The payment of a list is stricter and takes the exact version.
    """
    if entry["status"] not in ("approved", "paid"):
        return None
    for b in query("SELECT id, entries, created_at FROM stipend_batches WHERE settled_at IS NULL ORDER BY id DESC"):
        if entry["submitted_at"] <= b["created_at"] and entry["id"] in {pair[0] for pair in json.loads(b["entries"])}:
            return b["id"]
    return None


def _not_paid_from(listed, step):
    """
    An entry of a payment list that went to the bank may have been paid from it: `step`
    (returned, or the payment undone) is done only with the ticked confirmation that the bank has
    not paid it from that list. The message that refuses the step without it, or None.
    """
    if listed and request.form.get("not_paid") != "1":
        return (f"This entry is in payment list no. {listed}, which is not yet marked as paid. {step} only when the "
                f"bank has not paid it from that list, and tick the box that says so. Nothing was done.")
    return None


def _payment_error(ref, on):
    """What is wrong with the reference and the date of a payment, or None."""
    if not ref or not on:
        return "A payment needs its reference and its date."
    if len(ref) > REFERENCE_MAX:
        return f"The payment reference is longer than {REFERENCE_MAX} characters."
    try:
        day = datetime.strptime(on, "%Y-%m-%d").date()
    except ValueError:
        return "The date of the payment cannot be read."
    if day > now_ist().date():
        return "The date of the payment lies in the future."
    return None


@console.route("/stipend")
@login_required("stipend")
def stipend():
    settings = all_settings()
    f = {k: (request.args.get(k) or "").strip() for k in ("state", "q")}
    sql = " FROM applications a LEFT JOIN bank_details b ON b.application_id = a.id"
    args = []
    if f["state"] == "off":
        # entries of students who are not, or no longer, in the selected list
        sql += " WHERE a.status != 'selected' AND b.id IS NOT NULL"
    else:
        sql += " WHERE a.status = 'selected'"
    if f["state"] == "none":
        sql += " AND b.id IS NULL"
    elif f["state"] in STATES:
        sql += " AND b.status = ?"
        args.append(f["state"])
    elif f["state"] == "same":
        sql += " AND b.account_hash IN (SELECT account_hash FROM bank_details GROUP BY account_hash HAVING COUNT(*) > 1)"
    if f["q"]:
        sql += " AND (a.full_name LIKE ? OR a.app_no LIKE ? OR a.college_name LIKE ?)"
        args += [f"%{f['q']}%"] * 3
    total = query("SELECT COUNT(*) AS n" + sql, args, one=True)["n"]
    pg = paginate(total, safe_int(request.args.get("page"), 1), 100)
    rows = query("SELECT a.id, a.app_no, a.full_name, a.college_name, a.college_state, a.state, a.exam_rank, "
                 "b.status AS bank_status, b.account_last4, b.account_hash, b.ifsc" + sql +
                 " ORDER BY a.exam_rank IS NULL, a.exam_rank, a.id LIMIT ? OFFSET ?", args + [pg["per_page"], pg["offset"]])
    counts = {r["s"]: r["n"] for r in query(
        "SELECT COALESCE(b.status, 'none') AS s, COUNT(*) AS n FROM applications a "
        "LEFT JOIN bank_details b ON b.application_id = a.id WHERE a.status = 'selected' GROUP BY s")}
    # entries of students who have left the selected list; a payment made before stays paid
    off = query("SELECT COUNT(*) AS n, COALESCE(SUM(b.status = 'paid'), 0) AS paid FROM bank_details b "
                "JOIN applications a ON a.id = b.application_id WHERE a.status != 'selected'", one=True)
    # one account given for more than one application
    same = {r["account_hash"] for r in query("SELECT account_hash FROM bank_details GROUP BY account_hash HAVING COUNT(*) > 1")}
    # every payment list that went out and is not yet marked as paid or discarded, newest first: the
    # one at the bank may be older than many downloads made since, and none is left off the page
    batches = [dict(b, each=rupees(b["amount"] or amount(settings))) for b in query(
        "SELECT b.id, b.rows, b.amount, b.created_at, u.name AS made_by FROM stipend_batches b "
        "LEFT JOIN users u ON u.id = b.created_by WHERE b.settled_at IS NULL ORDER BY b.id DESC")]
    return render_template("console/stipend.html", rows=rows, f=f, pg=pg, counts=counts, selected=sum(counts.values()),
                           off_list=off["n"], off_paid=off["paid"], same=same, batches=batches, states=STATES,
                           settings=settings, mask=secure.mask_account, amount=rupees(amount(settings)),
                           due=rupees(amount(settings) * counts.get("approved", 0)),
                           today=now_ist().strftime("%Y-%m-%d"), last_date=_last_date(settings))


@console.route("/stipend/<int:aid>", methods=["GET", "POST"])
@login_required("stipend")
def stipend_entry(aid):
    a = query("SELECT * FROM applications WHERE id = ?", (aid,), one=True)
    if a is None:
        abort(404)
    entry = entry_of(aid)
    user = _user()
    if request.method == "POST":
        if entry is None:
            abort(404)
        if request.form.get("seen") != _version(entry):
            # the page was made from an entry that has changed since: what it showed is not what stands now
            flash("The entry was changed in the meantime. Nothing was done: check it again.", "error")
            return redirect(url_for("admin.stipend_entry", aid=aid))
        _act(a, entry, user)
        return redirect(url_for("admin.stipend_entry", aid=aid))
    account = aadhaar = ""
    readable = True
    others, listed = [], None
    if entry is not None:
        try:
            account, aadhaar = _numbers(entry)
        except ValueError:
            readable = False
        # the numbers stand on this page in full: who opened it is written down, without them
        audit("bank_viewed", "application", aid, detail=f"{a['app_no']}, {_ending(entry)}", user=user, ip=client_ip())
        others = query("SELECT a.id, a.app_no, a.full_name, a.college_name, a.status AS app_status, b.holder_name, b.ifsc, "
                       "b.status FROM bank_details b JOIN applications a ON a.id = b.application_id "
                       "WHERE b.account_hash = ? AND b.application_id != ? ORDER BY a.id", (entry["account_hash"], aid))
        listed = _listed_in(entry)
    # the changes of state apart from the looks at the entry, which would push them off the page
    marks = ",".join("?" * len(LOOKS))
    history = query("SELECT * FROM audit_log WHERE entity = 'application' AND entity_id = ? AND action LIKE 'bank_%' "
                    f"AND action NOT IN ({marks}) ORDER BY id DESC LIMIT 50", (aid, *LOOKS))
    looks = query(f"SELECT * FROM audit_log WHERE entity = 'application' AND entity_id = ? AND action IN ({marks}) "
                  "ORDER BY id DESC LIMIT 10", (aid, *LOOKS))
    looked = query(f"SELECT COUNT(*) AS n FROM audit_log WHERE entity = 'application' AND entity_id = ? AND action IN ({marks})",
                   (aid, *LOOKS), one=True)["n"]
    staff = {r["id"]: r["name"] for r in query("SELECT id, name FROM users")}
    # a paid entry shows the sum that was paid, not the setting of today
    shown = entry["paid_amount"] if entry is not None and entry["paid_amount"] else amount(all_settings())
    return render_template("console/stipend_entry.html", a=a, b=entry, account=account, aadhaar=aadhaar, readable=readable,
                           others=others, listed=listed, history=history, looks=looks, looked=looked, staff=staff,
                           amount=rupees(shown), same_name=entry is not None and _same_name(a["full_name"], entry["holder_name"]),
                           seen=_version(entry) if entry is not None else "", today=now_ist().strftime("%Y-%m-%d"))


def _act(a, entry, user):
    """One action of the staff on one entry: the change, its row in the audit log, the mail to the student."""
    action = request.form.get("action")
    what = f"{a['app_no']}, {_ending(entry)}"
    now, ip = utcnow(), client_ip()
    try:
        numbers = _numbers(entry)
    except ValueError:
        numbers = None
    if action in ("approve", "paid") and a["status"] != "selected":
        flash("This student is not in the selected list: nothing is approved or paid.", "error")
    elif action in ("approve", "paid") and numbers is None:
        flash("The numbers of this entry cannot be read with the key of this installation: it cannot be approved or paid.", "error")
    elif action == "approve":
        if not _move(entry, ["submitted"], "status = 'approved', reviewed_by = ?, reviewed_at = ?", (user["id"], now),
                     unless=ALONE):
            if query(f"SELECT 1 FROM bank_details WHERE id = ? AND NOT {ALONE}", (entry["id"],), one=True):
                return flash("The same account is approved or paid for another application: one of the two can be "
                             "approved, not both. Return the other entry first if it is the wrong one.", "error")
            return flash("The entry was changed in the meantime. Nothing was done.", "error")
        audit("bank_approved", "application", a["id"], detail=what, user=user, ip=ip)
        send_mail(a["email"], f"KTS 5.0: bank details approved for application {a['app_no']}",
                  _mail_text(a, [f"The bank details for your application {a['app_no']} ({_ending(entry)}) have been checked "
                                 f"and approved. The stipend will be paid to this account."]))
        flash(f"Bank details of {a['app_no']} approved.", "success")
    elif action == "return":
        remark = " ".join((request.form.get("remark") or "").split())
        if not remark:
            return flash("A remark is required: it tells the student what to correct.", "error")
        if len(remark) > REMARK_MAX:
            return flash(f"The remark is longer than {REMARK_MAX} characters.", "error")
        if _holds_number(remark, numbers or ()):
            return flash("Do not write the account or Aadhaar number into the remark: it is mailed to the student.", "error")
        # sent again and approved again, an entry that the bank paid from its list would be paid twice
        listed = _listed_in(entry)
        refused = _not_paid_from(listed, "Return it")
        if refused:
            return flash(refused, "error")
        if not _move(entry, ["submitted", "approved"], "status = 'returned', remark = ?, reviewed_by = ?, reviewed_at = ?",
                     (remark, user["id"], now)):
            return flash("The entry was changed in the meantime. Nothing was done.", "error")
        audit("bank_returned", "application", a["id"], user=user, ip=ip,
              detail=what + (f", the bank has not paid it from payment list no. {listed}" if listed else ""))
        send_mail(a["email"], f"KTS 5.0: bank details returned for application {a['app_no']}",
                  _mail_text(a, [f"CICT has returned the bank details for your application {a['app_no']} ({_ending(entry)}) "
                                 f"for correction.", f"Note from CICT: {remark}",
                                 f"Sign in at {current_app.config['BASE_URL']}/candidate/login, correct the details and "
                                 f"send them again."]))
        flash(f"Bank details of {a['app_no']} returned to the student.", "warning")
    elif action == "paid":
        ref = " ".join((request.form.get("paid_ref") or "").split())
        on = (request.form.get("paid_on") or "").strip()
        error = _payment_error(ref, on)
        if error:
            return flash(error, "error")
        if _holds_number(ref, numbers):
            return flash("Do not write the account or Aadhaar number into the payment reference: it is mailed to the student.", "error")
        # the sum as it is paid. An entry that stands in a payment list at the bank was paid what
        # the file of that list says; any other takes the setting, which may change afterwards
        listed = _listed_in(entry)
        batch = query("SELECT amount FROM stipend_batches WHERE id = ?", (listed,), one=True) if listed else None
        paid = (batch["amount"] if batch else None) or amount(all_settings())
        if not _move(entry, ["approved"], "status = 'paid', paid_ref = ?, paid_on = ?, paid_by = ?, paid_amount = ?",
                     (ref, on, user["id"], paid)):
            return flash("Only an approved entry can be marked as paid. Nothing was done.", "error")
        audit("bank_paid", "application", a["id"], detail=f"{what}, reference {ref}, {on}", user=user, ip=ip)
        send_mail(*_mail_paid(a, entry, rupees(paid), ref, on))
        flash(f"Stipend of {a['app_no']} marked as paid.", "success")
    elif action == "unpaid":
        if user["role"] != "superadmin":
            abort(403)
        # approved again, an entry that the bank paid from its list would go into the next list as well
        listed = _listed_in(entry)
        refused = _not_paid_from(listed, "Take the mark back")
        if refused:
            return flash(refused, "error")
        if not _move(entry, ["paid"], "status = 'approved', paid_ref = '', paid_on = '', paid_by = NULL, paid_amount = NULL", ()):
            return flash("The entry is not marked as paid. Nothing was done.", "error")
        audit("bank_unpaid", "application", a["id"], user=user, ip=ip,
              detail=f"{what}, was reference {entry['paid_ref']}, {entry['paid_on']}"
                     + (f", the bank has not paid it from payment list no. {listed}" if listed else ""))
        send_mail(a["email"], f"KTS 5.0: payment entry withdrawn for application {a['app_no']}",
                  _mail_text(a, [f"The entry that the stipend for your application {a['app_no']} ({_ending(entry)}) was paid "
                                 f"has been withdrawn by CICT. The bank details stand as approved. You will get a "
                                 f"message when the payment is entered."]))
        flash(f"The mark 'paid' of {a['app_no']} was taken back; the entry is approved again.", "warning")
    else:
        abort(400)
    return None


@console.route("/stipend/paid", methods=["POST"])
@login_required("stipend")
def stipend_paid_all():
    """
    Mark the entries of one payment list as paid, with one reference and one date: those that
    are still approved and unchanged since the list was exported, and no others. The list is
    then settled and cannot be paid again.
    """
    user = _user()
    ref = " ".join((request.form.get("paid_ref") or "").split())
    on = (request.form.get("paid_on") or "").strip()
    error = _payment_error(ref, on)
    if error:
        flash(error, "error")
        return redirect(url_for("admin.stipend"))
    batch = query("SELECT * FROM stipend_batches WHERE id = ? AND settled_at IS NULL",
                  (safe_int(request.form.get("batch")),), one=True)
    if batch is None:
        flash("Choose the payment list that the bank has carried out. Nothing was done.", "error")
        return redirect(url_for("admin.stipend"))
    listed = {entry_id: version for entry_id, version in json.loads(batch["entries"])}
    ip = client_ip()
    # the sum per student as it stood in the file the bank carried out, whatever the setting says
    # today; a list made before the sum was kept with it takes the setting
    per_student = batch["amount"] or amount(all_settings())
    conn = get_db()
    if conn.in_transaction:
        conn.commit()
    # nobody changes an entry, and nobody else settles the list, between the reading and the writing
    conn.execute("BEGIN IMMEDIATE")
    try:
        now = utcnow()
        # the list is settled first, and once: a second 'paid' for it, sent at the same moment by
        # somebody else, finds it settled and touches no entry
        if conn.execute("UPDATE stipend_batches SET paid_ref = ?, paid_on = ?, settled_at = ? WHERE id = ? AND settled_at IS NULL",
                        (ref, on, now, batch["id"])).rowcount != 1:
            conn.rollback()
            flash(_settled_meanwhile(batch["id"]), "error")
            return redirect(url_for("admin.stipend"))
        rows = conn.execute("SELECT b.*, a.app_no, a.full_name, a.email FROM bank_details b "
                            "JOIN applications a ON a.id = b.application_id "
                            "WHERE b.status = 'approved' AND a.status = 'selected' ORDER BY a.id").fetchall()
        # the reference goes into the mail and onto the page of every student paid: no number of
        # an entry of this list may stand in it, also not of one that is left out below
        marks = ",".join("?" * len(listed))
        for r in conn.execute(f"SELECT account_enc, aadhaar_enc FROM bank_details WHERE id IN ({marks})", list(listed)).fetchall():
            try:
                numbers = _numbers(r)
            except ValueError:
                continue
            if _holds_number(ref, numbers):
                conn.rollback()
                flash("Do not write an account or Aadhaar number into the payment reference: it is mailed to the students.", "error")
                return redirect(url_for("admin.stipend"))
        paid, unread = [], 0
        for r in rows:
            if listed.get(r["id"]) != r["updated_at"]:
                # not in this list, or changed since it went out (returned, sent again, approved again)
                continue
            try:
                _numbers(r)
            except ValueError:
                # an entry that cannot be read was not checked against this key: it is left out
                unread += 1
                continue
            paid.append(r)
        conn.executemany("UPDATE bank_details SET status = 'paid', paid_ref = ?, paid_on = ?, paid_by = ?, paid_amount = ?, "
                         "updated_at = ? WHERE id = ? AND status = 'approved' AND updated_at = ?",
                         [(ref, on, user["id"], per_student, now, r["id"], r["updated_at"]) for r in paid])
        audit_rows("bank_paid", "application",
                   [(r["application_id"], f"{r['app_no']}, {_ending(r)}, reference {ref}, {on}, payment list {batch['id']}")
                    for r in paid], user=user, ip=ip)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if paid:
        send_later([_mail_paid(r, r, rupees(per_student), ref, on) for r in paid])
    left = len(listed) - len(paid) - unread
    flash(f"{len(paid)} entries of payment list no. {batch['id']} marked as paid with the reference {ref}."
          + (f" {unread} entries cannot be read with the key of this installation and were left out." if unread else "")
          + (f" {left} entries of the list were changed since it went out (returned, paid one by one or no longer "
             f"selected) and were left out: check them one by one." if left else ""),
          "success" if paid and not left else "warning")
    return redirect(url_for("admin.stipend"))


def _settled_meanwhile(bid):
    """What the second of two staff who settle one list at the same moment is told."""
    gone = query("SELECT paid_ref FROM stipend_batches WHERE id = ?", (bid,), one=True)
    done = "discarded" if gone is not None and gone["paid_ref"] == "discarded" else "marked as paid"
    return f"Payment list {bid} was {done} a moment ago by somebody else. Nothing was done."


@console.route("/stipend/discard", methods=["POST"])
@login_required("stipend")
def stipend_discard():
    """
    Discard a payment list that never went to the bank (a look at the due list, a download made
    twice): the list is settled with the reference 'discarded' and nothing is marked as paid; its
    entries stay approved, no longer name that list and go into the next one.
    """
    user = _user()
    bid = safe_int(request.form.get("batch"))
    batch = query("SELECT * FROM stipend_batches WHERE id = ? AND settled_at IS NULL", (bid,), one=True)
    if batch is None:
        flash("Choose the payment list to discard. Nothing was done.", "error")
        return redirect(url_for("admin.stipend"))
    conn = get_db()
    # settled once, whoever is faster
    if conn.execute("UPDATE stipend_batches SET paid_ref = 'discarded', settled_at = ? WHERE id = ? AND settled_at IS NULL",
                    (utcnow(), bid)).rowcount != 1:
        conn.rollback()
        flash(_settled_meanwhile(bid), "error")
        return redirect(url_for("admin.stipend"))
    # audit() commits the row together with the change
    audit("bank_list_discarded", "bank_details", None, user=user, ip=client_ip(),
          detail=f"payment list {bid} discarded: {batch['rows']} entries, made on {batch['created_at']}, nothing marked as paid")
    flash(f"Payment list no. {bid} ({batch['rows']} entries) was discarded: nothing was marked as paid, and its entries "
          f"stay approved for the next list.", "warning")
    return redirect(url_for("admin.stipend"))


def _inert(value):
    """
    A cell of the CSV file that a spreadsheet must not take for a formula: what a student typed
    may begin with = + - or @. An apostrophe in front makes it text.
    """
    value = "" if value is None else str(value)
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def _as_text(number):
    """
    A number in the CSV file, written ="0012345": Excel shows it as text, with its zeros in
    front and all its digits. Opened as a plain number, Excel would drop the zeros and turn the
    digits after the fifteenth into zeros.
    """
    return f'="{number}"' if number else ""


def _file(fmt, name, headers, data, sheet, text_cols):
    """The export as the browser saves it."""
    if fmt == "xlsx":
        return Response(xlsx_bytes(headers, data, sheet, text_cols=text_cols),
                        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename={name}"})
    return Response(csv_bytes(headers, data), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}"})


def _stamp():
    return now_ist().strftime("%Y%m%d-%H%M")


def _export_none(fmt, user, head):
    """
    The selected students who have sent no bank details yet, with their e-mail and mobile: the
    list for a reminder. No column of a bank, no number of an account.
    """
    rows = query("SELECT a.app_no, a.full_name, a.college_name, a.college_state, a.state, a.email, a.mobile "
                 "FROM applications a LEFT JOIN bank_details b ON b.application_id = a.id "
                 "WHERE a.status = 'selected' AND b.id IS NULL ORDER BY a.exam_rank IS NULL, a.exam_rank, a.id")
    headers = ["S. No.", "Application No", "Student's name", "College", "State", "E-mail", "Mobile"]
    data = [[n, r["app_no"], r["full_name"], r["college_name"], r["college_state"] or r["state"], r["email"], r["mobile"]]
            for n, r in enumerate(rows, start=1)]
    if not head:
        audit("bank_exported", "bank_details", None, user=user, ip=client_ip(),
              detail={"rows": len(data), "which": "none", "fmt": fmt, "aadhaar": False})
    name = f"KTS5-stipend-none-{_stamp()}.{fmt}"
    if fmt == "csv":
        data = [[row[0]] + [_inert(v) for v in row[1:]] for row in data]
    return _file(fmt, name, headers, data, "Not yet submitted", range(1, len(headers)))


# the columns of a payment list, in the order of the file; the Aadhaar number, or the mark
# 'changed since the list' of a list downloaded again, comes after them
HEADERS = ["S. No.", "Application No", "Student's name", "Account holder", "Account number", "IFSC", "Bank", "Branch",
           "Account type", "Amount (Rs.)", "College", "State", "E-mail", "Mobile", "Status", "Payment reference",
           "Payment date", "Approved by", "Approved on"]
ACCOUNT_COL, AMOUNT_COL = 4, 9
ENTRY_COLUMNS = ("SELECT b.*, a.app_no, a.full_name, a.college_name, a.college_state, a.state, a.email, a.mobile, "
                 "a.status AS app_status, u.name AS approved_by FROM bank_details b "
                 "JOIN applications a ON a.id = b.application_id LEFT JOIN users u ON u.id = b.reviewed_by ")


def _cells(n, r, account, paid):
    """One row of a payment list: the entry as it stands, at the sum `paid`."""
    return [n, r["app_no"], r["full_name"], r["holder_name"], account, r["ifsc"], r["bank_name"], r["branch"],
            r["account_type"], paid, r["college_name"], r["college_state"] or r["state"], r["email"], r["mobile"],
            r["status"], r["paid_ref"], r["paid_on"], r["approved_by"] or "", fmt_dt(r["reviewed_at"], numeric=True)]


def _amount_of(r, per_student):
    """A paid entry shows the sum that was paid, the others `per_student`."""
    return r["paid_amount"] if r["status"] == "paid" and r["paid_amount"] else per_student


def _name_left_out(left_out):
    """The entries whose numbers cannot be read are named, never with a number that may be wrong or missing."""
    if left_out:
        flash(f"{len(left_out)} entries cannot be read with the key of this installation and were left out of the export: "
              f"{', '.join(left_out[:10])}{' and others' if len(left_out) > 10 else ''}. Put back the key that was in use "
              f"when they were made; an entry that is not paid yet can also be returned to the student to be typed again.",
              "error")


def _sheet(fmt, name, headers, data, numbers):
    """
    The file of a payment list: every column but the serial number and the amount is text. In the
    CSV file the numbers of the columns `numbers` are written ="…" and what a student typed is
    never a formula.
    """
    if fmt == "csv":
        for row in data:
            row[1:] = [_inert(v) if c != AMOUNT_COL else v for c, v in enumerate(row[1:], start=1)]
            for c in numbers:
                row[c] = _as_text(row[c])
    return _file(fmt, name, headers, data, "Stipend", [c for c in range(len(headers)) if c not in (0, AMOUNT_COL)])


@console.route("/stipend/export.<fmt>")
@login_required("stipend")
def stipend_export(fmt):
    which = request.args.get("which") or "due"
    if fmt not in ("xlsx", "csv") or which not in list(EXPORTS) + ["none"]:
        abort(404)
    user = _user()
    # Flask answers a HEAD with this view and sends the headers without the file: a download
    # manager or a link checker asking for them takes no number out, makes no payment list and is
    # not written down
    head = request.method == "HEAD"
    if which == "none":
        return _export_none(fmt, user, head)
    with_aadhaar = request.args.get("aadhaar") == "1"
    # what is still to pay is for the students of the selected list only; what was paid stays in
    # the record also when the student has left the selected list since
    rows = query(ENTRY_COLUMNS + f"WHERE b.status IN ({','.join('?' * len(EXPORTS[which]))}) "
                 "AND (a.status = 'selected' OR b.status = 'paid') ORDER BY a.exam_rank IS NULL, a.exam_rank, a.id",
                 EXPORTS[which])
    per_student = amount(all_settings())
    headers = HEADERS + (["Aadhaar number"] if with_aadhaar else [])
    data, listed, left_out = [], [], []
    for r in rows:
        try:
            account, aadhaar = _numbers(r)
        except ValueError:
            # the entry is left out and named, as by the payment of a list
            left_out.append(r["app_no"])
            continue
        data.append(_cells(len(data) + 1, r, account, _amount_of(r, per_student)) + ([aadhaar] if with_aadhaar else []))
        if r["status"] == "approved":
            listed.append([r["id"], r["updated_at"]])
    batch = None
    if which == "due" and listed and not head:
        # the payment list as it goes out: 'paid' is marked later for these entries, in this version,
        # at this sum, and no others
        batch = execute("INSERT INTO stipend_batches(entries, rows, amount, created_by, created_at) VALUES(?,?,?,?,?)",
                        (json.dumps(listed), len(listed), per_student, user["id"], utcnow()))
    # what was taken out and its sum, never the numbers themselves
    detail = {"rows": len(data), "amount": sum(row[AMOUNT_COL] for row in data), "which": which, "fmt": fmt,
              "aadhaar": with_aadhaar}
    if batch:
        detail["list"] = batch
    if left_out:
        detail["left_out"] = len(left_out)
    if not head:
        _name_left_out(left_out)
        audit("bank_exported", "bank_details", None, user=user, ip=client_ip(), detail=detail)
    name = f"KTS5-stipend-{which}{f'-list{batch}' if batch else ''}-{_stamp()}.{fmt}"
    return _sheet(fmt, name, headers, data, [ACCOUNT_COL] + ([len(headers) - 1] if with_aadhaar else []))


@console.route("/stipend/list/<int:bid>.<fmt>")
@login_required("stipend")
def stipend_list(bid, fmt):
    """
    A payment list downloaded again, without making a new one: the same entries, in the order of
    the list and as they stand now, at the sum the list went out with, and a last column that
    marks the entries changed since (returned, sent again, approved again, paid one by one) or no
    longer selected: 'paid' for the list would leave those out. No Aadhaar column.
    """
    if fmt not in ("xlsx", "csv"):
        abort(404)
    batch = query("SELECT * FROM stipend_batches WHERE id = ?", (bid,), one=True)
    if batch is None:
        abort(404)
    user = _user()
    head = request.method == "HEAD"
    pairs = json.loads(batch["entries"])
    found = {r["id"]: r for r in query(ENTRY_COLUMNS + f"WHERE b.id IN ({','.join('?' * len(pairs))})",
                                       [entry_id for entry_id, _version in pairs])}
    per_student = batch["amount"] or amount(all_settings())
    headers = HEADERS + ["Changed since the list"]
    data, left_out, changed = [], [], 0
    for entry_id, version in pairs:
        r = found.get(entry_id)
        if r is None:
            continue
        try:
            account, _aadhaar = _numbers(r)
        except ValueError:
            left_out.append(r["app_no"])
            continue
        mark = "yes" if r["updated_at"] != version else "" if r["app_status"] == "selected" else "no longer selected"
        changed += bool(mark)
        data.append(_cells(len(data) + 1, r, account, _amount_of(r, per_student)) + [mark])
    detail = {"rows": len(data), "amount": sum(row[AMOUNT_COL] for row in data), "which": "list", "fmt": fmt, "list": bid,
              "changed": changed}
    if left_out:
        detail["left_out"] = len(left_out)
    if not head:
        _name_left_out(left_out)
        audit("bank_exported", "bank_details", None, user=user, ip=client_ip(), detail=detail)
    return _sheet(fmt, f"KTS5-stipend-due-list{bid}-{_stamp()}.{fmt}", headers, data, [ACCOUNT_COL])

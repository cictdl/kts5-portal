"""
Stipend: the bank details of the selected students (version 1.2.0).

    python -m pytest tests/test_stipend.py -q

The student sends the details of his or her own account (/candidate/bank); the staff check them
against the proof, approve, return or mark the payment, and export the payment list
(/console/stipend). The sign-in of a candidate is weak, so the tests look at the safeguards as
much as at the form: nothing secret in plain text, nothing changed once sent, nothing paid
without approval, full numbers for superadmin and admin only.

Every number here is invented. The Aadhaar-shaped numbers are made by the tests with the check
digit of the portal; the account numbers and branch codes belong to no bank.
"""
import csv
import io
import json
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import timedelta
from pathlib import Path

import pytest

from conftest import add_candidates, make_app
from test_public_fixes import FIRST, PDF, PNG, _answer, _staff

ACCOUNT = "000123450987"          # 12 digits, two zeros in front
OTHER_ACCOUNT = "987650001234567"  # 15 digits
THIRD_ACCOUNT = "112233445566"     # 12 digits
IFSC = "TEST0AB1234"
MAIN = "http://localhost"


@pytest.fixture(autouse=True)
def empty_limiter():
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def _aadhaar(body="23456789012"):
    """An Aadhaar-shaped number of the tests: eleven digits and the check digit of the portal."""
    from kts.utils import verhoeff_digit
    return body + verhoeff_digit(body)


def _wrong(number):
    """The same number with another last digit: its check digit is wrong."""
    return number[:-1] + str((int(number[-1]) + 1) % 10)


AADHAAR = _aadhaar()
SPACED = f"{AADHAAR[:4]} {AADHAAR[4:8]} {AADHAAR[8:]}"


def _site(n=2, published="1", form_open="1", aadhaar="1", last_date="", selected=None, **config):
    """An application of its own with n students; the first `selected` of them (all by default) are selected."""
    from kts.db import execute, query, set_setting
    app = make_app(ADMIN_EMAIL=FIRST, **config)
    students = add_candidates(app, n)
    with app.app_context():
        for rank, s in enumerate(students, start=1):
            s["id"] = query("SELECT id FROM applications WHERE app_no = ?", (s["app_no"],), one=True)["id"]
            s["name"] = f"Campus Student {rank}"
            s["email"] = f"campus{rank}@tests.example"
            status = "selected" if selected is None or rank <= selected else "not_selected"
            execute("UPDATE applications SET status = ?, exam_rank = ? WHERE id = ?", (status, rank, s["id"]))
        set_setting("merit.published", published)
        set_setting("stipend.open", form_open)
        set_setting("stipend.aadhaar", aadhaar)
        set_setting("stipend.last_date", last_date)
    return app, students


def _setting(app, key, value):
    from kts.db import set_setting
    with app.app_context():
        set_setting(key, value)


def _student(app, who):
    client = app.test_client()
    client.get("/candidate/login")
    r = client.post("/candidate/login", data={"_csrf": _token(client), "app_no": who["app_no"], "dob": who["dob"],
                                              "last4": who["last4"]})
    assert r.status_code == 302 and r.headers["Location"].endswith("/candidate/")
    return client


def _token(client):
    with client.session_transaction() as s:
        return s["_csrf"]


def _form(client, proof=("cheque.pdf", PDF), **changed):
    form = {"_csrf": _token(client), "holder_name": "Campus Student 1", "account": ACCOUNT, "account_again": ACCOUNT,
            "ifsc": IFSC.lower(), "bank_name": "Test Bank of the Tests", "branch": "College Road", "account_type": "savings",
            "aadhaar": SPACED, "declare_own": "1", "declare_correct": "1", "declare_consent": "1"}
    if proof is not None:
        form["proof"] = (io.BytesIO(proof[1]), proof[0])
    form.update(changed)
    form = {k: v for k, v in form.items() if v is not None}
    return client.post("/candidate/bank", data=form, content_type="multipart/form-data")


def _rows(app):
    from kts.db import query
    with app.app_context():
        return [dict(r) for r in query("SELECT * FROM bank_details ORDER BY id")]


def _proofs(app):
    folder = Path(app.config["UPLOAD_DIR"]) / "bankproofs"
    return sorted(p.name for p in folder.glob("*")) if folder.exists() else []


def _query(app, sql, args=()):
    from kts.db import query
    with app.app_context():
        return [dict(r) for r in query(sql, args)]


def _text(key, lang="en"):
    from markupsafe import escape
    from kts.i18n import text
    return str(escape(text(key, lang)))


def _errors(page):
    return re.findall(r'<span class="err"[^>]*>(.*?)</span>', page)


def _sent(app=None, students=None):
    """The first student has sent correct details: (app, students, client of the student)."""
    if app is None:
        app, students = _site()
    client = _student(app, students[0])
    r = _form(client)
    assert r.status_code == 302 and r.headers["Location"].endswith("/candidate/bank"), _errors(r.get_data(as_text=True))
    return app, students, client


def _admin(app, role="admin"):
    return _staff(app, f"{role}@tests.example", role=role)


def _act(client, aid, action, **fields):
    """An action of the staff from the page of the entry as it stands now: the forms send its version as 'seen'."""
    from kts.stipend import _version, entry_of
    with client.application.app_context():
        entry = entry_of(aid)
    seen = _version(entry) if entry is not None else ""
    return client.post(f"/console/stipend/{aid}", data={"_csrf": _token(client), "action": action, "seen": seen, **fields})


def _flashes(client):
    """The messages waiting for the next page of this client."""
    with client.session_transaction() as s:
        return [str(m) for _c, m in s.get("_flashes", [])]


def _lists(admin):
    """The payment lists that the page offers to be marked as paid, newest first."""
    page = admin.get("/console/stipend").get_data(as_text=True)
    return [int(b) for b in re.findall(r'<option value="(\d+)">No\. ', page)]


def _pay_list(admin, ref, on="2026-09-15", batch=None):
    """'Paid' for a payment list: the one given, or the list exported just now."""
    if batch is None:
        admin.get("/console/stipend/export.csv")
        batch = _lists(admin)[0]
    return admin.post("/console/stipend/paid", data={"_csrf": _token(admin), "paid_ref": ref, "paid_on": on, "batch": batch})


def _csv(admin, which="due", **args):
    r = admin.get("/console/stipend/export.csv", query_string={"which": which, **args})
    assert r.status_code == 200, which
    return list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))


def _status(app, aid):
    return _query(app, "SELECT status FROM bank_details WHERE application_id = ?", (aid,))[0]["status"]


def _logged_errors(caplog):
    """The error lines of the log (the warnings of a fresh application are not counted)."""
    import logging
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]


# ---- secure.py ----------------------------------------------------------------

def test_seal_and_unseal():
    from kts import secure
    app = make_app(ADMIN_EMAIL=FIRST)
    with app.app_context():
        for text in (ACCOUNT, AADHAAR, "", "x" * 100):
            token = secure.seal(text)
            assert token.startswith("v1.") and secure.unseal(token) == text
            if text:
                assert text not in token
        # two seals of one text differ, and both open
        one, two = secure.seal(ACCOUNT), secure.seal(ACCOUNT)
        assert one != two and secure.unseal(one) == secure.unseal(two) == ACCOUNT
    key = Path(app.config["INSTANCE_DIR"]) / "stipend.key"
    assert key.is_file() and len(key.read_bytes()) == 64


def test_a_changed_seal_is_refused():
    import base64
    from kts import secure
    app = make_app(ADMIN_EMAIL=FIRST)
    with app.app_context():
        token = secure.seal(ACCOUNT)
        raw = base64.urlsafe_b64decode(token[3:])
        # every byte: nonce, sealed text and tag
        for i in range(len(raw)):
            changed = raw[:i] + bytes([raw[i] ^ 1]) + raw[i + 1:]
            with pytest.raises(ValueError):
                secure.unseal("v1." + base64.urlsafe_b64encode(changed).decode("ascii"))
        for bad in ("", "v1.", "v2." + token[3:], token[3:], token[:-4], token + "AAAA", "v1.!!!!", "v1." + "A" * 40, None, 12345):
            with pytest.raises(ValueError):
                secure.unseal(bad)
    # a seal of another key does not open
    other = make_app(ADMIN_EMAIL=FIRST)
    with other.app_context():
        with pytest.raises(ValueError):
            secure.unseal(token)


def test_lookup_is_stable_and_keyed():
    from kts import secure
    app, other = make_app(ADMIN_EMAIL=FIRST), make_app(ADMIN_EMAIL=FIRST)
    with app.app_context():
        value = secure.lookup(ACCOUNT)
        assert value == secure.lookup(ACCOUNT) and re.fullmatch(r"[0-9a-f]{64}", value)
        assert secure.lookup(OTHER_ACCOUNT) != value and ACCOUNT not in value
    with other.app_context():
        assert secure.lookup(ACCOUNT) != value


def test_masks():
    from kts import secure
    assert secure.mask_account("0987") == "XXXXXX0987" and secure.mask("0987", 12) == "XXXXXXXX0987"
    assert secure.mask_aadhaar("1234") == "XXXX XXXX 1234" and secure.mask_aadhaar("") == ""


def test_key_from_the_setting(monkeypatch):
    from kts import secure
    monkeypatch.setenv("KTS_STIPEND_KEY", "5a" * 64)
    app = make_app(ADMIN_EMAIL=FIRST)
    with app.app_context():
        token = secure.seal(ACCOUNT)
        assert secure.unseal(token) == ACCOUNT
    # no file is made while the setting names the key
    assert not (Path(app.config["INSTANCE_DIR"]) / "stipend.key").exists()
    # another application with the same setting opens the seal
    with make_app(ADMIN_EMAIL=FIRST).app_context():
        assert secure.unseal(token) == ACCOUNT
    # a setting that cannot be used gives no key at all, not the file
    for bad in ("5a" * 63, "zz" * 64, "short"):
        monkeypatch.setenv("KTS_STIPEND_KEY", bad)
        with app.app_context():
            with pytest.raises(secure.NoKey):
                secure.seal(ACCOUNT)
            assert not secure.have_key()
    assert not (Path(app.config["INSTANCE_DIR"]) / "stipend.key").exists()


def test_a_key_file_that_cannot_be_read_is_never_replaced():
    from kts import secure
    app = make_app(ADMIN_EMAIL=FIRST)
    key = Path(app.config["INSTANCE_DIR"]) / "stipend.key"
    key.write_bytes(b"not a key")
    with app.app_context():
        with pytest.raises(secure.NoKey):
            secure.seal(ACCOUNT)
    assert key.read_bytes() == b"not a key"
    # the same key written as 128 hex digits is read as well
    key.write_text("0f" * 64 + "\r\n", encoding="ascii")
    with app.app_context():
        assert secure.unseal(secure.seal(ACCOUNT)) == ACCOUNT


def test_no_key_nothing_is_stored(monkeypatch):
    app, students = _site()
    client = _student(app, students[0])
    monkeypatch.setenv("KTS_STIPEND_KEY", "not hex")
    r = _form(client)
    assert r.status_code == 503 and _text("bank.err_store") in r.get_data(as_text=True)
    assert _rows(app) == [] and _proofs(app) == []
    assert _query(app, "SELECT * FROM outbox") == []
    monkeypatch.delenv("KTS_STIPEND_KEY")
    assert _form(client).status_code == 302 and len(_rows(app)) == 1


def test_a_lost_key_file_is_not_made_anew():
    """Entries are stored and the key file is gone: no new key, nothing stored, until the file is back."""
    app, students, _client = _sent(None)
    key = Path(app.config["INSTANCE_DIR"]) / "stipend.key"
    saved = key.read_bytes()
    key.unlink()
    client = _student(app, students[1])
    r = _form(client, holder_name="Campus Student 2")
    assert r.status_code == 503 and not key.exists()
    assert len(_rows(app)) == 1 and len(_proofs(app)) == 1
    key.write_bytes(saved)
    assert _form(client, holder_name="Campus Student 2").status_code == 302 and len(_rows(app)) == 2


# ---- who may open the form ------------------------------------------------------

@pytest.mark.parametrize("case", ["not_selected", "not_published"])
def test_the_form_is_for_the_selected_list_only(case):
    app, students = _site(published="0" if case == "not_published" else "1",
                          selected=0 if case == "not_selected" else None)
    client = _student(app, students[0])
    r = client.get("/candidate/bank")
    page = r.get_data(as_text=True)
    assert r.status_code == 200 and _text("bank.only_selected") in page
    assert 'name="account"' not in page and _text("bank.notice_pay") not in page
    r = _form(client)
    assert r.status_code == 403 and _rows(app) == [] and _proofs(app) == []
    # no card on the home page either
    assert 'id="bank-card"' not in client.get("/candidate/").get_data(as_text=True)


def test_a_visitor_is_sent_to_the_sign_in():
    app, _students = _site()
    r = app.test_client().get("/candidate/bank")
    assert r.status_code == 302 and r.headers["Location"].endswith("/candidate/login")


def test_the_form_is_closed_until_it_is_opened():
    app, students = _site(form_open="0")
    client = _student(app, students[0])
    page = client.get("/candidate/bank").get_data(as_text=True)
    assert _text("bank.not_open") in page and 'name="account"' not in page
    r = _form(client)
    assert r.status_code == 302 and _rows(app) == [] and _proofs(app) == []
    _setting(app, "stipend.open", "1")
    assert 'name="account"' in client.get("/candidate/bank").get_data(as_text=True)


def test_the_last_date():
    from kts.utils import now_ist
    today = now_ist().date()
    app, students = _site(last_date=(today - timedelta(days=1)).isoformat())
    client = _student(app, students[0])
    page = client.get("/candidate/bank").get_data(as_text=True)
    assert _text("bank.closed") in page and 'name="account"' not in page
    assert _form(client).status_code == 302 and _rows(app) == []
    # the last day itself is open
    _setting(app, "stipend.last_date", today.isoformat())
    assert 'name="account"' in client.get("/candidate/bank").get_data(as_text=True)
    assert _form(client).status_code == 302 and len(_rows(app)) == 1


# ---- the fields -----------------------------------------------------------------

@pytest.fixture(scope="module")
def site():
    app, students = _site()
    return app, _student(app, students[0])


def _refused(site, field, key, **changed):
    app, client = site
    r = _form(client, **changed)
    page = r.get_data(as_text=True)
    assert r.status_code == 400, changed
    assert _rows(app) == [] and _proofs(app) == []
    # the message stands at its field
    if field != "declare":
        marked = re.findall(r'<div class="field[^"]*has-err[^"]*">(.*?)</div>', page, re.S)
        assert any(f'name="{field}"' in block for block in marked), (field, changed)
    assert _text(key) in _errors(page), (_errors(page), changed)
    # the two numbers never come back into the page
    assert ACCOUNT not in page and AADHAAR not in page and SPACED not in page
    return page


@pytest.mark.parametrize("value", ["", "   ", "முருகன்", "राम कुमार", "Ｒａｍｅｓｈ", "x" * 121])
def test_the_name_of_the_holder(site, value):
    key = "reg.err_required" if not value.strip() else ("bank.err_long" if value.startswith("x") else "reg.err_english")
    _refused(site, "holder_name", key, holder_name=value)


@pytest.mark.parametrize("field", ["bank_name", "branch"])
@pytest.mark.parametrize("value", ["", "भारतीय बैंक", "بینک"])
def test_bank_and_branch_in_english(site, field, value):
    _refused(site, field, "reg.err_required" if not value else "reg.err_english", **{field: value})


@pytest.mark.parametrize("value", ["12345678", "1" * 19, "000000000", "1234 5678 90", "12345-67890", "ABC123456789",
                                   "١٢٣٤٥٦٧٨٩٠", "१२३४५६७८९०", "１２３４５６７８９０"])
def test_the_account_number(site, value):
    _refused(site, "account", "bank.err_account", account=value, account_again=value)


def test_the_account_number_is_required(site):
    _refused(site, "account", "reg.err_required", account="", account_again="")


@pytest.mark.parametrize("again", ["00123450987", ACCOUNT + "1", "", "000123450988"])
def test_the_two_account_numbers_must_agree(site, again):
    _refused(site, "account_again", "bank.err_account_match", account_again=again)


@pytest.mark.parametrize("value", ["ABCD1234567", "ABC00123456", "ABCD012345", "ABCD01234567", "ABCD0-12345", "1234012345A",
                                   "АBCD0123456", "ABCD0१२३४५६"])
def test_the_ifsc(site, value):
    _refused(site, "ifsc", "bank.err_ifsc", ifsc=value)


@pytest.mark.parametrize("value", [_wrong(AADHAAR), _aadhaar("13456789012"), _aadhaar("03456789012"), AADHAAR[:11],
                                   AADHAAR + "0", "2345-6789-0123", "ABCD56789012", "२३४५६७८९०१२३"])
def test_the_aadhaar_number(site, value):
    _refused(site, "aadhaar", "bank.err_aadhaar", aadhaar=value)


def test_the_aadhaar_number_is_required_when_asked(site):
    _refused(site, "aadhaar", "reg.err_required", aadhaar="")


@pytest.mark.parametrize("value", [None, "", "fixed", "Savings"])
def test_the_type_of_account(site, value):
    _refused(site, "account_type", "reg.err_required", account_type=value)


@pytest.mark.parametrize("missing", ["declare_own", "declare_correct", "declare_consent"])
def test_the_three_declarations(site, missing):
    _refused(site, "declare", "reg.err_declare", **{missing: None})


@pytest.mark.parametrize("proof", [None, ("cheque.gif", b"GIF89a" + b"\0" * 50), ("cheque.pdf", PNG), ("cheque.png", PDF),
                                   ("cheque.pdf", b""), ("cheque.pdf", b"%PDF-" + b"0" * (2 * 1024 * 1024))],
                         ids=["missing", "gif", "png-as-pdf", "pdf-as-png", "empty", "too-large"])
def test_the_proof(site, proof):
    _refused(site, "proof", "reg.err_idproof", proof=proof)


def test_the_form_in_right_to_left_and_left_to_right():
    app, students = _site()
    client = _student(app, students[0])
    for lang in ("en", "ur", "ks"):
        page = client.get(f"/candidate/bank?lang={lang}").get_data(as_text=True)
        for field in ("holder_name", "account", "account_again", "ifsc", "bank_name", "branch", "aadhaar"):
            start = page.rfind("<", 0, page.find(f'name="{field}"'))
            whole = page[start:page.find(">", start) + 1]
            assert 'dir="ltr"' in whole and 'lang="en"' in whole, (lang, field, whole)
            if field in ("account", "account_again", "aadhaar"):
                assert 'autocomplete="off"' in whole and "value=" not in whole, whole
    client.get("/candidate/bank?lang=en")


def test_the_page_says_how_much_and_how():
    app, students = _site()
    _setting(app, "stipend.amount", "12500")
    page = _student(app, students[0]).get("/candidate/bank").get_data(as_text=True)
    assert "Rs. 12,500" in page
    for key in ("bank.notice_pay", "bank.notice_english", "bank.notice_locked", "bank.registered_name",
                "bank.declare_consent_aadhaar"):
        assert _text(key) in page, key
    assert "Campus Student 1" in page
    # without the question the Aadhaar field and its consent go
    _setting(app, "stipend.aadhaar", "0")
    page = _student(app, students[0]).get("/candidate/bank").get_data(as_text=True)
    assert 'name="aadhaar"' not in page and _text("bank.declare_consent") in page
    assert _text("bank.declare_consent_aadhaar") not in page


def test_rupees():
    from kts.utils import rupees
    assert [rupees(v) for v in (10000, "10000", 999, 125000, 12345678, 0)] == ["10,000", "10,000", "999", "1,25,000",
                                                                                 "1,23,45,678", "0"]


def test_the_check_digit():
    from kts.utils import valid_aadhaar, verhoeff_digit
    # the examples of the Verhoeff scheme
    assert verhoeff_digit("236") == "3" and verhoeff_digit("12345") == "1"
    assert valid_aadhaar(AADHAAR) and not valid_aadhaar(_wrong(AADHAAR))
    # every single wrong digit is found
    for i in range(1, 12):
        for d in "0123456789":
            if d != AADHAAR[i]:
                assert not valid_aadhaar(AADHAAR[:i] + d + AADHAAR[i + 1:]), (i, d)


# ---- a correct entry ---------------------------------------------------------------

def test_a_correct_entry_is_stored_sealed(caplog):
    from kts import secure
    app, students, client = _sent(None)
    rows = _rows(app)
    assert len(rows) == 1
    b = rows[0]
    assert b["application_id"] == students[0]["id"] and b["status"] == "submitted"
    assert b["ifsc"] == IFSC and b["account_last4"] == "0987" and b["aadhaar_last4"] == AADHAAR[-4:]
    assert b["holder_name"] == "Campus Student 1" and b["account_type"] == "savings" and b["proof_name"] == "cheque.pdf"
    assert b["proof_path"].startswith("bankproofs/") and len(_proofs(app)) == 1
    with app.app_context():
        # zeros in front are kept
        assert secure.unseal(b["account_enc"]) == ACCOUNT and secure.unseal(b["aadhaar_enc"]) == AADHAAR
    # nothing secret in plain text anywhere in the files of the database
    folder = Path(app.config["DATABASE"]).parent
    files = [p for p in folder.iterdir() if p.name.startswith(Path(app.config["DATABASE"]).name)]
    assert files
    for path in files:
        raw = path.read_bytes()
        for secret in (ACCOUNT, ACCOUNT.lstrip("0"), AADHAAR, SPACED, AADHAAR[:8]):
            assert secret.encode("ascii") not in raw, (path.name, secret)
            assert secret.encode("utf-16-le") not in raw, (path.name, secret)
    # the mail to the registered address says the last four digits only
    mails = _query(app, "SELECT * FROM outbox")
    assert len(mails) == 1 and mails[0]["to_addr"] == students[0]["email"]
    assert "ending in 0987" in mails[0]["body"] and students[0]["app_no"] in mails[0]["body"]
    assert "write to CICT at once" in mails[0]["body"]
    audit = _query(app, "SELECT * FROM audit_log WHERE action = 'bank_submitted'")
    assert len(audit) == 1 and audit[0]["entity_id"] == students[0]["id"] and "0987" in audit[0]["detail"]
    for row in mails + audit:
        for secret in (ACCOUNT, ACCOUNT.lstrip("0"), AADHAAR):
            assert secret not in str(row), row
    for secret in (ACCOUNT, ACCOUNT.lstrip("0"), AADHAAR):
        assert secret not in caplog.text
    # the page shows the entry masked
    page = client.get("/candidate/bank").get_data(as_text=True)
    assert "XXXXXX0987" in page and f"XXXX XXXX {AADHAAR[-4:]}" in page and IFSC in page
    assert _text("bank.st_submitted") in page and 'name="account"' not in page
    assert ACCOUNT not in page and AADHAAR not in page
    r = client.get("/candidate/bank")
    assert "no-store" in r.headers["Cache-Control"]


def test_a_sent_entry_is_locked():
    app, _students, client = _sent(None)
    before, files = _rows(app), _proofs(app)
    r = _form(client, account=OTHER_ACCOUNT, account_again=OTHER_ACCOUNT, holder_name="Somebody Else")
    assert r.status_code == 302
    assert _rows(app) == before and _proofs(app) == files
    assert _text("bank.locked") in client.get("/candidate/bank").get_data(as_text=True)
    assert len(_query(app, "SELECT * FROM outbox")) == 1


def test_the_limit_of_submissions():
    app, students = _site()
    client = _student(app, students[0])
    for _ in range(10):
        assert _form(client, account="1").status_code == 400
    r = _form(client)
    assert r.status_code == 400 and _text("reg.err_rate") in r.get_data(as_text=True)
    assert _rows(app) == [] and _proofs(app) == []
    # another student from the same address is not held up
    assert _form(_student(app, students[1]), holder_name="Campus Student 2").status_code == 302


def test_another_student_never_sees_or_changes_this_entry():
    app, students, _client = _sent(None)
    first = _rows(app)[0]
    other = _student(app, students[1])
    page = other.get("/candidate/bank").get_data(as_text=True)
    assert 'name="account"' in page and "XXXXXX0987" not in page and IFSC not in page
    # whatever the form names, the entry is that of the student who is signed in
    r = _form(other, holder_name="Campus Student 2", account=OTHER_ACCOUNT, account_again=OTHER_ACCOUNT,
              application_id=str(students[0]["id"]))
    assert r.status_code == 302
    rows = _rows(app)
    assert rows[0] == first and rows[1]["application_id"] == students[1]["id"]
    # the console has an address per application; the candidate area has none
    assert other.get(f"/console/stipend/{students[0]['id']}").status_code == 302


# ---- the home page of the candidate ----------------------------------------------------

def test_the_card_on_the_home_page():
    app, students = _site()
    client = _student(app, students[0])
    page = client.get("/candidate/").get_data(as_text=True)
    card = page[page.find('id="bank-card"'):]
    assert _text("bank.title") in card and _text("bank.st_form") in card and 'href="/candidate/bank"' in card
    assert _form(client).status_code == 302
    card = client.get("/candidate/").get_data(as_text=True)
    assert _text("bank.st_submitted") in card[card.find('id="bank-card"'):]


@pytest.mark.parametrize("lang", ["ta", "hi", "ur", "sat"])
def test_the_pages_in_other_languages(lang):
    """Until the translators have them, the new texts stand in English; never a key."""
    app, students = _site()
    client = _student(app, students[0])
    from kts.i18n import LANG_INFO
    for path in ("/candidate/bank", "/candidate/"):
        page = client.get(f"{path}?lang={lang}").get_data(as_text=True)
        assert f'<html lang="{lang}" dir="{LANG_INFO[lang]["dir"]}"' in page
        assert not re.findall(r"[>\"']\s*bank\.[a-z_]+\s*[<\"']", page), path
        assert _text("bank.title", lang) in page
    assert _form(client).status_code == 302
    page = client.get(f"/candidate/bank?lang={lang}").get_data(as_text=True)
    assert "XXXXXX0987" in page and not re.findall(r">\s*bank\.[a-z_]+\s*<", page)
    client.get("/candidate/?lang=en")


# ---- return, correction, approval, payment ---------------------------------------------------

def test_return_correct_and_send_again():
    from kts import secure
    app, students, client = _sent(None)
    aid = students[0]["id"]
    chief = _admin(app)
    first_proof = _proofs(app)
    # a remark is required, and it must not hold the numbers
    assert _act(chief, aid, "return", remark="").status_code == 302 and _status(app, aid) == "submitted"
    _act(chief, aid, "return", remark=f"The number {ACCOUNT[:6]} {ACCOUNT[6:]} is not on the cheque")
    assert _status(app, aid) == "submitted"
    _act(chief, aid, "return", remark="The name on the cheque is not yours. Upload the passbook of your own account.")
    assert _status(app, aid) == "returned"
    mail = _query(app, "SELECT * FROM outbox ORDER BY id DESC LIMIT 1")[0]
    assert "passbook of your own account" in mail["body"] and ACCOUNT not in mail["body"]
    # the student sees the remark and the form, with what is no secret filled in
    page = client.get("/candidate/bank").get_data(as_text=True)
    assert "passbook of your own account" in page and 'name="account"' in page
    assert f'value="{IFSC}"' in page and 'value="Test Bank of the Tests"' in page
    assert ACCOUNT not in page and AADHAAR not in page
    # sent again after the last date, with the proof kept
    from kts.utils import now_ist
    _setting(app, "stipend.last_date", (now_ist().date() - timedelta(days=3)).isoformat())
    r = _form(client, proof=None, account=OTHER_ACCOUNT, account_again=OTHER_ACCOUNT)
    assert r.status_code == 302
    rows = _rows(app)
    assert len(rows) == 1 and rows[0]["status"] == "submitted" and rows[0]["account_last4"] == "4567"
    assert _proofs(app) == first_proof
    with app.app_context():
        assert secure.unseal(rows[0]["account_enc"]) == OTHER_ACCOUNT
    # returned once more and sent with a new proof: the old file goes
    _act(chief, aid, "return", remark="Upload a clearer photo.")
    assert _form(client, proof=("passbook.png", PNG)).status_code == 302
    assert len(_proofs(app)) == 1 and _proofs(app) != first_proof and _rows(app)[0]["proof_name"] == "passbook.png"
    actions = [r["action"] for r in _query(app, "SELECT action FROM audit_log WHERE action LIKE 'bank_%' ORDER BY id")]
    assert actions.count("bank_returned") == 2 and actions.count("bank_submitted") == 3


def test_approve_pay_and_undo():
    app, students, client = _sent(None)
    aid = students[0]["id"]
    admin = _admin(app)
    # nothing is paid before it is approved
    _act(admin, aid, "paid", paid_ref="UTR-TEST-1", paid_on="2026-09-01")
    assert _status(app, aid) == "submitted"
    _act(admin, aid, "approve")
    assert _status(app, aid) == "approved"
    assert "approved" in _query(app, "SELECT subject FROM outbox ORDER BY id DESC LIMIT 1")[0]["subject"]
    # approving again changes nothing
    _act(admin, aid, "approve")
    assert len(_query(app, "SELECT * FROM audit_log WHERE action = 'bank_approved'")) == 1
    # a payment needs a reference and a date that is not in the future
    from kts.utils import now_ist
    for fields in ({"paid_ref": "", "paid_on": "2026-09-01"}, {"paid_ref": "UTR-TEST-1", "paid_on": ""},
                   {"paid_ref": "UTR-TEST-1", "paid_on": (now_ist().date() + timedelta(days=2)).isoformat()},
                   {"paid_ref": "UTR-TEST-1", "paid_on": "01-09-2026"}, {"paid_ref": f"NEFT {ACCOUNT}", "paid_on": "2026-09-01"}):
        _act(admin, aid, "paid", **fields)
        assert _status(app, aid) == "approved", fields
    _act(admin, aid, "paid", paid_ref="UTR-TEST-1", paid_on="2026-09-01")
    assert _status(app, aid) == "paid"
    mail = _query(app, "SELECT * FROM outbox ORDER BY id DESC LIMIT 1")[0]
    assert "UTR-TEST-1" in mail["body"] and "Rs. 10,000" in mail["body"] and "ending in 0987" in mail["body"]
    page = client.get("/candidate/bank").get_data(as_text=True)
    assert "UTR-TEST-1" in page and _text("bank.paid_text") in page
    # only a superadmin takes the mark back
    assert _act(admin, aid, "unpaid").status_code == 403 and _status(app, aid) == "paid"
    chief = _staff(app)
    _act(chief, aid, "unpaid")
    assert _status(app, aid) == "approved"
    row = _rows(app)[0]
    assert row["paid_ref"] == "" and row["paid_on"] == ""
    actions = [r["action"] for r in _query(app, "SELECT action FROM audit_log WHERE action LIKE 'bank_%' ORDER BY id")]
    assert actions == ["bank_submitted", "bank_approved", "bank_paid", "bank_unpaid"]
    subjects = [m["subject"] for m in _query(app, "SELECT subject FROM outbox ORDER BY id")]
    assert len(subjects) == 4 and "withdrawn" in subjects[-1]
    # a student who leaves the selected list is neither approved nor paid
    from kts.db import execute
    with app.app_context():
        execute("UPDATE applications SET status = 'withdrawn' WHERE id = ?", (aid,))
    _act(admin, aid, "paid", paid_ref="UTR-TEST-2", paid_on="2026-09-01")
    assert _status(app, aid) == "approved"


def test_the_page_of_one_entry():
    app, students, _client = _sent(None)
    aid = students[0]["id"]
    admin = _admin(app)
    page = admin.get(f"/console/stipend/{aid}").get_data(as_text=True)
    assert ACCOUNT in page and f"{AADHAAR[:4]} {AADHAAR[4:8]} {AADHAAR[8:]}" in page and IFSC in page
    assert "Campus Student 1" in page and "Test Bank of the Tests" in page
    assert f'href="/console/files/{_rows(app)[0]["proof_path"]}"' in page
    viewed = _query(app, "SELECT * FROM audit_log WHERE action = 'bank_viewed'")
    assert len(viewed) == 1 and viewed[0]["actor"] == "admin@tests.example" and ACCOUNT not in viewed[0]["detail"]
    # names that differ are pointed out
    assert "not written alike" not in page
    from kts.db import execute
    with app.app_context():
        execute("UPDATE bank_details SET holder_name = 'Somebody Else'")
    assert "not written alike" in admin.get(f"/console/stipend/{aid}").get_data(as_text=True)
    # an application without an entry, and one that does not exist
    assert admin.get(f"/console/stipend/{students[1]['id']}").status_code == 200
    assert admin.get("/console/stipend/99999").status_code == 404


def test_the_application_page_names_the_state():
    app, students, _client = _sent(None)
    aid = students[0]["id"]
    page = _admin(app).get(f"/console/applications/{aid}").get_data(as_text=True)
    assert f'href="/console/stipend/{aid}"' in page and "Bank details for the stipend" in page
    page = _admin(app, "verifier").get(f"/console/applications/{aid}").get_data(as_text=True)
    assert "/console/stipend" not in page


# ---- the console: who may ----------------------------------------------------------

@pytest.mark.parametrize("role", ["verifier", "content", "agency", "viewer"])
def test_the_console_pages_need_the_permission(role):
    app, students, _client = _sent(None)
    aid = students[0]["id"]
    client = _admin(app, role)
    for path in ("/console/stipend", f"/console/stipend/{aid}", "/console/stipend/export.xlsx",
                 "/console/stipend/export.csv?aadhaar=1"):
        r = client.get(path)
        assert r.status_code == 403, path
        assert ACCOUNT.encode() not in r.data
    for path, data in ((f"/console/stipend/{aid}", {"action": "approve"}),
                       ("/console/stipend/paid", {"paid_ref": "X-1", "paid_on": "2026-09-01"})):
        assert client.post(path, data={"_csrf": _token(client), **data}).status_code == 403
    assert _status(app, aid) == "submitted"
    assert _query(app, "SELECT * FROM audit_log WHERE action IN ('bank_viewed', 'bank_exported')") == []
    if role != "agency":
        assert "/console/stipend" not in client.get("/console/").get_data(as_text=True)


def test_visitors_are_sent_to_the_sign_in():
    app, students, _client = _sent(None)
    visitor = app.test_client()
    for path in ("/console/stipend", f"/console/stipend/{students[0]['id']}", "/console/stipend/export.csv"):
        r = visitor.get(path)
        assert r.status_code == 302 and r.headers["Location"] == "/console/login", path


def test_the_menu_and_the_list():
    app, students, _client = _sent(None)
    admin = _admin(app)
    page = admin.get("/console/").get_data(as_text=True)
    assert 'href="/console/stipend"' in page
    page = admin.get("/console/stipend").get_data(as_text=True)
    assert "XXXXXX0987" in page and ACCOUNT not in page and AADHAAR not in page and IFSC in page
    for s in students:
        assert s["app_no"] in page
    page = admin.get("/console/stipend?state=none").get_data(as_text=True)
    assert students[1]["app_no"] in page and students[0]["app_no"] not in page
    page = admin.get("/console/stipend", query_string={"state": "submitted", "q": "Student 1"}).get_data(as_text=True)
    assert students[0]["app_no"] in page and students[1]["app_no"] not in page
    assert "no-store" in admin.get("/console/stipend").headers["Cache-Control"]


def test_one_account_for_two_applications_is_marked():
    app, students = _site(n=3)
    _sent(app, students)
    # the second gives the same account, with one more zero in front
    other = _student(app, students[1])
    assert _form(other, holder_name="Campus Student 2", account="0" + ACCOUNT, account_again="0" + ACCOUNT).status_code == 302
    third = _student(app, students[2])
    assert _form(third, holder_name="Campus Student 3", account=OTHER_ACCOUNT, account_again=OTHER_ACCOUNT).status_code == 302
    admin = _admin(app)
    page = admin.get("/console/stipend").get_data(as_text=True)
    assert page.count("⚠ same account") == 2
    page = admin.get("/console/stipend?state=same").get_data(as_text=True)
    assert students[0]["app_no"] in page and students[1]["app_no"] in page and students[2]["app_no"] not in page
    page = admin.get(f"/console/stipend/{students[0]['id']}").get_data(as_text=True)
    assert f'href="/console/stipend/{students[1]["id"]}"' in page and "Campus Student 2" in page
    page = admin.get(f"/console/stipend/{students[2]['id']}").get_data(as_text=True)
    assert "No other application gives this account" in page


# ---- the proof ------------------------------------------------------------------------

def test_the_proof_is_for_the_permission_only():
    app, students, _client = _sent(None)
    name = _rows(app)[0]["proof_path"]
    admin, chief = _admin(app), _staff(app)
    for client in (admin, chief):
        r = client.get(f"/console/files/{name}")
        assert r.status_code == 200 and r.data == PDF
        r.close()
    opened = _query(app, "SELECT * FROM audit_log WHERE action = 'bank_proof_opened'")
    assert len(opened) == 2 and opened[0]["entity_id"] == students[0]["id"]
    visitor = app.test_client()
    for role in ("verifier", "content", "agency", "viewer"):
        assert _answer(_admin(app, role), f"/console/files/{name}") == 403, role
    agency = _staff(app, "agency2@tests.example", role="agency")
    for client, path, status in ((visitor, f"/console/files/{name}", 302), (visitor, f"/files/{name}", 404),
                                 (visitor, f"/files/notices/../{name}", 404), (agency, f"/hub/files/{name}", 404),
                                 (agency, f"/hub/files/tasks/../{name}", 404), (visitor, f"/hub/files/{name}", 302),
                                 (admin, f"/console/files/BankProofs/{name.split('/')[1]}", 404),
                                 (admin, f"/console/files/bankproofs./{name.split('/')[1]}", 404)):
        assert _answer(client, path) == status, path
    # the key is no address either
    key = (Path(app.config["INSTANCE_DIR"]) / "stipend.key").read_bytes()
    for path in ("/instance/stipend.key", "/files/../instance/stipend.key", "/static/../instance/stipend.key",
                 "/console/files/../instance/stipend.key", "/console/files/bankproofs/../../instance/stipend.key"):
        for client in (visitor, admin):
            r = client.get(path)
            assert r.status_code in (302, 404) and key not in r.data, path


def test_the_key_is_kept_out_of_git():
    from conftest import ROOT
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "stipend.key" in lines and "instance/*" in lines


# ---- export and payment of all ----------------------------------------------------------

def _approved(n=3):
    """n students, the first two approved, the third only submitted."""
    app, students = _site(n=n)
    admin = _admin(app)
    for i, s in enumerate(students):
        client = _student(app, s)
        account = ACCOUNT if i == 0 else f"55500{i}0000{i}"
        r = _form(client, holder_name=s["name"], account=account, account_again=account, aadhaar=_aadhaar(f"2{i}345678901"))
        assert r.status_code == 302
        if i < 2:
            _act(admin, s["id"], "approve")
    return app, students, admin


def _sheet(data):
    """
    The cells of the first sheet of an xlsx file, {'E2': (type, value)}, strings read from the
    shared table, and the number format of each cell, {'E2': '@'}.
    """
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared = ["".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t"))
                  for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns)]
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        styles = ET.fromstring(z.read("xl/styles.xml"))
    # format 49 of Excel is Text, "@"; the others that matter here are written into the file
    codes = {"0": "General", "49": "@"}
    codes.update({f.get("numFmtId"): f.get("formatCode") for f in styles.iter(f"{{{ns['m']}}}numFmt")})
    xfs = [xf.get("numFmtId") for xf in styles.find("m:cellXfs", ns).findall("m:xf", ns)]
    cells, formats = {}, {}
    for c in sheet.iter(f"{{{ns['m']}}}c"):
        v = c.find("m:v", ns)
        kind = c.get("t", "n")
        value = v.text if v is not None else None
        cells[c.get("r")] = (kind, shared[int(value)] if kind == "s" else value)
        formats[c.get("r")] = codes.get(xfs[int(c.get("s", "0"))])
    return cells, formats


def test_the_export_writes_account_numbers_as_text():
    app, students, admin = _approved()
    r = admin.get("/console/stipend/export.xlsx")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    # the export of what is to pay is payment list no. 1, and its file says so
    assert "filename=KTS5-stipend-due-list1-" in r.headers["Content-Disposition"]
    assert "no-store" in r.headers["Cache-Control"]
    cells, formats = _sheet(r.data)
    assert cells["E1"] == ("s", "Account number") and cells["J1"] == ("s", "Amount (Rs.)")
    # the account number is a string cell with its zeros in front, in the format Text
    assert cells["E2"] == ("s", ACCOUNT) and cells["B2"] == ("s", students[0]["app_no"])
    assert formats["E2"] == formats["E3"] == formats["N2"] == "@"
    assert cells["E3"] == ("s", "55500100001") and cells["N2"] == ("s", "9876500001")
    assert cells["J2"] == ("n", "10000") and cells["A2"] == ("n", "1") and formats["J2"] == "General"
    # approved and not yet paid: two rows; the third entry is not approved and is never in it
    assert "B3" in cells and "B4" not in cells
    assert students[2]["app_no"] not in str(cells)
    # who approved, and when, stand at the end; no Aadhaar column unless it is asked for
    assert cells["R1"] == ("s", "Approved by") and cells["S1"] == ("s", "Approved on") and cells["R2"] == ("s", "Test admin")
    assert re.fullmatch(r"\d\d-\d\d-\d{4}, \d\d:\d\d", cells["S2"][1]) and formats["S2"] == "@"
    assert "T1" not in cells and AADHAAR not in str(cells)
    cells, _styles = _sheet(admin.get("/console/stipend/export.xlsx?aadhaar=1").data)
    assert cells["T1"] == ("s", "Aadhaar number") and cells["T2"] == ("s", _aadhaar("20345678901"))
    # the audit row says what went out and its sum, and which payment list it is
    audit = _query(app, "SELECT * FROM audit_log WHERE action = 'bank_exported' ORDER BY id")
    assert [a["detail"] for a in audit] == [
        '{"rows": 2, "amount": 20000, "which": "due", "fmt": "xlsx", "aadhaar": false, "list": 1}',
        '{"rows": 2, "amount": 20000, "which": "due", "fmt": "xlsx", "aadhaar": true, "list": 2}']
    assert audit[0]["actor"] == "admin@tests.example"
    lists = _query(app, "SELECT * FROM stipend_batches ORDER BY id")
    assert [(b["id"], b["rows"], b["settled_at"]) for b in lists] == [(1, 2, None), (2, 2, None)]
    assert all(ACCOUNT not in b["entries"] and json.loads(b["entries"]) for b in lists)


def test_the_export_as_csv():
    app, students, admin = _approved()
    r = admin.get("/console/stipend/export.csv")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    rows = list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
    assert rows[0][4] == "Account number" and len(rows) == 3 and len(rows[0]) == 19
    # Excel shows ="000123450987" as the text 000123450987
    assert rows[1][4] == f'="{ACCOUNT}"' and rows[1][5] == IFSC and rows[1][9] == "10000" and rows[1][17] == "Test admin"
    rows = list(csv.reader(io.StringIO(admin.get("/console/stipend/export.csv?aadhaar=1").data.decode("utf-8-sig"))))
    assert rows[0][19] == "Aadhaar number" and rows[1][19] == f'="{_aadhaar("20345678901")}"'
    # what a student typed is never a formula
    from kts.db import execute
    with app.app_context():
        execute("UPDATE bank_details SET branch = '=HYPERLINK(\"http://example.org\")' WHERE application_id = ?",
                (students[0]["id"],))
    rows = list(csv.reader(io.StringIO(admin.get("/console/stipend/export.csv").data.decode("utf-8-sig"))))
    assert rows[1][7].startswith("'=")
    cells, _styles = _sheet(admin.get("/console/stipend/export.xlsx").data)
    assert cells["H2"][0] == "s" and cells["H2"][1].startswith("=HYPERLINK")
    assert len(_query(app, "SELECT * FROM audit_log WHERE action = 'bank_exported'")) == 4
    # an unknown choice gives nothing
    assert admin.get("/console/stipend/export.csv?which=everything").status_code == 404
    assert admin.get("/console/stipend/export.pdf").status_code == 404


def test_the_entries_of_a_payment_list_are_paid_at_once():
    app, students, admin = _approved()
    before = len(_query(app, "SELECT * FROM outbox"))
    # without a payment list nothing is marked
    r = admin.post("/console/stipend/paid", data={"_csrf": _token(admin), "paid_ref": "BATCH-TEST-7", "paid_on": "2026-09-15"})
    assert r.status_code == 302 and [x["status"] for x in _rows(app)] == ["approved", "approved", "submitted"]
    assert "Choose the payment list" in " ".join(_flashes(admin))
    page = admin.get("/console/stipend").get_data(as_text=True)
    assert "No payment list is waiting" in page and _lists(admin) == []
    # a date in the future is refused
    from kts.utils import now_ist
    later = (now_ist().date() + timedelta(days=1)).isoformat()
    r = _pay_list(admin, "BATCH-TEST-7", later)
    assert r.status_code == 302 and [x["status"] for x in _rows(app)] == ["approved", "approved", "submitted"]
    assert _lists(admin) == [1]
    r = _pay_list(admin, "BATCH-TEST-7", batch=1)
    assert r.status_code == 302
    rows = _rows(app)
    assert [x["status"] for x in rows] == ["paid", "paid", "submitted"]
    assert rows[0]["paid_ref"] == "BATCH-TEST-7" and rows[0]["paid_on"] == "2026-09-15" and rows[0]["paid_amount"] == 10000
    assert "2 entries of payment list no. 1 marked as paid" in " ".join(_flashes(admin))
    mails = _query(app, "SELECT * FROM outbox ORDER BY id")[before:]
    assert sorted(m["to_addr"] for m in mails) == [students[0]["email"], students[1]["email"]]
    assert all("BATCH-TEST-7" in m["body"] and ACCOUNT not in m["body"] for m in mails)
    paid = _query(app, "SELECT * FROM audit_log WHERE action = 'bank_paid'")
    assert sorted(a["entity_id"] for a in paid) == [students[0]["id"], students[1]["id"]]
    assert all("payment list 1" in a["detail"] for a in paid)
    # the list is settled: it is offered no more, and nothing is paid from it a second time
    settled = _query(app, "SELECT * FROM stipend_batches")[0]
    assert settled["settled_at"] and settled["paid_ref"] == "BATCH-TEST-7" and settled["paid_on"] == "2026-09-15"
    assert _lists(admin) == []
    _pay_list(admin, "BATCH-AGAIN", batch=1)
    assert "Choose the payment list" in " ".join(_flashes(admin))
    assert [x["paid_ref"] for x in _rows(app)] == ["BATCH-TEST-7", "BATCH-TEST-7", ""]
    # paid entries in the export of the paid ones, and in "approved and paid"
    cells, _styles = _sheet(admin.get("/console/stipend/export.xlsx?which=paid").data)
    assert cells["O2"] == ("s", "paid") and cells["P2"] == ("s", "BATCH-TEST-7") and "B4" not in cells
    cells, _styles = _sheet(admin.get("/console/stipend/export.xlsx").data)
    assert "B2" not in cells
    cells, _styles = _sheet(admin.get("/console/stipend/export.xlsx?which=all").data)
    assert "B3" in cells and "B4" not in cells


def test_the_mails_of_a_payment_to_all_go_out_in_the_background(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, msg):
            sent.append(msg["To"])

    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    app, students, admin = _approved()
    app.config["SMTP_HOST"] = "mail.tests.example"
    r = _pay_list(admin, "BATCH-TEST-8")
    assert r.status_code == 302
    # the page only queues them, as mails of a list (1.2.35): the sender of the outbox sends them
    assert sent == []
    queued = _query(app, "SELECT status, priority FROM outbox WHERE subject LIKE '%stipend paid%'")
    assert [(m["status"], m["priority"]) for m in queued] == [("queued", 1), ("queued", 1)]
    from kts import mailq
    # with them go the mails to one person queued before (bank details submitted, approved), these first
    assert mailq.run_once(app)["sent"] == len(_query(app, "SELECT id FROM outbox"))
    assert sent[-2:] == [students[0]["email"], students[1]["email"]] or sorted(sent[-2:]) == sorted([students[0]["email"], students[1]["email"]])
    subjects = _query(app, "SELECT status FROM outbox WHERE subject LIKE '%stipend paid%'")
    assert [m["status"] for m in subjects] == ["sent", "sent"]


def test_an_entry_of_a_student_who_left_the_list_is_never_paid():
    app, students, admin = _approved()
    # the list goes out with both; the first student leaves the selected list before the bank pays
    assert len(_csv(admin)) == 3
    from kts.db import execute
    with app.app_context():
        execute("UPDATE applications SET status = 'withdrawn' WHERE id = ?", (students[0]["id"],))
    _pay_list(admin, "BATCH-TEST-9", batch=1)
    assert [x["status"] for x in _rows(app)] == ["approved", "paid", "submitted"]
    assert "1 entries of the list were changed" in " ".join(_flashes(admin))
    rows = _csv(admin, "all")
    assert len(rows) == 2 and rows[1][1] == students[1]["app_no"]
    page = admin.get("/console/stipend").get_data(as_text=True)
    assert "no longer in the selected list" in page and "Of these" not in page
    assert students[0]["app_no"] in admin.get("/console/stipend?state=off").get_data(as_text=True)


def test_a_later_approval_is_not_paid_from_an_earlier_list():
    """Monday the list goes to the bank; during the week more are approved; Friday only that list is marked."""
    app, students, admin = _approved()
    admin.get("/console/stipend")
    monday = _csv(admin)
    assert [r[1] for r in monday[1:]] == [students[0]["app_no"], students[1]["app_no"]]
    # nothing was left out, so nothing is said
    assert _flashes(admin) == []
    # the same list downloaded again, with the Aadhaar numbers, is a list of its own with the same rows
    admin.get("/console/stipend/export.xlsx?aadhaar=1")
    # during the week the third is approved
    _act(admin, students[2]["id"], "approve")
    assert _lists(admin) == [2, 1]
    # Friday: the bank confirms Monday's file
    _pay_list(admin, "BATCH-MON", batch=1)
    assert [x["status"] for x in _rows(app)] == ["paid", "paid", "approved"]
    mails = _query(app, "SELECT to_addr FROM outbox WHERE subject LIKE '%stipend paid%'")
    assert sorted(m["to_addr"] for m in mails) == [students[0]["email"], students[1]["email"]]
    # the third is still due and goes into the next list; list no. 2 pays nobody a second time
    assert [r[1] for r in _csv(admin)[1:]] == [students[2]["app_no"]]
    _pay_list(admin, "BATCH-AGAIN", batch=2)
    assert [x["status"] for x in _rows(app)] == ["paid", "paid", "approved"]
    assert _rows(app)[0]["paid_ref"] == "BATCH-MON"
    assert "0 entries of payment list no. 2" in " ".join(_flashes(admin)) and "2 entries of the list were changed" in " ".join(_flashes(admin))
    lists = _query(app, "SELECT * FROM stipend_batches ORDER BY id")
    assert [(b["rows"], bool(b["settled_at"])) for b in lists] == [(2, True), (2, True), (1, False)]
    assert all(ACCOUNT not in b["entries"] and "5550010000" not in b["entries"] for b in lists)


def test_a_list_is_made_by_a_download_with_rows_only_and_every_unsettled_list_is_offered():
    """A GET of the due export with rows makes a list; a HEAD or an export without rows makes none; Monday's list stays offered after twenty more looks."""
    app, students, admin = _approved()
    # a HEAD (a download manager or a link checker) gets the headers of the file and makes nothing
    head = admin.head("/console/stipend/export.csv")
    assert head.status_code == 200 and head.data == b"" and "attachment; filename=KTS5-stipend-due-2" in head.headers["Content-Disposition"]
    assert "-list" not in head.headers["Content-Disposition"]
    assert admin.head("/console/stipend/export.csv?which=none").status_code == 200
    assert _query(app, "SELECT * FROM stipend_batches") == [] and _lists(admin) == []
    assert _query(app, "SELECT * FROM audit_log WHERE action = 'bank_exported'") == []
    # a GET with rows makes list no. 1, and the HEAD had the headers of the same file
    got = admin.get("/console/stipend/export.csv")
    assert "filename=KTS5-stipend-due-list1-" in got.headers["Content-Disposition"]
    assert head.headers["Content-Length"] == str(len(got.data)) and head.headers["Content-Type"] == got.headers["Content-Type"]
    assert len(_query(app, "SELECT * FROM audit_log WHERE action = 'bank_exported'")) == 1
    # the option names the list with its date, time, rows and amount
    page = admin.get("/console/stipend").get_data(as_text=True)
    option = re.search(r'<option value="1">([^<]*)</option>', page).group(1)
    made = _query(app, "SELECT created_at FROM stipend_batches")[0]["created_at"]
    from kts.utils import fmt_dt
    assert option == f"No. 1 · {fmt_dt(made)} · 2 entries · Rs. 10,000 each"
    # no list is chosen in advance: the staff pick the number that the file carries
    assert '<option value="" disabled selected>' in page and 'selected>No. ' not in page
    # the third is approved; twenty more downloads make twenty lists, and Monday's stays on the page
    _act(admin, students[2]["id"], "approve")
    for _ in range(20):
        assert admin.get("/console/stipend/export.csv").status_code == 200
    assert _lists(admin) == list(range(21, 0, -1))
    # once every approved entry is paid, a download of the due list has no rows and makes no list
    _pay_list(admin, "BATCH-MON", batch=1)
    assert [x["status"] for x in _rows(app)] == ["paid", "paid", "approved"]
    assert "2 entries of payment list no. 1 marked as paid" in " ".join(_flashes(admin))
    assert _lists(admin) == list(range(21, 1, -1))
    _pay_list(admin, "BATCH-FRI", batch=21)
    assert [x["status"] for x in _rows(app)] == ["paid", "paid", "paid"]
    assert len(_csv(admin)) == 1 and len(_query(app, "SELECT * FROM stipend_batches")) == 21
    assert _lists(admin) == list(range(20, 1, -1))


def test_a_payment_list_that_never_went_to_the_bank_is_discarded():
    """A look at the due list that did not go to the bank is discarded: settled, nothing paid, its entries free for the next list."""
    app, students, admin = _approved()
    aid = students[0]["id"]
    _csv(admin)
    admin.get("/console/stipend/export.xlsx")
    assert _lists(admin) == [2, 1]
    assert "In payment list no. 2" in admin.get(f"/console/stipend/{aid}").get_data(as_text=True)
    page = admin.get("/console/stipend").get_data(as_text=True)
    button = re.search(r'<button[^>]*formaction="/console/stipend/discard"[^>]*>', page).group(0)
    assert 'data-confirm="Discard the chosen payment list?' in button and "formnovalidate" in button
    # without the CSRF token, or without a list, nothing is done
    assert admin.post("/console/stipend/discard", data={"batch": "2"}).status_code == 400
    r = admin.post("/console/stipend/discard", data={"_csrf": _token(admin), "batch": ""})
    assert r.status_code == 302 and "Choose the payment list to discard" in " ".join(_flashes(admin))
    r = admin.post("/console/stipend/discard", data={"_csrf": _token(admin), "batch": "2"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/console/stipend")
    assert "Payment list no. 2 (2 entries) was discarded" in " ".join(_flashes(admin))
    lists = _query(app, "SELECT * FROM stipend_batches ORDER BY id")
    assert [(b["id"], b["paid_ref"], bool(b["settled_at"])) for b in lists] == [(1, "", False), (2, "discarded", True)]
    assert [x["status"] for x in _rows(app)] == ["approved", "approved", "submitted"]
    assert not _query(app, "SELECT * FROM audit_log WHERE action = 'bank_paid'")
    discarded = _query(app, "SELECT * FROM audit_log WHERE action = 'bank_list_discarded'")
    assert len(discarded) == 1 and discarded[0]["actor"] == "admin@tests.example"
    assert "payment list 2 discarded: 2 entries" in discarded[0]["detail"] and ACCOUNT not in discarded[0]["detail"]
    # the page of the entry names list no. 1 only; the select offers list no. 1 only
    page = admin.get(f"/console/stipend/{aid}").get_data(as_text=True)
    assert "In payment list no. 1" in page and "In payment list no. 2" not in page
    assert _lists(admin) == [1]
    # a discarded list is not discarded or paid a second time; the last list goes too, and the entries go into the next
    admin.post("/console/stipend/discard", data={"_csrf": _token(admin), "batch": "2"})
    assert "Choose the payment list to discard" in " ".join(_flashes(admin))
    _pay_list(admin, "BATCH-X", batch=2)
    assert "Choose the payment list" in " ".join(_flashes(admin)) and [x["status"] for x in _rows(app)] == ["approved", "approved", "submitted"]
    admin.post("/console/stipend/discard", data={"_csrf": _token(admin), "batch": "1"})
    assert _lists(admin) == [] and "In payment list" not in admin.get(f"/console/stipend/{aid}").get_data(as_text=True)
    assert "No payment list is waiting" in admin.get("/console/stipend").get_data(as_text=True)
    third = _csv(admin)
    assert [row[1] for row in third[1:]] == [students[0]["app_no"], students[1]["app_no"]] and _lists(admin) == [3]
    # a paid list is not discarded either
    _pay_list(admin, "BATCH-3", batch=3)
    admin.post("/console/stipend/discard", data={"_csrf": _token(admin), "batch": "3"})
    assert "Choose the payment list to discard" in " ".join(_flashes(admin))
    assert _query(app, "SELECT paid_ref FROM stipend_batches WHERE id = 3")[0]["paid_ref"] == "BATCH-3"
    # the rows of the audit log are for the permission
    for role in ("verifier", "content", "viewer"):
        client = _admin(app, role)
        assert client.post("/console/stipend/discard", data={"_csrf": _token(client), "batch": "1"}).status_code == 403
        assert "bank_list_discarded" not in client.get("/console/").get_data(as_text=True)


def test_a_payment_list_is_downloaded_again_without_making_a_new_list(monkeypatch):
    """The file of a list again, as its entries stand now, with the mark of what has changed; no new list."""
    app, students, admin = _approved(4)
    _act(admin, students[2]["id"], "approve")
    assert len(_csv(admin)) == 4 and _lists(admin) == [1]
    # since the list went out: the second paid one by one (at the sum of the list, whatever the setting), the third no
    # longer selected, the setting raised
    import kts.stipend
    monkeypatch.setattr(kts.stipend, "utcnow", lambda: "2030-01-01T10:00:00+00:00")
    _setting(app, "stipend.amount", "11000")
    _act(admin, students[1]["id"], "paid", paid_ref="UTR-ONE", paid_on="2026-09-01")
    from kts.db import execute
    with app.app_context():
        execute("UPDATE applications SET status = 'withdrawn' WHERE id = ?", (students[2]["id"],))
    _setting(app, "stipend.amount", "12000")
    r = admin.get("/console/stipend/list/1.csv")
    assert r.status_code == 200 and "attachment; filename=KTS5-stipend-due-list1-" in r.headers["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
    from kts.stipend import HEADERS
    assert rows[0] == HEADERS + ["Changed since the list"] and len(rows[0]) == 20
    assert [(row[1], row[14], row[9], row[19]) for row in rows[1:]] == [
        (students[0]["app_no"], "approved", "10000", ""), (students[1]["app_no"], "paid", "10000", "yes"),
        (students[2]["app_no"], "approved", "10000", "no longer selected")]
    assert rows[1][4] == f'="{ACCOUNT}"' and rows[2][15] == "UTR-ONE"
    # no new list; the audit row names the list and what has changed
    assert [(b["id"], b["settled_at"]) for b in _query(app, "SELECT * FROM stipend_batches")] == [(1, None)]
    audit = _query(app, "SELECT detail FROM audit_log WHERE action = 'bank_exported' ORDER BY id")
    assert json.loads(audit[-1]["detail"]) == {"rows": 3, "amount": 30000, "which": "list", "fmt": "csv", "list": 1, "changed": 2}
    assert len(audit) == 2 and json.loads(audit[0]["detail"])["which"] == "due"
    cells, formats = _sheet(admin.get("/console/stipend/list/1.xlsx").data)
    assert cells["T1"] == ("s", "Changed since the list") and cells["T3"] == ("s", "yes") and cells["T4"] == ("s", "no longer selected")
    assert cells.get("T2", ("n", None))[1] in (None, "") and cells["E2"] == ("s", ACCOUNT) and formats["E2"] == "@"
    assert cells["J2"] == ("n", "10000") and cells["J3"] == ("n", "10000") and "B5" not in cells
    # the page offers the download in its table of the lists that wait
    page = admin.get("/console/stipend").get_data(as_text=True)
    assert 'href="/console/stipend/list/1.xlsx"' in page and 'href="/console/stipend/list/1.csv"' in page
    assert "Rs. 10,000 each" in page and "Test admin" in page[page.find("Payment lists not yet marked as paid"):]
    # a HEAD writes nothing; an unknown list or format is nothing; the permission is needed
    head = admin.head("/console/stipend/list/1.csv")
    assert head.status_code == 200 and head.data == b"" and head.headers["Content-Length"] == str(len(r.data))
    assert len(_query(app, "SELECT * FROM audit_log WHERE action = 'bank_exported'")) == 3
    assert admin.get("/console/stipend/list/9.csv").status_code == 404 and admin.get("/console/stipend/list/1.pdf").status_code == 404
    assert _admin(app, "verifier").get("/console/stipend/list/1.csv").status_code == 403
    # an entry that cannot be read is left out and named, as in the export
    _damage(app, students[0]["id"])
    admin.get("/console/stipend")
    rows = list(csv.reader(io.StringIO(admin.get("/console/stipend/list/1.csv").data.decode("utf-8-sig"))))
    assert [row[1] for row in rows[1:]] == [students[1]["app_no"], students[2]["app_no"]]
    flashes = _flashes(admin)
    assert len(flashes) == 1 and students[0]["app_no"] in flashes[0] and "left out" in flashes[0]
    assert json.loads(_query(app, "SELECT detail FROM audit_log WHERE action = 'bank_exported' ORDER BY id DESC")[0]["detail"])["left_out"] == 1
    # 'paid' for the list agrees with the marks: the unchanged entry of a selected student only; the settled list can still be downloaded
    with app.app_context():
        execute("UPDATE bank_details SET account_enc = ? WHERE application_id = ?",
                (_query(app, "SELECT account_enc FROM bank_details WHERE application_id = ?", (students[3]["id"],))[0]["account_enc"], students[0]["id"]))
    _act(admin, students[0]["id"], "return", remark="Send the details again.", not_paid="1")
    assert _status(app, students[0]["id"]) == "returned"
    _pay_list(admin, "BATCH-L", batch=1)
    assert [x["status"] for x in _rows(app)] == ["returned", "paid", "approved", "submitted"]
    assert "0 entries of payment list no. 1" in " ".join(_flashes(admin))
    assert admin.get("/console/stipend/list/1.xlsx").status_code == 200 and _lists(admin) == []


def test_a_payment_list_marked_as_paid_by_two_staff_at_once_is_settled_once(monkeypatch):
    """
    The bank confirms the list and two staff mark it at the same moment. The second request read
    the list before the first settled it: it finds the list settled, leaves its reference and date
    as they are, touches no entry and says so.
    """
    import threading
    import kts.stipend
    app, students, admin = _approved()
    chief = _admin(app, "superadmin")
    _csv(admin)
    assert _lists(admin) == [1]
    real, first = kts.stipend.client_ip, []

    def meanwhile():
        # the first request runs to its end while the second stands between its reading and its writing
        if not first:
            first.append(threading.Thread(target=_pay_list, args=(chief, "REF-FIRST", "2026-09-15", 1)))
            first[0].start()
            first[0].join(15)
        return real()

    monkeypatch.setattr(kts.stipend, "client_ip", meanwhile)
    r = _pay_list(admin, "REF-SECOND", "2026-09-16", batch=1)
    assert r.status_code == 302 and first and not first[0].is_alive()
    assert [(x["status"], x["paid_ref"]) for x in _rows(app)] == [("paid", "REF-FIRST"), ("paid", "REF-FIRST"), ("submitted", "")]
    settled = _query(app, "SELECT * FROM stipend_batches")[0]
    assert settled["settled_at"] and (settled["paid_ref"], settled["paid_on"]) == ("REF-FIRST", "2026-09-15")
    assert "2 entries of payment list no. 1 marked as paid with the reference REF-FIRST" in " ".join(_flashes(chief))
    told = " ".join(_flashes(admin))
    assert "Payment list 1 was marked as paid a moment ago by somebody else. Nothing was done." in told
    assert "check them one by one" not in told and "REF-SECOND" not in told
    # two entries paid once: one audit row and one mail each
    assert len(_query(app, "SELECT * FROM audit_log WHERE action = 'bank_paid'")) == 2
    assert len(_query(app, "SELECT * FROM outbox WHERE subject LIKE '%stipend paid%'")) == 2
    # the same when the other member of staff discarded the list in the meantime
    monkeypatch.setattr(kts.stipend, "client_ip", real)
    _act(admin, students[2]["id"], "approve")
    _csv(admin)
    assert _lists(admin) == [2]
    first.clear()

    def discarded_meanwhile():
        if not first:
            first.append(threading.Thread(target=chief.post, args=("/console/stipend/discard",),
                                          kwargs={"data": {"_csrf": _token(chief), "batch": "2"}}))
            first[0].start()
            first[0].join(15)
        return real()

    monkeypatch.setattr(kts.stipend, "client_ip", discarded_meanwhile)
    _pay_list(admin, "REF-THIRD", batch=2)
    assert "Payment list 2 was discarded a moment ago by somebody else. Nothing was done." in " ".join(_flashes(admin))
    assert _status(app, students[2]["id"]) == "approved"
    assert _query(app, "SELECT paid_ref FROM stipend_batches WHERE id = 2")[0]["paid_ref"] == "discarded"


def test_an_entry_of_a_payment_list_is_not_paid_twice(monkeypatch):
    """Returned after the export, corrected and approved again: paid from the next list only, and only if the bank did not pay it."""
    app, students, admin = _approved()
    aid = students[0]["id"]
    first = _csv(admin)
    assert first[1][1] == students[0]["app_no"] and first[1][4] == f'="{ACCOUNT}"'
    # the page of the entry names its list, and the return asks whether the bank has paid it
    page = admin.get(f"/console/stipend/{aid}").get_data(as_text=True)
    assert "In payment list no. 1" in page and 'name="not_paid"' in page
    # the return, the new entry and the new approval come later than the export (updated_at counts seconds)
    import kts.stipend
    monkeypatch.setattr(kts.stipend, "utcnow", lambda: "2030-01-01T10:00:00+00:00")
    _act(admin, aid, "return", remark="Upload a clearer photo.")
    assert _status(app, aid) == "approved" and "tick the box" in " ".join(_flashes(admin))
    _act(admin, aid, "return", remark="Upload a clearer photo.", not_paid="1")
    assert _status(app, aid) == "returned"
    returned = _query(app, "SELECT detail FROM audit_log WHERE action = 'bank_returned'")[0]["detail"]
    assert "has not paid it from payment list no. 1" in returned and ACCOUNT not in returned
    client = _student(app, students[0])
    assert _form(client, proof=None, account=OTHER_ACCOUNT, account_again=OTHER_ACCOUNT).status_code == 302
    _act(admin, aid, "approve")
    assert _status(app, aid) == "approved"
    assert "In payment list" not in admin.get(f"/console/stipend/{aid}").get_data(as_text=True)
    # 'paid' for list no. 1 leaves the changed entry out and says so; no mail says it was paid
    _pay_list(admin, "BATCH-1", batch=1)
    rows = _rows(app)
    assert rows[0]["status"] == "approved" and rows[1]["status"] == "paid"
    assert "1 entries of the list were changed" in " ".join(_flashes(admin))
    assert not _query(app, "SELECT * FROM outbox WHERE to_addr = ? AND subject LIKE '%stipend paid%'", (students[0]["email"],))
    # the corrected entry goes to the bank once, in the next list; a paid entry enters no list again
    second = _csv(admin)
    assert [r[1] for r in second[1:]] == [students[0]["app_no"]] and second[1][4] == f'="{OTHER_ACCOUNT}"'
    assert _lists(admin) == [2]
    # a return without a list to answer for asks no question
    _act(admin, students[1]["id"], "return", remark="Upload a clearer photo.")
    assert _status(app, students[1]["id"]) == "paid"  # a paid entry is not returned at all
    from kts.db import execute
    with app.app_context():
        execute("UPDATE bank_details SET account_enc = account_enc")
    _pay_list(admin, "BATCH-2", batch=2)
    assert _status(app, aid) == "paid" and _rows(app)[0]["account_last4"] == OTHER_ACCOUNT[-4:]


def test_the_undo_of_a_payment_made_one_by_one_needs_the_confirmation_of_its_list(monkeypatch):
    """Paid one by one while its list is at the bank, the entry stays in that list: the page says so, and the undo asks, as a return does."""
    app, students, admin = _approved()
    aid = students[0]["id"]
    _csv(admin)
    import kts.stipend
    monkeypatch.setattr(kts.stipend, "utcnow", lambda: "2030-01-01T10:00:00+00:00")
    _act(admin, aid, "paid", paid_ref="UTR-TEST-1", paid_on="2026-09-01")
    assert _status(app, aid) == "paid"
    chief = _staff(app)
    page = chief.get(f"/console/stipend/{aid}").get_data(as_text=True)
    assert "In payment list no. 1" in page and "marked as paid already, not through this list" in page
    undo = page[page.find('value="unpaid"') - 900:page.find('value="unpaid"')]
    assert 'name="not_paid"' in undo and "has not paid this entry from payment list no. 1" in undo
    # without the ticked box nothing is done
    monkeypatch.setattr(kts.stipend, "utcnow", lambda: "2030-01-01T10:00:01+00:00")
    _act(chief, aid, "unpaid")
    assert _status(app, aid) == "paid" and "tick the box" in " ".join(_flashes(chief))
    assert not _query(app, "SELECT * FROM audit_log WHERE action = 'bank_unpaid'")
    _act(chief, aid, "unpaid", not_paid="1")
    assert _status(app, aid) == "approved"
    undone = _query(app, "SELECT detail FROM audit_log WHERE action = 'bank_unpaid'")
    assert len(undone) == 1 and "was reference UTR-TEST-1" in undone[0]["detail"]
    assert "the bank has not paid it from payment list no. 1" in undone[0]["detail"] and ACCOUNT not in undone[0]["detail"]
    # the list keeps its number on the page, and a return asks again
    page = admin.get(f"/console/stipend/{aid}").get_data(as_text=True)
    assert "In payment list no. 1" in page and "marked as paid already" not in page and 'name="not_paid"' in page
    _act(admin, aid, "return", remark="Upload a clearer photo.")
    assert _status(app, aid) == "approved" and "payment list no. 1" in " ".join(_flashes(admin))
    _act(admin, aid, "return", remark="Upload a clearer photo.", not_paid="1")
    assert _status(app, aid) == "returned"
    assert "has not paid it from payment list no. 1" in _query(app, "SELECT detail FROM audit_log WHERE action = 'bank_returned'")[0]["detail"]
    # 'paid' for the list leaves the entry out, as before: it has changed since the list went out
    _pay_list(admin, "BATCH-1", batch=1)
    assert _status(app, aid) == "returned" and "1 entries of the list were changed" in " ".join(_flashes(admin))
    # an entry paid one by one and never in a list is undone without a question
    _act(admin, students[2]["id"], "approve")
    _act(admin, students[2]["id"], "paid", paid_ref="UTR-TEST-2", paid_on="2026-09-02")
    page = chief.get(f"/console/stipend/{students[2]['id']}").get_data(as_text=True)
    assert "In payment list" not in page and 'name="not_paid"' not in page
    _act(chief, students[2]["id"], "unpaid")
    assert _status(app, students[2]["id"]) == "approved"


def test_an_action_from_an_older_page_does_nothing():
    """Approve, return, paid and undo act only on the entry as the page showed it."""
    from kts import secure
    from kts.db import execute
    app, students, client = _sent(None)
    aid = students[0]["id"]
    chief, admin = _staff(app), _admin(app)
    page = chief.get(f"/console/stipend/{aid}").get_data(as_text=True)
    seen = re.search(r'name="seen" value="([0-9a-f]{20})"', page).group(1)
    assert page.count(f'name="seen" value="{seen}"') == 2 and ACCOUNT in page
    # returned by another member of staff and sent again with another account, all within a second
    _act(admin, aid, "return", remark="The cheque does not show the name.")
    assert _form(client, proof=None, account=OTHER_ACCOUNT, account_again=OTHER_ACCOUNT).status_code == 302
    # Approve on the older page
    chief.post(f"/console/stipend/{aid}", data={"_csrf": _token(chief), "action": "approve", "seen": seen})
    assert _status(app, aid) == "submitted"
    assert "bank_approved" not in [r["action"] for r in _query(app, "SELECT action FROM audit_log")]
    assert "changed in the meantime" in " ".join(_flashes(chief))
    # without the version of the page nothing is done either
    chief.post(f"/console/stipend/{aid}", data={"_csrf": _token(chief), "action": "approve"})
    assert _status(app, aid) == "submitted"
    # the page as it stands works
    _act(chief, aid, "approve")
    assert _status(app, aid) == "approved"
    # 'paid' from a page that showed the entry before a return, a new entry and a new approval
    older = re.search(r'name="seen" value="([0-9a-f]{20})"', chief.get(f"/console/stipend/{aid}").get_data(as_text=True)).group(1)
    _act(admin, aid, "return", remark="Upload the passbook.")
    assert _form(client, proof=None).status_code == 302
    _act(chief, aid, "approve")
    chief.post(f"/console/stipend/{aid}", data={"_csrf": _token(chief), "action": "paid", "seen": older,
                                                "paid_ref": "REF-TEST-A", "paid_on": "2026-09-01"})
    assert _status(app, aid) == "approved" and _rows(app)[0]["paid_ref"] == ""
    # a payment undone on an older page stays paid
    _act(chief, aid, "paid", paid_ref="REF-TEST-B", paid_on="2026-09-02")
    with app.app_context():
        execute("UPDATE bank_details SET updated_at = '2026-09-02T10:00:00+00:00'")
    older = re.search(r'name="seen" value="([0-9a-f]{20})"', chief.get(f"/console/stipend/{aid}").get_data(as_text=True)).group(1)
    _act(chief, aid, "unpaid")
    _act(chief, aid, "paid", paid_ref="REF-TEST-C", paid_on="2026-09-03")
    chief.post(f"/console/stipend/{aid}", data={"_csrf": _token(chief), "action": "unpaid", "seen": older})
    row = _rows(app)[0]
    assert row["status"] == "paid" and row["paid_ref"] == "REF-TEST-C"
    with app.app_context():
        assert secure.unseal(row["account_enc"]) == ACCOUNT
    # the version says nothing about the numbers
    assert ACCOUNT not in seen and OTHER_ACCOUNT not in seen and ACCOUNT not in older


def test_one_account_is_approved_for_one_application_only():
    app, students = _site(n=3)
    _sent(app, students)
    other = _student(app, students[1])
    assert _form(other, holder_name="Campus Student 2", account="0" + ACCOUNT, account_again="0" + ACCOUNT).status_code == 302
    admin = _admin(app)
    one, two = students[0]["id"], students[1]["id"]
    _act(admin, one, "approve")
    _act(admin, two, "approve")
    assert [x["status"] for x in _rows(app)] == ["approved", "submitted"]
    assert "one of the two can be approved, not both" in " ".join(_flashes(admin))
    assert not _query(app, "SELECT * FROM audit_log WHERE action = 'bank_approved' AND entity_id = ?", (two,))
    assert len(_query(app, "SELECT * FROM outbox WHERE subject LIKE '%approved%'")) == 1
    # still refused while the other is paid
    _act(admin, one, "paid", paid_ref="UTR-TEST-5", paid_on="2026-09-15")
    _act(admin, two, "approve")
    assert [x["status"] for x in _rows(app)] == ["paid", "submitted"]
    # a superadmin takes 'paid' back, the staff return the first: now the second may be approved
    chief = _staff(app)
    _act(chief, one, "unpaid")
    _act(admin, one, "return", remark="The account is not yours.")
    _act(admin, two, "approve")
    assert [x["status"] for x in _rows(app)] == ["returned", "approved"]
    # the first, sent again with the same account, cannot be approved beside it
    client = _student(app, students[0])
    assert _form(client, holder_name=students[0]["name"]).status_code == 302
    _act(admin, one, "approve")
    assert [x["status"] for x in _rows(app)] == ["submitted", "approved"]
    # another account is not held up
    third = _student(app, students[2])
    assert _form(third, holder_name="Campus Student 3", account=OTHER_ACCOUNT, account_again=OTHER_ACCOUNT).status_code == 302
    _act(admin, students[2]["id"], "approve")
    assert _status(app, students[2]["id"]) == "approved"


def test_another_key_is_refused_while_entries_exist(monkeypatch):
    """The key is bound to the stored entries: the file, then another key in the setting, or another key file."""
    monkeypatch.delenv("KTS_STIPEND_KEY", raising=False)
    app, students = _site(n=3)
    _sent(app, students)
    key = Path(app.config["INSTANCE_DIR"]) / "stipend.key"
    admin = _admin(app)
    _act(admin, students[0]["id"], "approve")
    other = _student(app, students[1])
    # another key in the setting: nothing is stored, no proof is kept, the form says so
    monkeypatch.setenv("KTS_STIPEND_KEY", "3c" * 64)
    r = _form(other, holder_name="Campus Student 2")
    assert r.status_code == 503 and _text("bank.err_store") in r.get_data(as_text=True)
    assert len(_rows(app)) == 1 and len(_proofs(app)) == 1
    # the same key written as hex in the setting is accepted, and the account given twice is marked
    monkeypatch.setenv("KTS_STIPEND_KEY", key.read_bytes().hex())
    assert _form(other, holder_name="Campus Student 2").status_code == 302
    rows = _rows(app)
    assert len(rows) == 2 and rows[0]["account_hash"] == rows[1]["account_hash"]
    assert admin.get("/console/stipend").get_data(as_text=True).count("⚠ same account") == 2
    # a key file of another installation is refused as well; the file of before opens everything again
    monkeypatch.delenv("KTS_STIPEND_KEY")
    saved = key.read_bytes()
    key.write_bytes(bytes.fromhex("1f" * 64))
    third = _student(app, students[2])
    r = _form(third, holder_name="Campus Student 3", account=OTHER_ACCOUNT, account_again=OTHER_ACCOUNT)
    assert r.status_code == 503 and len(_rows(app)) == 2 and len(_proofs(app)) == 2
    key.write_bytes(saved)
    assert _form(third, holder_name="Campus Student 3", account=OTHER_ACCOUNT, account_again=OTHER_ACCOUNT).status_code == 302
    assert len(_rows(app)) == 3 and len(_csv(admin, "all")) == 2


def test_a_damaged_newest_entry_does_not_stop_the_form(monkeypatch, caplog):
    """One damaged row is no reason to refuse every entry: the key is tried against the newest few, and the log names what it found."""
    import logging
    from kts import secure
    monkeypatch.delenv("KTS_STIPEND_KEY", raising=False)
    app, students = _site(n=4)
    caplog.set_level(logging.ERROR, logger=app.logger.name)
    _sent(app, students)
    two = _student(app, students[1])
    assert _form(two, holder_name="Campus Student 2", account=OTHER_ACCOUNT, account_again=OTHER_ACCOUNT).status_code == 302
    _damage(app, students[1]["id"])
    # a new entry is stored all the same, sealed with the key in use; nothing is logged
    third = _student(app, students[2])
    assert _form(third, holder_name="Campus Student 3", account=THIRD_ACCOUNT, account_again=THIRD_ACCOUNT).status_code == 302
    assert len(_rows(app)) == 3 and _logged_errors(caplog) == []
    # the damaged entry is cleared through the form: returned by the staff, sent again by the student
    admin = _admin(app)
    _act(admin, students[1]["id"], "return", remark="Please send the details again.")
    assert _form(two, holder_name="Campus Student 2", account=OTHER_ACCOUNT, account_again=OTHER_ACCOUNT).status_code == 302
    with app.app_context():
        assert [secure.unseal(r["account_enc"]) for r in _rows(app)] == [ACCOUNT, OTHER_ACCOUNT, THIRD_ACCOUNT]
    # another key opens none of them: refused as before, and the log blames the key
    monkeypatch.setenv("KTS_STIPEND_KEY", "3c" * 64)
    fourth = _student(app, students[3])
    assert _form(fourth, holder_name="Campus Student 4", account=THIRD_ACCOUNT, account_again=THIRD_ACCOUNT).status_code == 503
    logged = _logged_errors(caplog)
    assert len(logged) == 1 and "Put back the key" in logged[0]
    assert all(s["app_no"] in logged[0] for s in students[:3]) and students[3]["app_no"] not in logged[0]
    monkeypatch.delenv("KTS_STIPEND_KEY")
    caplog.clear()
    # when every entry tried is damaged, nothing tells a damaged row from another key: the key is blamed
    for s in students[:3]:
        _damage(app, s["id"])
    r = _form(fourth, holder_name="Campus Student 4", account=THIRD_ACCOUNT, account_again=THIRD_ACCOUNT)
    assert r.status_code == 503 and len(_rows(app)) == 3 and len(_proofs(app)) == 3
    logged = _logged_errors(caplog)
    assert len(logged) == 1 and "Put back the key" in logged[0] and "applications KTS5-" in logged[0]
    assert ACCOUNT not in caplog.text and OTHER_ACCOUNT not in caplog.text and THIRD_ACCOUNT not in caplog.text


def test_a_single_damaged_entry_is_named_in_the_log_instead_of_the_key(caplog):
    """With one entry stored and that one damaged, the log names its application number, not the key."""
    import logging
    app, students, _client = _sent(None)
    caplog.set_level(logging.ERROR, logger=app.logger.name)
    _damage(app, students[0]["id"])
    r = _form(_student(app, students[1]), holder_name="Campus Student 2", account=OTHER_ACCOUNT, account_again=OTHER_ACCOUNT)
    assert r.status_code == 503 and _text("bank.err_store") in r.get_data(as_text=True)
    assert len(_rows(app)) == 1 and len(_proofs(app)) == 1
    logged = _logged_errors(caplog)
    assert len(logged) == 1
    message = logged[0]
    assert students[0]["app_no"] in message and "damaged" in message and "return that entry" in message
    assert "Put back the key" not in message and ACCOUNT not in message
    # returned and sent again, the damaged entry is replaced (it is no witness for the key while it
    # is being sent again), and the form is open to everybody again
    _act(_admin(app), students[0]["id"], "return", remark="Please send the details again.")
    assert _form(_client).status_code == 302
    assert _form(_student(app, students[1]), holder_name="Campus Student 2", account=OTHER_ACCOUNT, account_again=OTHER_ACCOUNT).status_code == 302
    assert len(_rows(app)) == 2


def test_setting_a_then_setting_b_is_refused(monkeypatch):
    monkeypatch.setenv("KTS_STIPEND_KEY", "5a" * 64)
    app, students = _site()
    assert _form(_student(app, students[0])).status_code == 302
    monkeypatch.setenv("KTS_STIPEND_KEY", "3c" * 64)
    r = _form(_student(app, students[1]), holder_name="Campus Student 2")
    assert r.status_code == 503 and len(_rows(app)) == 1 and len(_proofs(app)) == 1
    # a key file left by a refused first submission, with no entry behind it, stops nothing
    monkeypatch.delenv("KTS_STIPEND_KEY")
    app, students = _site()
    first = _student(app, students[0])
    assert _form(first, proof=("cheque.exe", b"MZ not a proof")).status_code == 400
    assert (Path(app.config["INSTANCE_DIR"]) / "stipend.key").is_file()
    monkeypatch.setenv("KTS_STIPEND_KEY", "3c" * 64)
    assert _form(first).status_code == 302 and len(_rows(app)) == 1


def test_a_failed_write_of_the_key_file_leaves_nothing_behind(monkeypatch):
    """The first key cannot be written (a full disk): no stipend.key of 0 bytes stops the form afterwards."""
    from kts import secure
    app, students = _site()
    key = Path(app.config["INSTANCE_DIR"]) / "stipend.key"
    real = os.fdopen

    class Failing:
        def __init__(self, fh):
            self.fh = fh

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.fh.close()

        def write(self, data):
            raise OSError(28, "No space left on device")

    monkeypatch.setattr(secure.os, "fdopen", lambda handle, mode="r", *a, **k: Failing(real(handle, mode, *a, **k)))
    client = _student(app, students[0])
    assert _form(client).status_code == 503
    monkeypatch.setattr(secure.os, "fdopen", real)
    assert not key.exists() and not list(key.parent.glob("stipend.key*"))
    assert _rows(app) == [] and _proofs(app) == []
    assert _form(client).status_code == 302 and len(_rows(app)) == 1 and len(key.read_bytes()) == 64


def test_a_payment_stays_in_the_record_when_the_student_leaves_the_list():
    app, students, admin = _approved()
    _pay_list(admin, "BATCH-TEST-10")
    # the first student is withdrawn after the payment, on the page of the application
    verifier = _admin(app, role="verifier")
    aid = students[0]["id"]
    r = verifier.post(f"/console/applications/{aid}", data={"_csrf": _token(verifier), "action": "withdraw", "remarks": "Left"})
    assert r.status_code == 302 and _status(app, aid) == "paid"
    for which, count in (("paid", 2), ("all", 2), ("due", 0)):
        rows = _csv(admin, which)
        assert len(rows) == count + 1, which
        assert (students[0]["app_no"] in str(rows)) == (which != "due"), which
    page = admin.get("/console/stipend").get_data(as_text=True)
    assert "never paid" not in page and "Of these, 1 was paid before" in page
    assert "and 1 paid to students no longer selected" in page
    page = admin.get(f"/console/stipend/{aid}").get_data(as_text=True)
    assert "Nothing is approved or paid" not in page and "The stipend was paid on" in page and "BATCH-TEST-10" in page


def test_a_paid_student_who_leaves_the_list_still_sees_the_payment():
    app, students, admin = _approved()
    _pay_list(admin, "BATCH-TEST-11")
    # the first student is withdrawn, the second waitlisted by a selection run again; the third has only sent
    from kts.db import execute
    with app.app_context():
        for s, status in zip(students, ("withdrawn", "waitlisted", "withdrawn")):
            execute("UPDATE applications SET status = ? WHERE id = ?", (status, s["id"]))
    for s in students[:2]:
        client = _student(app, s)
        page = client.get("/candidate/bank").get_data(as_text=True)
        assert "BATCH-TEST-11" in page and _text("bank.paid_text") in page and _text("bank.only_selected") not in page
        assert 'name="account"' not in page and "XXXXXX" in page
        home = client.get("/candidate/").get_data(as_text=True)
        assert 'id="bank-card"' in home and _text("bank.st_paid") in home
        # nothing can be sent from it
        assert _form(client).status_code == 302 and _status(app, s["id"]) == "paid"
    # the same when the merit list is taken off
    _setting(app, "merit.published", "0")
    assert "BATCH-TEST-11" in _student(app, students[0]).get("/candidate/bank").get_data(as_text=True)
    _setting(app, "merit.published", "1")
    # an entry that is not paid stays hidden once the student has left the list
    client = _student(app, students[2])
    assert _text("bank.only_selected") in client.get("/candidate/bank").get_data(as_text=True)
    assert 'id="bank-card"' not in client.get("/candidate/").get_data(as_text=True)


def test_the_amount_paid_is_kept():
    app, students, admin = _approved(n=4)
    _act(admin, students[0]["id"], "paid", paid_ref="REF-ONE", paid_on="2026-09-15")
    _pay_list(admin, "BATCH-1", on="2026-09-16")
    assert [x["paid_amount"] for x in _rows(app)] == [10000, 10000, None, None]
    # the setting changes afterwards; the third entry is approved at the new rate
    _setting(app, "stipend.amount", "12000")
    _act(admin, students[2]["id"], "approve")
    cells, _styles = _sheet(admin.get("/console/stipend/export.xlsx?which=paid").data)
    assert cells["J2"] == ("n", "10000") and cells["J3"] == ("n", "10000")
    cells, _styles = _sheet(admin.get("/console/stipend/export.xlsx").data)
    assert cells["J2"] == ("n", "12000") and "J3" not in cells
    rows = _csv(admin, "all")
    assert [(row[14], row[9]) for row in rows[1:]] == [("paid", "10000"), ("paid", "10000"), ("approved", "12000")]
    assert '"amount": 32000' in _query(app, "SELECT detail FROM audit_log WHERE action = 'bank_exported' ORDER BY id DESC")[0]["detail"]
    for s in students[:2]:
        assert "Rs. 10,000" in admin.get(f"/console/stipend/{s['id']}").get_data(as_text=True)
    # undone, and paid again at the new rate
    chief = _staff(app)
    _act(chief, students[0]["id"], "unpaid")
    assert _rows(app)[0]["paid_amount"] is None
    _act(admin, students[0]["id"], "paid", paid_ref="REF-TWO", paid_on="2026-09-20")
    assert _rows(app)[0]["paid_amount"] == 12000
    assert "Rs. 12,000" in _query(app, "SELECT body FROM outbox ORDER BY id DESC LIMIT 1")[0]["body"]


def test_a_payment_list_is_paid_at_the_sum_of_its_file():
    """The setting changes after the list went to the bank: the bank paid what the file said, and so does the record."""
    app, students, admin = _approved()
    assert [row[9] for row in _csv(admin)[1:]] == ["10000", "10000"]
    assert _query(app, "SELECT amount FROM stipend_batches")[0]["amount"] == 10000
    _setting(app, "stipend.amount", "12000")
    # the page still says what the list went out with; a new list takes the new sum
    _act(admin, students[2]["id"], "approve")
    _csv(admin)
    page = admin.get("/console/stipend").get_data(as_text=True)
    assert "No. 1 · " in page and "No. 2 · " in page
    assert re.search(r'value="1">No\. 1 · [^<]* · Rs\. 10,000 each<', page) and re.search(r'value="2">No\. 2 · [^<]* · Rs\. 12,000 each<', page)
    _pay_list(admin, "BATCH-RAISE", batch=1)
    assert [x["paid_amount"] for x in _rows(app)] == [10000, 10000, None]
    mails = _query(app, "SELECT body FROM outbox WHERE subject LIKE '%stipend paid%'")
    assert len(mails) == 2 and all("Rs. 10,000" in m["body"] and "12,000" not in m["body"] for m in mails)
    assert [row[9] for row in _csv(admin, "paid")[1:]] == ["10000", "10000"]
    for s in students[:2]:
        assert "Rs. 10,000" in admin.get(f"/console/stipend/{s['id']}").get_data(as_text=True)
    # a list made before the sum was kept with it is paid at the setting of the day
    from kts.db import execute
    with app.app_context():
        execute("UPDATE stipend_batches SET amount = NULL WHERE id = 2")
    assert re.search(r'value="2">No\. 2 · [^<]* · Rs\. 12,000 each<', admin.get("/console/stipend").get_data(as_text=True))
    _pay_list(admin, "BATCH-OLD", batch=2)
    assert _rows(app)[2]["paid_amount"] == 12000


def test_a_payment_made_one_by_one_takes_the_sum_of_the_list_at_the_bank():
    """The file at the bank says what an entry of it was paid; an entry in no list takes the setting of the day."""
    app, students, admin = _approved()
    _csv(admin)
    _setting(app, "stipend.amount", "12000")
    _act(admin, students[0]["id"], "paid", paid_ref="UTR-LISTED", paid_on="2026-09-01")
    _act(admin, students[2]["id"], "approve")
    _act(admin, students[2]["id"], "paid", paid_ref="UTR-ALONE", paid_on="2026-09-01")
    assert [x["paid_amount"] for x in _rows(app)] == [10000, None, 12000]
    mails = _query(app, "SELECT body FROM outbox WHERE subject LIKE '%stipend paid%' ORDER BY id")
    assert len(mails) == 2 and "Rs. 10,000" in mails[0]["body"] and "Rs. 12,000" in mails[1]["body"]
    assert "Rs. 10,000" in admin.get(f"/console/stipend/{students[0]['id']}").get_data(as_text=True)
    # once its list is discarded, an entry takes the setting like any other
    assert admin.post("/console/stipend/discard", data={"_csrf": _token(admin), "batch": 1}).status_code == 302
    _act(admin, students[1]["id"], "paid", paid_ref="UTR-AFTER", paid_on="2026-09-01")
    assert _rows(app)[1]["paid_amount"] == 12000


def test_the_reference_of_a_list_holds_no_number_of_an_entry_that_is_left_out():
    """The reference is mailed to every student paid: the number of a returned entry of the same list does not go into it."""
    app, students, admin = _approved()
    _csv(admin)
    _act(admin, students[1]["id"], "return", remark="Upload a clearer photo.", not_paid="1")
    assert _status(app, students[1]["id"]) == "returned"
    other = _rows(app)[1]["account_last4"]
    assert other == "0001"
    r = _pay_list(admin, "NEFT 555-0010-0001", batch=1)
    assert r.status_code == 302 and "Do not write an account or Aadhaar number" in " ".join(_flashes(admin))
    assert _status(app, students[0]["id"]) == "approved" and _lists(admin) == [1]
    assert not _query(app, "SELECT * FROM audit_log WHERE action = 'bank_paid'")
    _pay_list(admin, "NEFT-OK-1", batch=1)
    assert _status(app, students[0]["id"]) == "paid" and _lists(admin) == []


def test_an_entry_paid_by_an_earlier_list_is_not_called_paid_one_by_one():
    """Two downloads hold the same entry; the first list is paid: the page names the second without saying how the entry was paid."""
    app, students, admin = _approved()
    _csv(admin)
    _csv(admin)
    assert _lists(admin) == [2, 1]
    _pay_list(admin, "BATCH-FIRST", batch=1)
    page = _staff(app).get(f"/console/stipend/{students[0]['id']}").get_data(as_text=True)
    assert "In payment list no. 2" in page and "marked as paid already, not through this list" in page
    assert "paid one by one" not in page


def _damage(app, aid):
    """One character of the seal changed: the entry cannot be read any more."""
    from kts.db import execute, query
    with app.app_context():
        enc = query("SELECT account_enc FROM bank_details WHERE application_id = ?", (aid,), one=True)["account_enc"]
        execute("UPDATE bank_details SET account_enc = ? WHERE application_id = ?",
                (enc[:10] + ("A" if enc[10] != "A" else "B") + enc[11:], aid))


def test_an_unreadable_entry_is_left_out_of_the_export_and_named():
    app, students, admin = _approved(4)
    _act(admin, students[2]["id"], "approve")
    _damage(app, students[1]["id"])
    admin.get("/console/stipend")
    r = admin.get("/console/stipend/export.xlsx")
    assert r.status_code == 200
    cells, _styles = _sheet(r.data)
    # two rows, numbered 1 and 2 without a gap, the unreadable one not among them
    assert cells["A2"] == ("n", "1") and cells["A3"] == ("n", "2") and "B4" not in cells
    assert cells["E2"] == ("s", ACCOUNT) and students[1]["app_no"] not in str(cells)
    flashes = _flashes(admin)
    assert len(flashes) == 1 and students[1]["app_no"] in flashes[0] and "left out" in flashes[0]
    detail = json.loads(_query(app, "SELECT detail FROM audit_log WHERE action = 'bank_exported'")[0]["detail"])
    assert detail == {"rows": 2, "amount": 20000, "which": "due", "fmt": "xlsx", "aadhaar": False, "list": 1, "left_out": 1}
    # the payment of the list agrees with the list: the same two entries
    _pay_list(admin, "BATCH-TEST-2", batch=1)
    assert [x["status"] for x in _rows(app)] == ["paid", "approved", "paid", "submitted"]
    # a damaged paid entry does not block the record of the payments either
    _damage(app, students[0]["id"])
    admin.get("/console/stipend")
    r = admin.get("/console/stipend/export.xlsx?which=paid")
    cells, _styles = _sheet(r.data)
    assert r.status_code == 200 and cells["B2"] == ("s", students[2]["app_no"]) and "B3" not in cells
    assert students[0]["app_no"] in _flashes(admin)[0]


def test_the_list_of_the_students_who_have_not_submitted():
    app, students = _site(n=5)
    _sent(app, students)
    admin = _admin(app)
    page = admin.get("/console/stipend?state=none").get_data(as_text=True)
    assert "export.csv?which=none" in page and "export.xlsx?which=none" in page
    assert "which=none" not in admin.get("/console/stipend").get_data(as_text=True)
    r = admin.get("/console/stipend/export.csv?which=none")
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
    assert rows[0] == ["S. No.", "Application No", "Student's name", "College", "State", "E-mail", "Mobile"]
    assert [row[1] for row in rows[1:]] == [s["app_no"] for s in students[1:]]
    assert [row[5] for row in rows[1:]] == [s["email"] for s in students[1:]]
    assert [row[6] for row in rows[1:]] == [f"98765{n:05d}" for n in range(2, 6)]
    text = r.get_data(as_text=True)
    assert ACCOUNT not in text and ACCOUNT[-4:] not in text and IFSC not in text
    x = admin.get("/console/stipend/export.xlsx?which=none&aadhaar=1")
    cells, _styles = _sheet(x.data)
    assert x.status_code == 200 and cells["G2"] == ("s", "9876500002") and "H1" not in cells
    audit = _query(app, "SELECT detail FROM audit_log WHERE action = 'bank_exported' ORDER BY id")
    assert [a["detail"] for a in audit] == ['{"rows": 4, "which": "none", "fmt": "csv", "aadhaar": false}',
                                           '{"rows": 4, "which": "none", "fmt": "xlsx", "aadhaar": false}']
    assert _query(app, "SELECT * FROM stipend_batches") == []
    for role in ("verifier", "content", "viewer"):
        assert _admin(app, role).get("/console/stipend/export.csv?which=none").status_code == 403


def test_every_opening_of_the_proof_is_written_down():
    app, students, _client = _sent(None)
    name = _rows(app)[0]["proof_path"]
    admin = _admin(app)
    # a request for a part of the file gets the whole file, and a row like any other
    for headers in ({}, {"Range": "bytes=0-"}, {"Range": "bytes=1-"}, {"Range": "bytes=1-", "If-Range": '"old"'}):
        r = admin.get(f"/console/files/{name}", headers=headers)
        assert r.status_code == 200 and r.data == PDF and "Accept-Ranges" not in r.headers, headers
        r.close()
    opened = _query(app, "SELECT entity_id FROM audit_log WHERE action = 'bank_proof_opened'")
    assert len(opened) == 4 and all(o["entity_id"] == students[0]["id"] for o in opened)
    # only the name the entry keeps is served: what Windows would open as the same file is refused, without a row
    folder, file = name.split("/")
    for variant in (f"{name}.", f"{name}%20", f"{name}..", f"{folder}/{file.upper()}", f"{name}::$DATA"):
        assert _answer(admin, f"/console/files/{variant}") == 404, variant
    assert len(_query(app, "SELECT id FROM audit_log WHERE action = 'bank_proof_opened'")) == 4


def test_a_proof_named_in_another_script_or_as_jfif_is_accepted():
    from kts.utils import limiter
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\0" * 300 + b"\xff\xd9"
    for name, body, stored, kept in (("காசோலை.pdf", PDF, ".pdf", "file.pdf"), ("पासबुक.jpg", jpeg, ".jpg", "file.jpg"),
                                     ("பாஸ்புக்.PNG", PNG, ".png", "file.png"), ("passbook.jfif", jpeg, ".jpg", "passbook.jfif"),
                                     ("photo.PJPEG", jpeg, ".jpg", "photo.PJPEG"), ("scan 1.pdf", PDF, ".pdf", "scan_1.pdf"),
                                     # a name in another script and one of the other names of a JPEG, together
                                     ("புகைப்படம்.jfif", jpeg, ".jpg", "file.jfif"), ("புகைப்படம்.JFIF", jpeg, ".jpg", "file.jfif"),
                                     ("तस्वीर.pjp", jpeg, ".jpg", "file.pjp")):
        # the limit of submissions counts every fresh application here as one: more cases than it allows
        limiter._hits.clear()
        app, students = _site(n=1)
        r = _form(_student(app, students[0]), proof=(name, body))
        assert r.status_code == 302, (name, _errors(r.get_data(as_text=True)))
        row = _rows(app)[0]
        assert row["proof_path"].endswith(stored) and row["proof_name"] == kept, name
        f = _staff(app).get("/console/files/" + row["proof_path"])
        assert f.status_code == 200 and f.data == body, name
        f.close()
    # the content still decides: PNG bytes under another name are refused, and so is a name without a type
    for name, body in (("காசோலை.pdf", PNG), ("passbook.jfif", PNG), ("புகைப்படம்.jfif", PNG), ("காசோலை", PDF),
                       ("காசோலை.gif", b"GIF89a" + b"\0" * 50)):
        limiter._hits.clear()
        app, students = _site(n=1)
        r = _form(_student(app, students[0]), proof=(name, body))
        assert r.status_code == 400 and _rows(app) == [] and _proofs(app) == [], name
        assert _text("reg.err_idproof") in _errors(r.get_data(as_text=True))


def test_the_rows_of_the_bank_details_are_for_the_permission_only():
    app, students, _client = _sent(None)
    aid = students[0]["id"]
    admin = _admin(app)
    admin.get(f"/console/stipend/{aid}")
    _act(admin, aid, "approve")
    _act(admin, aid, "paid", paid_ref="UTR-TEST-0001", paid_on="2026-09-15")
    marks = ("bank_", "ending in 0987", "UTR-TEST-0001")
    page = admin.get(f"/console/applications/{aid}").get_data(as_text=True)
    assert all(m in page for m in marks) and "bank_approved" in page
    # the looks at the full numbers stand on the stipend page only
    assert "bank_viewed" not in page
    assert all(m in admin.get("/console/").get_data(as_text=True) for m in marks)
    for role in ("verifier", "viewer", "content"):
        client = _admin(app, role)
        pages = [client.get("/console/").get_data(as_text=True)]
        if role != "content":
            pages.append(client.get(f"/console/applications/{aid}").get_data(as_text=True))
        for page in pages:
            assert page and not any(m in page for m in marks), role


def test_the_number_without_its_zeros_is_refused_too():
    app, students, _client = _sent(None)
    aid = students[0]["id"]
    admin = _admin(app)
    short = ACCOUNT.lstrip("0")
    before = len(_query(app, "SELECT * FROM outbox"))
    for remark in (f"Account {short} does not match the cheque", f"Account 0{short} is wrong",
                   f"Account {short[:5]} {short[5:]} is wrong", f"Account {short[:3]}-{short[3:]} is wrong"):
        _act(admin, aid, "return", remark=remark)
        assert _status(app, aid) == "submitted", remark
    assert len(_query(app, "SELECT * FROM outbox")) == before
    _act(admin, aid, "approve")
    _act(admin, aid, "paid", paid_ref=f"NEFT {short}", paid_on="2026-09-01")
    assert _status(app, aid) == "approved"
    _pay_list(admin, f"B {short}")
    assert _status(app, aid) == "approved"
    # the last four digits, and other numbers, are still allowed
    _act(admin, aid, "return", remark=f"The account ending in {ACCOUNT[-4:]} is not on cheque 123456.", not_paid="1")
    assert _status(app, aid) == "returned"


def test_the_number_with_marks_between_its_digits_is_refused_too():
    """Statements and passbooks print long numbers in groups: dots, slashes, commas or underscores between them."""
    app, students, _client = _sent(None)
    aid = students[0]["id"]
    admin = _admin(app)
    short = ACCOUNT.lstrip("0")
    before = len(_query(app, "SELECT * FROM outbox"))
    for remark in (f"The number {ACCOUNT[:3]}.{ACCOUNT[3:6]}.{ACCOUNT[6:]} is not on the cheque",
                   f"The number {ACCOUNT[:6]}/{ACCOUNT[6:]} is wrong", f"The number {ACCOUNT[:6]},{ACCOUNT[6:]} is wrong",
                   f"The number {ACCOUNT[:6]}_{ACCOUNT[6:]} is wrong", f"The number {short[:3]}.{short[3:6]}.{short[6:]} is wrong",
                   f"The number {ACCOUNT[:4]} - {ACCOUNT[4:8]} / {ACCOUNT[8:]} is wrong", f"See ({short[:3]}) {short[3:]}.",
                   f"Aadhaar {AADHAAR[:4]}.{AADHAAR[4:8]}.{AADHAAR[8:]} is not readable"):
        _act(admin, aid, "return", remark=remark)
        assert _status(app, aid) == "submitted", remark
    assert len(_query(app, "SELECT * FROM outbox")) == before
    _act(admin, aid, "approve")
    _act(admin, aid, "paid", paid_ref=f"NEFT {short[:3]}.{short[3:6]}.{short[6:]}", paid_on="2026-09-01")
    assert _status(app, aid) == "approved"
    _pay_list(admin, f"B {ACCOUNT[:6]}/{ACCOUNT[6:]}")
    assert _status(app, aid) == "approved"
    # dates, sums, cheque numbers and codes with letters in them are still allowed
    _act(admin, aid, "return", not_paid="1",
         remark=f"Rs. 10,000.00 was returned on 01/09/2026 (cheque 987/65); IFSC {IFSC} shows branch 50987, not {ACCOUNT[-4:]}.")
    assert _status(app, aid) == "returned"


def test_the_history_keeps_the_changes_of_state_after_many_looks():
    app, students, client = _sent(None)
    aid = students[0]["id"]
    admin = _admin(app)
    _act(admin, aid, "approve")
    _act(admin, aid, "return", remark="Upload the passbook of your own account.")
    assert _form(client, proof=None).status_code == 302
    _act(admin, aid, "approve")
    proof = _rows(app)[0]["proof_path"]
    for _ in range(30):
        admin.get(f"/console/stipend/{aid}")
        admin.get(f"/console/files/{proof}").close()
    page = admin.get(f"/console/stipend/{aid}").get_data(as_text=True)
    shown = re.findall(r"<code>(bank_[a-z_]+)</code>", page[page.find("<h3>History</h3>"):])
    assert shown.count("bank_approved") == 2 and shown.count("bank_returned") == 1 and shown.count("bank_submitted") == 2
    # the looks are counted, and the last ten stand below the changes of state
    assert "Opened by the staff: 61 (the last 10 below)" in page
    assert shown.count("bank_viewed") + shown.count("bank_proof_opened") == 10
    # the page of the application keeps the trail as well
    page = admin.get(f"/console/applications/{aid}").get_data(as_text=True)
    assert "bank_approved" in page and "bank_returned" in page and "bank_viewed" not in page


def test_the_card_says_what_the_state_means():
    app, students, client = _sent(None)
    aid = students[0]["id"]
    admin = _admin(app)

    def card(c):
        page = c.get("/candidate/").get_data(as_text=True)
        start = page.find('id="bank-card"')
        return page[start:page.find('href="/candidate/bank"', start)]

    assert _text("bank.submitted_text") in card(client) and _text("bank.card_text") not in card(client)
    _act(admin, aid, "approve")
    assert _text("bank.approved_text") in card(client)
    _act(admin, aid, "paid", paid_ref="UTR-TEST-6", paid_on="2026-09-15")
    assert _text("bank.paid_text") in card(client) and _text("bank.card_text") not in card(client)
    # a student without an entry, before the form opens and after it is closed
    other = _student(app, students[1])
    assert _text("bank.card_text") in card(other) and _text("bank.not_open") not in card(other)
    _setting(app, "stipend.open", "0")
    assert _text("bank.card_text") in card(other) and _text("bank.not_open") in card(other)


def test_the_inputs_leave_room_for_the_spaces_the_server_removes():
    app, students = _site(n=4)
    page = _student(app, students[0]).get("/candidate/bank").get_data(as_text=True)
    for field, least in (("ifsc", len("TEST 0AB1234")), ("account", 20), ("account_again", 20)):
        tag = re.search(rf'<input[^>]*name="{field}"[^>]*>', page).group(0)
        assert int(re.search(r'maxlength="(\d+)"', tag).group(1)) >= least, tag
    for n, value in enumerate((" TEST0AB1234", "TEST0AB1234 ", "test 0ab 1234", "TEST 0AB1234")):
        assert _form(_student(app, students[n]), holder_name=students[n]["name"], ifsc=value).status_code == 302, value
        assert _rows(app)[n]["ifsc"] == IFSC


def test_the_messages_are_tied_to_their_fields():
    app, students = _site(n=1)
    client = _student(app, students[0])
    r = _form(client, ifsc="BAD", account_again="1", aadhaar=_wrong(AADHAAR), account_type=None, declare_own=None, proof=None)
    assert r.status_code == 400
    page = r.get_data(as_text=True)
    ids = re.findall(r' id="([^"]+)"', page)
    assert len(ids) == len(set(ids))
    refs = set(re.findall(r'aria-(?:describedby|labelledby)="([^"]+)"', page))
    assert refs <= set(ids)
    errs = re.findall(r'<span class="err" id="([^"]+)"', page)
    assert sorted(errs) == ["aadhaar-err", "account_again-err", "account_type-err", "declare-err", "ifsc-err", "proof-err"]
    assert set(errs) <= refs
    for name in ("ifsc", "account_again", "aadhaar", "proof"):
        tag = re.search(rf'<input[^>]*name="{name}"[^>]*>', page).group(0)
        assert 'aria-invalid="true"' in tag and f'aria-describedby="{name}-err"' in tag, tag
    assert 'role="radiogroup" aria-labelledby="account_type-label"' in page and page.count('aria-describedby="declare-err"') == 3
    # without an error nothing is marked
    ok = client.get("/candidate/bank").get_data(as_text=True)
    assert "aria-invalid" not in ok and "aria-describedby" not in ok and 'role="radiogroup"' in ok


# ---- nothing in full where it does not belong -----------------------------------------------

def test_no_full_number_in_mails_audit_or_messages():
    app, students, client = _sent(None)
    aid = students[0]["id"]
    admin = _admin(app)
    _act(admin, aid, "return", remark="Upload the passbook.")
    assert _form(client, proof=None).status_code == 302
    _act(admin, aid, "approve")
    admin.get("/console/stipend/export.xlsx?aadhaar=1")
    _act(admin, aid, "paid", paid_ref="UTR-TEST-3", paid_on="2026-09-10")
    rows = _query(app, "SELECT * FROM audit_log") + _query(app, "SELECT * FROM outbox")
    flashes = []
    for c in (admin, client):
        with c.session_transaction() as s:
            flashes += [str(m) for m in s.get("_flashes", [])]
    for secret in (ACCOUNT, ACCOUNT.lstrip("0"), AADHAAR, SPACED):
        assert secret not in str(rows) and secret not in str(flashes), secret
    for path in ("/console/stipend", "/console/audit", "/console/outbox", f"/console/applications/{aid}", "/console/"):
        page = admin.get(path).get_data(as_text=True)
        assert ACCOUNT not in page and AADHAAR not in page, path


def test_the_settings_of_the_stipend():
    app, _students = _site()
    chief = _staff(app)
    page = chief.get("/console/settings").get_data(as_text=True)
    for key in ("stipend.open", "stipend.last_date", "stipend.amount", "stipend.aadhaar"):
        assert f'name="{key}"' in page, key
    from kts.db import DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS["stipend.open"] == "0" and DEFAULT_SETTINGS["stipend.amount"] == "10000"
    assert DEFAULT_SETTINGS["stipend.aadhaar"] == "1" and DEFAULT_SETTINGS["stipend.last_date"] == ""
    from kts.auth import PERMS
    assert PERMS["stipend"] == {"superadmin", "admin"}

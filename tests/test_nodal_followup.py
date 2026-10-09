"""
The Nodal Officers, what follows the accounts (version 1.2.39): the accounts from a spreadsheet, the
morning mail, the close of verification shown to them, the reminders of CICT.

    python -m pytest tests -q
"""
import html
import io
import re
from datetime import datetime

from test_nodal_access import _nodal, _portal, _token
from test_public_fixes import _staff

HEAD = ["State/UT", "Nodal HEI", "Name of the Nodal Officer", "E-mail", "Phone"]


def _upload(client, data, name):
    return client.post("/console/nodal/import", data={"_csrf": _token(client), "file": (io.BytesIO(data), name)},
                       content_type="multipart/form-data")


def _entries(page):
    return html.unescape(re.search(r'name="entries" value="([^"]*)"', page).group(1))


def test_the_accounts_from_a_spreadsheet():
    from kts.db import query
    from kts.utils import xlsx_bytes, xlsx_rows
    app, _ids = _portal()
    admin = _staff(app, "admin@tests.example", "superadmin")
    _nodal(app, "assam.old@tests.example", ["Assam"])
    _staff(app, "verifier@tests.example", "verifier")
    # the sheet to fill in: every State/UT, the Nodal Institution, the accounts that exist
    r = admin.get("/console/nodal/sheet.xlsx")
    assert r.status_code == 200 and "spreadsheetml" in r.mimetype
    rows = xlsx_rows(r.data)
    assert rows[0] == HEAD and len(rows) == 1 + 36
    assert ["Kerala", "Central University of Kerala", "", "", ""] in rows
    assert next(row for row in rows if row[0] == "Assam")[3] == "assam.old@tests.example"
    assert next(row for row in rows if row[0] == "Ladakh")[1] == ""
    filled = [("Kerala", "Central University of Kerala", "Dr.  K. Nair", "K.Nair@ker.example", "9876543210"),
              ("tamil  nadu", "", "Dr. K. Nair", "k.nair@ker.example", ""),          # the same officer, a second State/UT
              ("Delhi", "", "Dr. Delhi", "verifier@tests.example", ""),             # the e-mail of another role
              ("Assam", "", "Dr. Assam", "assam.old@tests.example", ""),            # has it already
              ("Bihar", "", "Dr. Assam", "assam.old@tests.example", ""),            # one more for an existing account
              ("Atlantis", "", "Dr. X", "x@x.example", ""),                         # no such State/UT
              ("Goa", "Indian Institute of Technology Goa", "", "", ""),            # not filled in
              ("Punjab", "", "Dr. P", "not-an-email", "")]
    page = _upload(admin, xlsx_bytes(HEAD, filled, "Nodal officers", text_cols=(3, 4)), "officers.xlsx").get_data(as_text=True)
    assert page.count("new account") == 2 and "add the State/UT to the existing account" in page
    assert "the account already has this State/UT" in page and "the role verifier" in page
    assert "unknown State/UT “Atlantis”" in page and "not valid" in page and "Goa" not in page
    assert "Create 1 account(s) and mail their temporary passwords · add States/UTs to 1 account(s)" in page
    with app.app_context():
        assert query("SELECT id FROM users WHERE email = 'k.nair@ker.example'", one=True) is None
    r = admin.post("/console/nodal/import", data={"_csrf": _token(admin), "step": "confirm", "entries": _entries(page)},
                   follow_redirects=True)
    assert "Created 1 account(s) of Nodal Officers" in r.get_data(as_text=True)
    with app.app_context():
        u = query("SELECT * FROM users WHERE email = 'k.nair@ker.example'", one=True)
        assert (u["role"], u["states"], u["name"], u["phone"], u["must_change_password"]) == ("nodal", "Kerala|Tamil Nadu", "Dr. K. Nair", "9876543210", 1)
        assert query("SELECT states FROM users WHERE email = 'assam.old@tests.example'", one=True)["states"] == "Assam|Bihar"
        assert query("SELECT role, states FROM users WHERE email = 'verifier@tests.example'", one=True)["role"] == "verifier"
        assert query("SELECT id FROM users WHERE email = 'x@x.example'", one=True) is None
        mail = query("SELECT body FROM outbox WHERE to_addr = 'k.nair@ker.example'", one=True)["body"]
    assert "As Nodal Officer for Kerala, Tamil Nadu" in mail and "Verification closes on 21 October 2026." in mail
    assert "Temporary password: Kts5-" in mail
    # the same sheet again: nothing more to do
    page = _upload(admin, xlsx_bytes(HEAD, filled, "Nodal officers", text_cols=(3, 4)), "officers.xlsx").get_data(as_text=True)
    assert "new account" not in page and "Create " not in page and ">Back</a>" in page
    # the page of the officers
    page = admin.get("/console/nodal").get_data(as_text=True)
    kerala = page.split("Central University of Kerala")[1].split("</tr>")[0]
    assert "Dr. K. Nair" in kerala and "not signed in yet" in kerala


def test_a_csv_sheet_and_numbers_of_excel():
    from kts.db import query
    from kts.utils import sheet_rows, xlsx_bytes
    # Excel keeps a mobile number typed as a number: all its digits come back, without ".0" or an exponent
    assert sheet_rows("a.xlsx", xlsx_bytes(["Phone", "Share"], [(9876543210, 12.5)]))[1] == ["9876543210", "12.5"]
    app, _ids = _portal()
    admin = _staff(app, "admin@tests.example", "superadmin")
    text = "\ufeffState/UT;Nodal HEI;Name of the Nodal Officer;E-mail;Phone\nKerala;;Dr. Semi;semi@ker.example;\n"
    page = _upload(admin, text.encode("utf-8"), "officers.csv").get_data(as_text=True)
    assert "new account" in page
    admin.post("/console/nodal/import", data={"_csrf": _token(admin), "step": "confirm", "entries": _entries(page)})
    with app.app_context():
        assert query("SELECT states FROM users WHERE email = 'semi@ker.example'", one=True)["states"] == "Kerala"
    # a sheet without the columns, or not a sheet at all
    r = _upload(admin, b"Name,Address\nX,Y\n", "other.csv")
    assert "needs the columns State/UT" in admin.get(r.headers["Location"]).get_data(as_text=True)
    r = _upload(admin, b"PK\x03\x04 not really", "broken.xlsx")
    assert "could not be read as a spreadsheet" in admin.get(r.headers["Location"]).get_data(as_text=True)
    r = _upload(admin, b"%PDF-1.4", "form.pdf")
    assert "Upload the sheet as an Excel file" in admin.get(r.headers["Location"]).get_data(as_text=True)


def test_who_may_do_what():
    app, _ids = _portal()
    admin = _staff(app, "admin2@tests.example", "admin")     # follows the officers, makes no accounts
    page = admin.get("/console/nodal").get_data(as_text=True)
    assert "Remind every officer" in page and "The accounts from a spreadsheet" not in page
    assert admin.get("/console/nodal/sheet.xlsx").status_code == 403
    assert _upload(admin, b"x", "a.csv").status_code == 403
    officer = _nodal(app, "kerala@tests.example", ["Kerala"])
    assert officer.post("/console/nodal", data={"_csrf": _token(officer), "action": "remind_all"}).status_code == 403
    # the officer reads when verification closes
    page = officer.get("/console/applications?status=submitted").get_data(as_text=True)
    assert "Verification closes on 21 October 2026 (end of the day, IST). Only verified students can take the online test on 22 October 2026." in page


def _at(day, hour, minute=0):
    from kts.utils import IST
    return datetime(2026, 10, day, hour, minute, tzinfo=IST)


def test_the_morning_mail():
    from kts import nodal
    from kts.db import execute, query, set_setting
    app, _ids = _portal()          # awaiting: Kerala 2, Assam 1, Delhi 1
    _nodal(app, "kerala@tests.example", ["Kerala"])
    _nodal(app, "punjab@tests.example", ["Punjab"])
    _nodal(app, "two@tests.example", ["Assam", "Delhi"])
    _nodal(app, "away@tests.example", ["Kerala"])
    with app.app_context():
        for key, value in (("reg.start", "2026-10-15"), ("verify.end", "2026-10-21"), ("exam.date", "2026-10-22"),
                           ("nodal.digest", "1"), ("nodal.digest_time", "08:00")):
            set_setting(key, value)
        execute("UPDATE users SET active = 0 WHERE email = 'away@tests.example'")

    def mails():
        with app.app_context():
            return {r["to_addr"]: r for r in query("SELECT * FROM outbox WHERE to_addr LIKE '%@tests.example' ORDER BY id")}

    assert nodal.daily(app, _at(14, 9)) == 0          # before registration opens
    assert nodal.daily(app, _at(16, 7, 59)) == 0      # before the hour
    assert nodal.daily(app, _at(16, 8, 5)) == 2       # Kerala, and the officer of Assam and Delhi; Punjab has nothing
    assert nodal.daily(app, _at(16, 12)) == 0         # once a day
    sent = mails()
    assert set(sent) == {"kerala@tests.example", "two@tests.example"} and sent["kerala@tests.example"]["priority"] == 1
    kerala = sent["kerala@tests.example"]
    assert kerala["subject"] == "KTS 5.0: 2 applications await your verification (Kerala)"
    assert "Awaiting your verification: 2" in kerala["body"] and "Waiting longest: " in kerala["body"]
    assert ("Verification closes on 21 October 2026 (end of the day, IST). Only verified students can take the online test "
            "on 22 October 2026.") in kerala["body"]
    assert "/console/applications?status=submitted" in kerala["body"] and "on 16 October 2026 at 8:05 AM IST" in kerala["body"]
    two = sent["two@tests.example"]["body"]
    assert "Assam\n  Awaiting your verification: 1" in two and "Delhi\n  Awaiting your verification: 1" in two
    assert "All together: 2 awaiting, 0 verified, 0 rejected." in two
    # the last two days: a reminder
    assert nodal.daily(app, _at(20, 8, 30)) == 2
    with app.app_context():
        last = query("SELECT subject FROM outbox WHERE to_addr = 'kerala@tests.example' ORDER BY id DESC LIMIT 1", one=True)["subject"]
    assert last.startswith("Reminder – KTS 5.0: 2 applications await") and last.endswith("verification closes on 21 October 2026")
    assert nodal.daily(app, _at(22, 9)) == 0          # verification has closed
    with app.app_context():
        set_setting("nodal.digest", "0")
    assert nodal.daily(app, _at(21, 9)) == 0          # switched off
    # the sender of the mail queue sends it
    import inspect
    from kts import mailq
    assert "nodal.daily(app)" in inspect.getsource(mailq.start)


def test_cict_reminds_the_officers():
    from kts.db import query
    app, _ids = _portal()
    _nodal(app, "kerala@tests.example", ["Kerala"])
    _nodal(app, "punjab@tests.example", ["Punjab"])
    admin = _staff(app, "admin@tests.example", "superadmin")
    page = admin.get("/console/nodal").get_data(as_text=True)
    assert "Waiting longest" in page and "Awaiting verification in all States/UTs: <b>4</b>" in page
    assert "Morning mail to the officers with applications awaiting them:" in page and "<b>on</b>, at 08:00 IST" in page
    kerala = page.split("Central University of Kerala")[1].split("</tr>")[0]
    assert 'value="remind"' in kerala and "today" in kerala
    punjab = page.split("<b>Punjab</b>")[1].split("</tr>")[0]
    assert 'value="remind"' not in punjab
    r = admin.post("/console/nodal", data={"_csrf": _token(admin), "action": "remind", "state": "Kerala"}, follow_redirects=True)
    assert "Reminder queued to 1 Nodal Officer(s)" in r.get_data(as_text=True)
    r = admin.post("/console/nodal", data={"_csrf": _token(admin), "action": "remind", "state": "Punjab"}, follow_redirects=True)
    assert "No reminder sent" in r.get_data(as_text=True)
    admin.post("/console/nodal", data={"_csrf": _token(admin), "action": "remind_all"})
    with app.app_context():
        rows = query("SELECT to_addr, subject FROM outbox WHERE to_addr LIKE '%@tests.example' ORDER BY id")
    assert [r["to_addr"] for r in rows] == ["kerala@tests.example", "kerala@tests.example"]
    assert all(r["subject"].startswith("Reminder – KTS 5.0: 2 applications") for r in rows)
    # the settings page offers the close of verification and the morning mail
    page = admin.get("/console/settings").get_data(as_text=True)
    assert "Verification by the Nodal Officers closes on" in page and "Time of the morning mail" in page

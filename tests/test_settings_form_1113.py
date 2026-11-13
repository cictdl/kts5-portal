"""
The Settings page of the Console, field by field (1.2.187). CICT, 13 November 2026: "check all the parameters and settings are
working normally in the portal". The audit of that day changed each of the 123 fields through the form on a throw-away database and
read some 130 pages before and after: every setting was saved and did what it says. What it found is that the form took anything: a
number field left empty, or 0 minutes, reached the students of an assessment in progress as an error, or as an attempt of 0 minutes
that was over at once. Since 1.2.187

* a value that changes is looked at before it is saved: a number field takes a number (not below what the field needs), a time
  field a time, a date field a date; what cannot be used is not saved, the field keeps what it had, and the page says which and why;
* a value that stays as it is, is never looked at, so that nothing a database already holds stands in the way of the other fields;
* the four numbers of the pattern of the online assessment (questions, minutes, marks, marks taken) read as the built-in ones when
  the stored value cannot be used.

    python -m pytest tests/test_settings_form_1113.py -q
"""
import json
import re
from datetime import datetime
from html import unescape

from conftest import make_app
from test_nodal_access import _token
from test_public_fixes import _staff

INPUT = re.compile(r'<input type="(checkbox|number|date|text)"(?: id="[^"]*")? name="([^"]+)" value="([^"]*)"( checked)?')
CHOSEN = {"launch.at": "2026-12-25T10:00", "backup.times": "03:15, 15:15", "nodal.digest_time": "09:45", "exam.start_time": "09:30",
          "exam.end_time": "18:45", "kts.start_time": "10:30", "exam.open": "auto", "papers.open": "1", "circular.new_days": "7",
          "contact.notify": "desk@tests.example", "exam.marks_per_q": "1.5", "exam.negative": "0.25", "practice.questions": "7",
          "practice.minutes": "9"}


def _portal():
    app = make_app(ADMIN_PASSWORD=None)
    return app, _staff(app, "settings.admin@tests.example", "superadmin")


def _fields(admin):
    """The fields of the form as the page shows them: {key: (type, value, checked)}."""
    page = admin.get("/console/settings").get_data(as_text=True)
    return {m.group(2): (m.group(1), unescape(m.group(3)), bool(m.group(4))) for m in INPUT.finditer(page)}


def _send(admin, **change):
    """The form as a browser sends it, with these fields changed (a name with '__' for the '.'); gives the page that follows."""
    data = {"_csrf": _token(admin)}
    for key, (kind, value, checked) in _fields(admin).items():
        if kind != "checkbox":
            data[key] = value
        elif checked:
            data[key] = "1"
    for name, value in change.items():
        key = name.replace("__", ".")
        data.pop(key, None)
        if value is not None:
            data[key] = value
    return unescape(admin.post("/console/settings", data=data, follow_redirects=True).get_data(as_text=True))


def _stored(app, key):
    from kts.db import query
    with app.app_context():
        return query("SELECT value FROM settings WHERE key = ?", (key,), one=True)["value"]


def _other(n, key, kind, now):
    if kind == "bool":
        return None if now == "1" else "1"      # a box that is not ticked is not sent
    if key in CHOSEN:
        return CHOSEN[key]
    if kind == "date":
        return "2027-02-03"
    if kind == "number":
        return str(int(now or 0) + 3)
    return f"Audit text {n}"


def test_the_form_sent_back_as_it_is_shown_saves_nothing():
    from kts.admin import SETTING_GROUPS
    from kts.db import all_settings
    app, admin = _portal()
    keys = [key for _group, items in SETTING_GROUPS for key, _label, _kind in items]
    assert len(keys) == len(set(keys)) == 123 and sorted(_fields(admin)) == sorted(keys)
    with app.app_context():
        before = all_settings()
    page = _send(admin)
    assert "Saved 0 setting(s)." in page and "Not saved" not in page
    with app.app_context():
        assert all_settings() == before


def test_every_field_is_saved_and_shown_again():
    from kts.admin import SETTING_GROUPS
    app, admin = _portal()
    items = [(key, kind) for _group, rows in SETTING_GROUPS for key, _label, kind in rows]
    before = {key: _stored(app, key) for key, _kind in items}
    change = {key: _other(n, key, kind, before[key]) for n, (key, kind) in enumerate(items)}
    page = _send(admin, **{key.replace(".", "__"): value for key, value in change.items()})
    assert f"Saved {len(items)} setting(s)." in page and "Not saved" not in page, re.findall(r"Not saved[^<]*", page)
    shown = _fields(admin)
    for key, kind in items:
        want = change[key] if kind != "bool" else ("1" if change[key] else "0")
        assert _stored(app, key) == want != before[key], key
        assert (shown[key][1] == want) if kind != "bool" else (shown[key][2] == (want == "1")), key
    # one field alone: the others stay
    page = _send(admin, site__banner="Only the banner")
    assert "Saved 1 setting(s)." in page and _stored(app, "site.banner") == "Only the banner" and _stored(app, "exam.questions") == change["exam.questions"]
    # and back, through the form
    page = _send(admin, **{key.replace(".", "__"): (value if kind != "bool" else (value if value == "1" else None))
                           for (key, kind), value in ((item, before[item[0]]) for item in items)})
    assert f"Saved {len(items)} setting(s)." in page and "Not saved" not in page
    assert {key: _stored(app, key) for key, _kind in items} == before


def test_a_number_field_takes_a_number_that_can_be_used():
    app, admin = _portal()
    for key, bad in (("exam.duration_min", ""), ("exam.duration_min", "0"), ("exam.questions", "0"), ("exam.questions", "abc"), ("exam.questions", "-5"),
                     ("exam.questions", "12.5"), ("exam.marks_per_q", "0"), ("exam.marks_per_q", ""), ("exam.negative", "-1"), ("exam.negative", ""),
                     ("quiz.max_players", "0"), ("backup.keep", "0"), ("stipend.amount", "0"), ("stipend.amount", "10,000"), ("practice.questions", "2"),
                     ("practice.questions", "31"), ("practice.minutes", "61"), ("practice.minutes", "0"), ("mail.daily_limit", ""),
                     ("hei.max_per_state", "many")):
        before = _stored(app, key)
        page = _send(admin, **{key.replace(".", "__"): bad, "merit__note": f"saved with {key} {bad!r}"})
        # the field keeps what it had and the page says so; the other field of the same form is saved
        assert f"Not saved: {key}" in page and "Saved 1 setting(s)." in page, (key, bad)
        assert _stored(app, key) == before and _stored(app, "merit.note") == f"saved with {key} {bad!r}", (key, bad)
    for key, good in (("exam.negative", "0.25"), ("exam.marks_per_q", "1.5"), ("exam.duration_min", "45"), ("exam.questions", "40"), ("mail.daily_limit", "0"),
                      ("hei.max_per_state", "4"), ("practice.questions", "30"), ("practice.minutes", "1"), ("quiz.max_players", "1")):
        page = _send(admin, **{key.replace(".", "__"): good})
        assert "Saved 1 setting(s)." in page and "Not saved" not in page and _stored(app, key) == good, (key, good)
    # the browser lets a fraction of a mark into the two fields of the marks, and no number below 0 into any
    form = admin.get("/console/settings").get_data(as_text=True)
    for key in ("exam.marks_per_q", "exam.negative"):
        assert re.search(r'<input type="number" id="%s" name="%s" value="[^"]*" min="0" step="any">' % (key, key), form), key
    assert re.search(r'<input type="number" id="exam.questions" name="exam.questions" value="40" min="0">', form)


def test_a_time_a_day_a_choice_and_an_address_are_looked_at():
    app, admin = _portal()
    refused = (("exam.start_time", "zz"), ("exam.start_time", ""), ("exam.end_time", "25:00"), ("exam.end_time", "9 pm"), ("nodal.digest_time", "8.30"),
               ("nodal.digest_time", ""), ("kts.start_time", "noon"), ("backup.times", ""), ("backup.times", "zz"), ("backup.times", "02:00, 26:00"),
               ("launch.at", "tomorrow"), ("launch.at", "2026-12-25"), ("exam.open", "open"), ("exam.open", ""), ("papers.open", "yes"),
               ("circular.new_days", "thirty"), ("circular.new_days", ""), ("contact.notify", "not an address"), ("reg.end", "2026-13-45"),
               ("kts.start", "28.11.2026"))
    for key, bad in refused:
        before = _stored(app, key)
        page = _send(admin, **{key.replace(".", "__"): bad})
        assert f"Not saved: {key}" in page and "Saved 0 setting(s)." in page and _stored(app, key) == before, (key, bad)
    accepted = (("exam.start_time", "9:05"), ("exam.end_time", "22:30"), ("nodal.digest_time", "07:30"), ("kts.start_time", "10:30"), ("kts.start_time", ""),
                ("backup.times", "2.00; 14:00"), ("backup.times", "02:00, 14:00"), ("launch.at", ""), ("launch.at", "2026-12-25T10:00"),
                ("exam.open", "auto"), ("exam.open", "1"), ("papers.open", "0"), ("circular.new_days", "0"), ("contact.notify", ""),
                ("contact.notify", "desk@tests.example"), ("hei.end", ""), ("hei.end", "2026-11-30"), ("stipend.last_date", "2027-01-31"))
    for key, good in accepted:
        page = _send(admin, **{key.replace(".", "__"): good})
        assert "Saved 1 setting(s)." in page and "Not saved" not in page and _stored(app, key) == good, (key, good)


def test_a_value_that_stays_is_not_looked_at():
    from kts.db import set_setting
    app, admin = _portal()
    # as a database of before may hold them
    odd = {"backup.keep": "", "exam.start_time": "zz", "circular.new_days": "", "contact.notify": "not an address", "hei.max_per_state": ""}
    with app.app_context():
        for key, value in odd.items():
            set_setting(key, value)
    page = _send(admin, site__banner="The banner of the test")
    assert "Saved 1 setting(s)." in page and "Not saved" not in page
    assert _stored(app, "site.banner") == "The banner of the test" and {key: _stored(app, key) for key in odd} == odd
    # until the field itself is changed: to something of use, or not
    assert "Not saved: backup.keep" in _send(admin, backup__keep="none") and _stored(app, "backup.keep") == ""
    assert "Saved 1 setting(s)." in _send(admin, backup__keep="14") and _stored(app, "backup.keep") == "14"


def test_the_numbers_of_the_pattern_read_as_the_built_in_ones_when_they_cannot_be_used():
    from kts.db import DEFAULT_SETTINGS, all_settings, get_setting, set_setting
    app, admin = _portal()
    built_in = {key: DEFAULT_SETTINGS[key] for key in ("exam.questions", "exam.duration_min", "exam.marks_per_q", "exam.negative")}
    assert built_in == {"exam.questions": "50", "exam.duration_min": "30", "exam.marks_per_q": "2", "exam.negative": "0"}
    unusable = {"exam.questions": ("", "0", "abc", "-3", "12.5", "nan"), "exam.duration_min": ("", "0", "abc", "-3", "inf"),
                "exam.marks_per_q": ("", "0", "abc", "-1", "nan", "inf"), "exam.negative": ("", "abc", "-1", "nan", "inf")}
    with app.app_context():
        for key, values in unusable.items():
            for value in values:
                set_setting(key, value)
                assert get_setting(key) == all_settings()[key] == built_in[key], (key, value)
        for key, value in (("exam.questions", "5"), ("exam.duration_min", " 7 "), ("exam.marks_per_q", "1.5"), ("exam.negative", "0.25"), ("exam.negative", "0")):
            set_setting(key, value)
            assert get_setting(key) == all_settings()[key] == value.strip(), (key, value)
        # every other setting is read as it is stored
        set_setting("backup.keep", "")
        set_setting("exam.start_time", "zz")
        assert get_setting("backup.keep") == all_settings()["backup.keep"] == "" and get_setting("exam.start_time") == "zz"
        for key in built_in:
            set_setting(key, "")
    # the pages say what is in force, and so does the form
    client = app.test_client()
    page = client.get("/examination?lang=en").get_data(as_text=True)
    assert '<div class="val">30 minutes</div>' in page and "50 objective multiple-choice questions · 2 marks each" in page
    assert {key: _fields(admin)[key][1] for key in built_in} == built_in


def _assessment(app):
    """An accepted institution with its online assessment switched on, and a question bank in English."""
    from kts import kural as K
    from kts.db import execute, executemany, utcnow
    with app.app_context():
        rows = K.generate_questions("en", 60, "tests-settings")
        executemany("INSERT INTO questions(lang, qtype, text, opt_a, opt_b, opt_c, opt_d, correct, kural_no, difficulty, active, source, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,1,'auto',?)",
                    [(r["lang"], r["qtype"], r["text"], r["opt_a"], r["opt_b"], r["opt_c"], r["opt_d"], r["correct"], r["kural_no"],
                      r["difficulty"], utcnow()) for r in rows])
        iid = execute("INSERT INTO institutions(ref, name, itype, state, district, inst_key, status, head_name, coord_name, coord_email, created_at, "
                      "updated_at) VALUES('KTS5-HEI-S001', 'Settings College', 'Government college', 'Kerala', 'Thrissur', 'tests:settings', 'accepted', "
                      "'Dr. Head', 'Coordinator', 'coord.settings@tests.example', ?, ?)", (utcnow(), utcnow()))
        execute("UPDATE institutions SET test_on = 1, test_slug = 'settings-test', test_code = 'SET123', test_from = '2026-01-01', test_to = '2099-12-31' "
                "WHERE id = ?", (iid,))
    return iid


def _sit(app, iid, n, right=3, wrong=2):
    """A student of the institution starts the assessment, answers and submits: the attempt as it is stored."""
    from kts.db import execute, query, utcnow
    with app.app_context():
        sid = execute("INSERT INTO campus_students(institution_id, name, email, mobile, roll_no, course, lang, source, created_at, ip) "
                      "VALUES(?, ?, ?, ?, '', '', 'en', 'online', ?, '')", (iid, f"Student {n}", f"student{n}@tests.example", f"91234{n:05d}", utcnow()))
    client = app.test_client()
    client.get("/assessment/settings-test")
    with client.session_transaction() as s:
        s["campus_sid"] = sid
        token = s["_csrf"]
    r = client.post("/assessment/settings-test/start", data={"_csrf": token})
    assert r.status_code == 302 and r.headers["Location"].endswith("/assessment/settings-test/paper"), r.get_data(as_text=True)[:400]
    with app.app_context():
        attempt = query("SELECT * FROM campus_attempts WHERE student_id = ?", (sid,), one=True)
        key = {q["id"]: q["correct"] for q in query("SELECT id, correct FROM questions")}
    given = {}
    for i, p in enumerate(json.loads(attempt["paper_json"])):
        if i < right:
            given[str(p["q"])] = key[p["q"]]
        elif i < right + wrong:
            given[str(p["q"])] = next(x for x in "ABCD" if x != key[p["q"]])
    r = client.post("/assessment/settings-test/submit", data={"_csrf": token, "answers": json.dumps(given)}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        return dict(query("SELECT * FROM campus_attempts WHERE student_id = ?", (sid,), one=True)), r.get_data(as_text=True)


def _minutes(attempt):
    return round((datetime.fromisoformat(attempt["deadline_at"]) - datetime.fromisoformat(attempt["started_at"])).total_seconds() / 60)


def test_a_student_starts_and_is_scored_whatever_the_fields_of_the_pattern_hold():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("camp.from", "2026-01-01")
        set_setting("camp.to", "2099-12-31")
    iid = _assessment(app)
    # as the Console sets them
    with app.app_context():
        for key, value in (("exam.questions", "5"), ("exam.duration_min", "7"), ("exam.marks_per_q", "3"), ("exam.negative", "0.5")):
            set_setting(key, value)
    attempt, page = _sit(app, iid, 1)
    assert (len(json.loads(attempt["paper_json"])), _minutes(attempt), attempt["status"], attempt["score"], attempt["correct_count"]) == (5, 7, "submitted", 8.0, 3)
    assert re.search(r">8</b>\s*/\s*15<", page)
    # a database in which the four fields were cleared before 1.2.187, or hold 0 minutes: the built-in pattern, and no error
    for n, values in enumerate(({"exam.questions": "", "exam.duration_min": "", "exam.marks_per_q": "", "exam.negative": ""},
                                {"exam.questions": "0", "exam.duration_min": "0", "exam.marks_per_q": "0", "exam.negative": "x"}), start=2):
        with app.app_context():
            for key, value in values.items():
                set_setting(key, value)
        attempt, page = _sit(app, iid, n)
        assert (len(json.loads(attempt["paper_json"])), _minutes(attempt), attempt["status"], attempt["score"], attempt["correct_count"]) == \
            (50, 30, "submitted", 6.0, 3), values
        assert re.search(r">6</b>\s*/\s*100<", page)

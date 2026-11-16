"""
"Marks recorded: N of M" leaves the dashboard by State/UT (1.2.191). CICT, 16 November 2026: "Marks recorded: 0 of 4 hide all the
marks". The switch dashboard.marks of the Console, which has shown it since 1.2.175, is off from now on, and is switched off once
on a database of before; the Console shows it again. tests/conftest.py switches it on for the tests made before
(tests/test_marks_public_1112.py).

    python -m pytest tests/test_marks_hidden_1116.py -q
"""
from test_1110 import _app, _get, _main
from test_timeline import _settings, _sql, _start

# the dashboard as the live site has it since 1.2.189, 1.2.190 and 1.2.191
LIVE = {"figures.assessment": "0", "dashboard.table": "0", "figures.percent": "0", "progress.flow": "0", "dashboard.marks": "0"}


def _marked(app):
    """The marks of the Evaluation Committee recorded for one of the four institutions selected."""
    _sql(app, "UPDATE institutions SET sop_total = 70 WHERE name = 'Presidency College'")


def test_the_dashboard_names_no_marks():
    from kts.db import DEFAULT_SETTINGS
    from kts.i18n import CATALOG
    assert DEFAULT_SETTINGS["dashboard.marks"] == "0"
    app = _app(**LIVE)
    _marked(app)
    client = app.test_client()
    page = _main(_get(client, "/dashboard?lang=en"))
    assert "Marks recorded" not in page and "dash-marks" not in page and "Annexure-V" not in page
    # the square and the block of Tamil Nadu: the Participating Institutions registered, and nothing of the marks
    tn = page[page.index('href="#d-TN"'):]
    tn = tn[:tn.index("</a>")]
    assert "Participating Institutions registered: <bdi>3</bdi>" in tn and " of " not in tn
    block = page[page.index('<details class="card dash-state" id="d-TN">'):]
    summary = block[:block.index("</summary>")]
    assert "Participating Institutions registered: 3" in summary and " of " not in summary
    # in every language
    for code, cat in CATALOG.items():
        page = _main(_get(client, f"/dashboard?lang={code}"))
        assert cat["dash.marks"] not in page and cat["dash.marks_note"] not in page and "dash-marks" not in page, code
    # the table, where the Console shows it: without the column of the marks
    with app.app_context():
        from kts.db import set_setting
        set_setting("dashboard.table", "1")
    page = _main(_get(client, "/dashboard?lang=en"))
    head = page[page.index("<thead>"):page.index("</thead>")]
    assert head.count("<th ") == 2 and "Marks recorded" not in page


def test_the_console_shows_them_again():
    from kts.admin import SETTING_GROUPS
    assert {key: kind for key, _label, kind in dict(SETTING_GROUPS)["Site"]}["dashboard.marks"] == "bool"
    app = _app(**{**LIVE, "dashboard.marks": "1"})
    _marked(app)
    page = _main(_get(app.test_client(), "/dashboard?lang=en"))
    block = page[page.index('<details class="card dash-state" id="d-TN">'):]
    assert "Marks recorded: <bdi>1 of 3</bdi>" in block[:block.index("</summary>")]
    assert page.count('class="small muted dash-marks-note"') == 1


def test_a_database_of_before_has_them_switched_off_once():
    # the live site before 1.2.191: the marks shown, as since 1.2.175
    app = _app()
    _sql(app, "UPDATE settings SET value = '1' WHERE key = 'dashboard.marks'")
    _sql(app, "DELETE FROM settings WHERE key = 'migrate.marks_off_1116'")
    before = _settings(app)
    again = _start(app)
    after = _settings(again)
    assert after["dashboard.marks"] == "0" and after["migrate.marks_off_1116"] == "1"
    assert {k: after[k] for k in before if k != "dashboard.marks"} == {k: v for k, v in before.items() if k != "dashboard.marks"}
    assert "Marks recorded" not in again.test_client().get("/dashboard?lang=en").get_data(as_text=True)
    # once: switched on again in the Console, they stay on
    _sql(again, "UPDATE settings SET value = '1' WHERE key = 'dashboard.marks'")
    assert _settings(_start(again))["dashboard.marks"] == "1"

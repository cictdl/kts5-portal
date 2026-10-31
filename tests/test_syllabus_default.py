"""
The institution's ready online test offers the 108 Thirukkural by default (version 1.2.132): the form of a new assessment
has the 108 chosen, and an assessment switched on without a choice is on the 108; the Institutional Coordinator may still
choose all 1,330 couplets, and an assessment switched on with the whole book keeps it.

    python -m pytest tests -q
"""
from test_campus import _accepted, _coordinator, _portal


def test_the_108_are_chosen_until_the_institution_says_otherwise():
    from kts.db import query
    app = _portal()
    inst = _accepted(app)
    coord, token = _coordinator(app, inst)
    page = coord.get("/institution").get_data(as_text=True)
    assert 'value="108" selected>The 108 Thirukkural only</option>' in page and 'value="all" selected>' not in page
    assert page.index('value="108"') < page.index('value="all"')
    # switched on without a choice (as a form without the field would): the 108
    r = coord.post("/institution/assessment", data={"_csrf": token, "action": "on", "test_from": "2026-10-22", "test_to": "2026-11-20"},
                   follow_redirects=True)
    page = r.get_data(as_text=True)
    assert "The online assessment is on, on the 108 Thirukkural." in page and 'value="108" selected>' in page
    with app.app_context():
        assert query("SELECT test_syllabus FROM institutions WHERE id = ?", (inst["id"],), one=True)["test_syllabus"] == "108"
    # the whole book, chosen on purpose, is kept and shown chosen
    r = coord.post("/institution/assessment", data={"_csrf": token, "action": "on", "test_from": "2026-10-22", "test_to": "2026-11-20",
                                                     "syllabus": "all"}, follow_redirects=True)
    page = r.get_data(as_text=True)
    assert "The online assessment is on. Give" in page and 'value="all" selected>All 1,330 couplets</option>' in page
    assert 'value="108" selected>' not in page
    with app.app_context():
        assert query("SELECT test_syllabus FROM institutions WHERE id = ?", (inst["id"],), one=True)["test_syllabus"] == "all"
    # and back to the 108
    r = coord.post("/institution/assessment", data={"_csrf": token, "action": "on", "test_from": "2026-10-22", "test_to": "2026-11-20",
                                                     "syllabus": "108"}, follow_redirects=True)
    assert 'value="108" selected>' in r.get_data(as_text=True)

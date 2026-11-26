"""
The public pages and two mails without a selection of institutions (1.2.202). CICT, 17 November 2026: "every institute is
registered not selected" - asked: "All registered take part ... the Console, the public pages and the mails say registered, not
selected". Thirty-seven texts in the 23 languages; what is said of the selected students stays. As CICT chose, the step of the
schedule of 19 November, with the key dates, and the Guidelines for Nodal Institutions stay as they are.

    python -m pytest tests/test_no_selection_words_1118.py -q
"""
import json
import re

import pytest

from conftest import ROOT
from test_all_registered_1117 import _app, _row, _signs_up
from test_no_reserve_1117 import _count, _newest
from test_nodal_access import _nodal
from test_reserve_1111 import LANGS, _act, _insert

KEYS = ("reg.intro", "about.p2", "prog.i3.d", "prog.i3.l2", "prog.i4.d", "prog.i7.d", "exam.intro", "nodal.intro", "nodal.p1", "nodal.p2",
        "hei.intro", "hei.declare", "hei.ask", "nodal.alloc_note", "guide.intro", "guide.s1", "guide.i1", "guide.n2_t", "guide.n2",
        "home.hei_text", "home.assess_sub", "dash.intro", "dash.intro_sel", "nl.p2", "pg.intro", "no.s4", "no.note", "hub.s_shut",
        "hub.invite", "hub.i_open", "hub.n_sel_t", "hub.n_sel", "hs.lead", "hs.n2_t", "hs.n2", "timeline.assess", "exam.merit_intro")
# the step of 19 November and its key date stay as they are (CICT: "Leave it")
STAYS = ("Scrutiny and selection of the Participating Institutions by the Nodal Institutions",
         "Selection of the Participating Institutions by the Nodal Institutions")
GONE = re.compile(r"selected Participating|selects? the (number|prescribed|Participating)|confer selection|scrutinis|if selected as", re.I)


@pytest.fixture(autouse=True)
def empty_limiter():
    from kts.utils import limiter
    limiter._hits.clear()
    yield
    limiter._hits.clear()


def test_the_texts_in_23_languages():
    from kts.i18n import CATALOG
    en = CATALOG["en"]
    assert len(en) == 1553 and len(KEYS) == 37
    for key in KEYS:
        assert not GONE.search(en[key]), key
    assert en["reg.intro"].startswith("Each Participating Institution assesses its students, selects one on merit")
    assert en["hei.intro"] == ("The Participating Institutions of KTS 5.0 – Thirukkural Payilvom, State/UT by State/UT, as they have registered "
                              "on this portal. Each of them assesses its interested students and nominates one on merit on this portal, with "
                              "a Faculty Supervisor/Guide, endorsed by the Head of the Institution.")
    assert en["home.hei_text"].startswith("All interested Higher Educational Institutions register on this portal, and every institution that "
                                          "registers is a Participating Institution. The Participating Institutions access")
    assert en["guide.n2_t"] == en["hs.n2_t"] == "See the Participating Institutions"
    assert en["timeline.assess"] == "Last date for the assessment of interested students by each Participating Institution"
    # the selected students are spoken of as before
    assert "the selected students take part in a two-lecture academic orientation" in en["about.p2"]
    assert en["prog.i7.d"].startswith("Each selected student prepares an original article")
    # the step of 19 November and the Guidelines stay
    assert en["timeline.hei_select"] == STAYS[0] and en["kd.select"] == STAYS[1]
    assert en["ng.rank"].startswith("Rank the eligible institutions in descending order of total marks")
    assert sorted(CATALOG) == sorted(LANGS)
    for code in LANGS:
        c = CATALOG[code]
        for key in KEYS:
            text = c[key]
            assert text.strip() == text and "\n" not in text and "  " not in text, (code, key)
            assert sorted(re.findall(r"\{[^}]*\}", text)) == sorted(re.findall(r"\{[^}]*\}", en[key])), (code, key)
            assert code == "en" or text != en[key], (code, key)


def test_the_pages_speak_of_no_selection_of_institutions():
    app = _app()
    _insert(app, "Kochi College", "Kerala", "Ernakulam", "accepted", None)
    client = app.test_client()
    pages = {}
    for path in ("/", "/about", "/programme", "/how-to-take-part", "/how-to-submit-the-student", "/nodal-institutions", "/institutions",
                 "/institutions/register", "/join/kl", "/examination", "/my-college", "/progress"):
        r = client.get(path + "?lang=en")
        assert r.status_code == 200, path
        page = r.get_data(as_text=True)
        main = pages[path] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page[page.index("<main"):page.index("</main>")]))
        for words in STAYS:
            main = main.replace(words, "")
        assert not GONE.search(main), (path, GONE.search(main).group(0), main[max(0, GONE.search(main).start() - 120):GONE.search(main).end() + 80])
    assert "every institution that registers is a Participating Institution" in pages["/"]
    assert "by each Participating Institution" in pages["/"]
    assert "each Participating Institution assesses its interested students and nominates one on merit" in pages["/how-to-take-part"]
    assert "See the Participating Institutions" in pages["/how-to-take-part"] and "See the Participating Institutions" in pages["/how-to-submit-the-student"]
    assert "as they have registered on this portal" in pages["/institutions"]
    assert "that, as a Participating Institution, it will assess its interested students" in pages["/institutions/register"]
    assert "Every institution that registers is a Participating Institution; each assesses its students by" in pages["/join/kl"]
    assert "marks of the selection go to geographical representation" not in pages["/join/kl"]
    # where Settings keep the selection, the State/UT page speaks of the place as before
    from kts.db import set_setting
    with app.app_context():
        set_setting("hei.select_step", "1")
    assert "marks of the selection go to geographical representation" in client.get("/join/kl?lang=en").get_data(as_text=True)


def test_the_step_of_the_assessment_in_the_schedule():
    from kts.db import execute, init_db, query
    new = "Last date for the assessment of interested students by each Participating Institution"
    old = "Last date for the assessment of interested students by each selected Participating Institution"
    app = _app()
    steps = {r["key"]: r for r in json.loads((ROOT / "data" / "timeline.json").read_text(encoding="utf-8"))}      # by its key (1.2.209)
    assert steps["assess"]["title"] == new
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM events WHERE title = ?", (new,), one=True)["n"] == 1
        execute("UPDATE events SET title = ? WHERE title = ?", (old, new))      # a database of before
    init_db(app)
    with app.app_context():
        assert query("SELECT COUNT(*) AS n FROM events WHERE title = ?", (new,), one=True)["n"] == 1
        assert query("SELECT COUNT(*) AS n FROM events WHERE title = ?", (old,), one=True)["n"] == 0
        # the step of 19 November is as it was
        assert query("SELECT COUNT(*) AS n FROM events WHERE title = ?", (STAYS[0],), one=True)["n"] == 1


def test_the_invitation_and_the_decline():
    from kts import heis as HEI
    from kts.db import set_setting
    app = _app()
    officer = _nodal(app, "nodal.py@tests.example", ["Puducherry"])
    invited = _insert(app, "Invited College", "Puducherry", "Karaikal", "identified", None, head_name="", invited_by=1,
                      invite_token="invitation-of-the-test", coord_email="coord@invited.example")
    mails = _count(app, "outbox")
    with app.app_context():
        HEI.mail_invited(_row(app, "Invited College"))
    body = _newest(app, "outbox", mails)[-1]["body"]
    assert ("confirms the Institutional Coordinator. Every institution that registers is a Participating Institution. A Participating "
            "Institution assesses its students on the Thirukkural (the portal offers a ready online test) and nominates one student on merit") in body
    assert "confer selection" not in body and "selects the Participating Institutions" not in body
    # a decline
    _signs_up(app, "Alpha College")
    alpha = _row(app, "Alpha College")["id"]
    mails = _count(app, "outbox")
    assert "Alpha College: declined" in _act(officer, alpha, "decline").get_data(as_text=True)
    body = _newest(app, "outbox", mails)[0]["body"]
    assert body.startswith("Dear Sir/Madam,\n\nThe Nodal Institution of Puducherry could not accept the registration of your institution as a "
                           "Participating Institution of KTS 5.0.\n\nReference: KTS5-HEI-")
    assert "confer selection" not in body
    # where Settings keep the selection, the two mails are as they were
    with app.app_context():
        set_setting("hei.select_step", "1")
        mails = _count(app, "outbox")
        HEI.mail_invited(_row(app, "Invited College"))
    body = _newest(app, "outbox", mails)[-1]["body"]
    assert "The Nodal Institution then selects the Participating Institutions from those registered" in body
    assert "registration does not by itself confer selection. A selected institution assesses its students on the Thirukkural" in body
    assert invited

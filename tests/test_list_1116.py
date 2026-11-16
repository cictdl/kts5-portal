"""
CICT's list of 16 November 2026, page by page (1.2.192):

  /institutions          no percentages in "At a glance" and "Type of institution"; no "out of 1,000"
  /how-to-take-part      no part for students; for participating institutions: step 3 says that the institutions shall use the
                         portal's online assessment, links to "Online Assessment" and gives its instructions; no step "Select one
                         student on merit"; "After the nomination" with the days. For Nodal Officers: step 3 without "The portal
                         reminds those that are behind, and you can remind them too."; step 4 without "or reject it with a remark".
  /examination           "Online Assessment" for "Classroom quiz"; "The assessment at the institution" rewritten; the instructions
  the nomination form    its heading: STUDENT NOMINATION FORM
  /nodal-institutions    no percentages

Asked which tool "Online Assessment" names, CICT chose the institution's online test (not the live Classroom quiz).

    python -m pytest tests/test_list_1116.py -q
"""
import re

import pytest
from markupsafe import escape

from conftest import ROOT, make_app
from test_1110 import _app, _get, _main
from test_nodal_officers_status import _portal as _with_officers

SHALL = ("The Participating Institutions shall use the portal&#39;s online assessment for the selection of the students. "
         "The institutions may also assess the students in any other suitable mode.")
STEPS = ["Sign in", "Check the status", "Assess your students", "Select one student"]
HIDDEN = {"figures.percent": "0"}


@pytest.fixture(scope="module")
def site():
    from kts.db import set_setting
    app = make_app(ADMIN_PASSWORD=None)
    with app.app_context():
        set_setting("reg.end", "2026-11-24")      # the tests' portal keeps its registration open to 2030 (tests/conftest.py)
    return app.test_client()


def _part(page, name):
    start = page.index(f'<section id="{name}" class="card guide-part"')
    return page[start:page.index("</section>", start)]


def test_how_to_take_part_for_institutions_and_nodal_officers_only(site):
    page = _main(_get(site, "/how-to-take-part?lang=en"))
    # no part for students, nor a link to it
    assert "For students" not in page and 'id="students"' not in page and "#students" not in page
    assert "Check that your institution takes part" not in page and "As a selected student" not in page
    assert re.findall(r'<div class="res-tabs no-print">(.*?)</div>', page, re.S)[0].count("<a ") == 2
    inst = _part(page, "institutions")
    titles = re.findall(r'<li style="margin-bottom:12px"><b>([^<]+)</b>', inst)
    assert titles == ["Register your institution by 18 Nov 2026", "Sign in to the institution&#39;s page", "Assess your students by 23 Nov 2026",
                      "Submit the nomination by 24 Nov 2026", "Campus activities and report", "After the nomination"]
    assert "Select one student on merit" not in page
    # step 3: what the institutions shall use, the link "Online Assessment", and how it is done
    step3 = inst[inst.index("Assess your students by 23 Nov 2026"):inst.index("Submit the nomination by 24 Nov 2026")]
    assert SHALL in step3 and '<a href="/examination#online-assessment"><b>Online Assessment</b>' in step3
    assert "Switch on the portal&#39;s online test, choose its days" not in step3      # the text of the step until 1.2.191
    assert re.findall(r'<li><b class="hs-st">([^<]+)</b>', step3) == STEPS
    assert '<b class="ui-name" lang="en" dir="ltr">Switch on</b>' in step3 and "by 23 Nov 2026" in step3 and '<a href="/institution/login">' in step3
    assert '<b class="ui-name" lang="en" dir="ltr">Select</b> beside the student chosen on merit' in step3
    # the last step, with its days
    step7 = inst[inst.index("<b>After the nomination</b>"):]
    days = re.findall(r"<li><b><bdi>([^<]+)</bdi></b> · ([^<]+)</li>", step7)
    assert days == [("28 Nov 2026", "Inaugural function of KTS 5.0"), ("12 Dec 2026", "Valedictory function of KTS 5.0"),
                    ("By 14 Dec 2026", "Academic orientation and study material from CICT"),
                    ("15 Dec 2026 – 14 Jan 2027", "One-month research and writing period"),
                    ("By 14 Jan 2027", "Last date to submit the research work and reports")]
    # the Nodal Officers: five steps, two of them shorter
    nodal = _part(page, "nodal")
    assert len(re.findall(r'<li style="margin-bottom:12px"><b>', nodal)) == 5
    assert "selected one and registered them, with their coordinators.</p>" in nodal and "remind" not in nodal
    assert "and nomination form, and verify the application.</p>" in nodal and "reject" not in nodal
    assert "{" not in re.sub(r"<script.*?</script>", "", page, flags=re.S)
    # the guide of the institutions to print: the same six steps
    printed = _main(_get(site, "/how-to-take-part/institutions?lang=en"))
    assert re.findall(r'<li style="margin-bottom:12px"><b>([^<]+)</b>', printed) == titles and SHALL in printed
    assert re.findall(r'<li><b class="hs-st">([^<]+)</b>', printed) == STEPS and "For Nodal Officers" not in printed
    # the pages that sent a student to that part lead to the guide
    for path in ("/practice?lang=en",):
        assert 'href="/how-to-take-part"' in _get(site, path) and "#students" not in _get(site, path)


def test_the_page_of_the_assessment(site):
    whole = _get(site, "/examination?lang=en")
    page = _main(whole)
    # "Online Assessment" under the heading, for "Classroom quiz"; the quiz keeps its place in the menu
    assert '<p class="exam-quiz-link"><a class="btn quiz-cta" href="#online-assessment">🖥 Online Assessment</a></p>' in page
    assert "Classroom quiz" not in page and 'href="/quiz/"' not in page and "Classroom quiz" in whole
    # the assessment at the institution: what the institutions shall use
    card = page[page.index("<h2>The assessment at the institution</h2>"):page.index('id="online-assessment"')]
    assert SHALL in card and "which the institution may use" not in page and "a short written test, an oral interaction" not in page
    assert "30 minutes" in card and "50 objective multiple-choice questions" in card      # the pattern and the guidelines stay
    # the instructions, step by step
    block = page[page.index('<div class="card" id="online-assessment"'):]
    block = block[:block.index("</ol>") + 400]
    assert "<h2>🖥 Online Assessment</h2>" in block and "For the Institutional Coordinator of a Participating Institution" in block
    assert re.findall(r'<li><b class="hs-st">([^<]+)</b>', block) == STEPS
    assert "Type the six-digit code that the portal mails to you" in block and '<b class="ui-name" lang="en" dir="ltr">The online assessment of the portal</b>' in block
    assert 'href="/institution/login"' in block and 'href="/how-to-submit-the-student"' in block
    # "Submitting the selected student" gives the same four steps first, as before
    steps = re.findall(r'<li><b class="hs-st">([^<]+)</b>', _main(_get(site, "/how-to-submit-the-student?lang=en")))
    assert steps[:4] == STEPS and steps[4] == "Submit the nomination" and len(steps) == 13


def test_the_texts_in_every_language(site):
    from kts.i18n import CATALOG
    en = CATALOG["en"]
    assert en["exam.online_title"] == "Online Assessment" and escape(en["exam.shall"]) == SHALL
    assert en["guide.n3"] == ("The Progress page of the console shows which institutions of your State/UT have assessed their students, "
                              "selected one and registered them, with their coordinators.")
    assert en["guide.n4"] == "In the verification queue of the console, check each student's photograph, ID proof and nomination form, and verify the application."
    assert len(CATALOG) == 23
    for code, cat in CATALOG.items():
        for key in ("exam.online_title", "exam.shall", "guide.n3", "guide.n4"):
            assert cat[key] and cat[key].strip() == cat[key] and (code == "en" or cat[key] != en[key]), (code, key)
        # one sentence each for the two steps of the Nodal Officers, two for what the institutions shall use
        ends = lambda text: len(re.findall(r"[।.۔᱾](?:\s|$)", text))
        assert (ends(cat["guide.n3"]), ends(cat["guide.n4"]), ends(cat["exam.shall"])) == (1, 1, 2), code
        assert "{" not in cat["guide.n3"] + cat["guide.n4"] + cat["exam.shall"] + cat["exam.online_title"], code
        for path in ("/how-to-take-part", "/examination"):
            page = _main(_get(site, f"{path}?lang={code}"))
            assert str(escape(cat["exam.shall"])) in page and str(escape(cat["exam.online_title"])) in page, (code, path)
            assert not re.search(r"\{[a-z_]+\}", page), (code, path)
        guide = _main(_get(site, f"/how-to-take-part?lang={code}"))
        assert str(escape(cat["guide.n3"])) in guide and str(escape(cat["guide.n4"])) in guide, code
        assert 'id="students"' not in guide and len(re.findall(r'<li style="margin-bottom:12px"><b>', guide)) == 11, code      # 6 + 5 steps
    assert CATALOG["hi"]["exam.online_title"] == "ऑनलाइन मूल्यांकन" and CATALOG["ta"]["exam.online_title"] == "இணையவழி மதிப்பீடு"


def test_no_percentages_on_the_participating_institutions():
    client = _app(**HIDDEN).test_client()
    page = _main(_get(client, "/institutions?lang=en"))
    pi = page[page.index('<section class="pi"'):page.index('pi-states"')]
    # at a glance: the number, without a ring, a percentage or "of 1,000"
    kpis = pi[pi.index('<div class="pi-kpis'):pi.index('<div class="pi-two')]
    assert '<div class="num">5</div><div class="lbl">Participating institutions</div>' in kpis
    assert "pi-ring" not in kpis and "<svg" not in kpis and "%" not in kpis and "of 1,000" not in kpis and "1,000" not in pi
    # the types of institution: the counts, no percentage
    legend = pi[pi.index('<ul class="pi-legend">'):pi.index("</ul>", pi.index('<ul class="pi-legend">'))]
    assert re.findall(r"<span>([^<]+)</span><b>(\d+)</b></li>", legend) == [("Government college", "5")] and "%" not in legend
    # the switch of the Console brings the three back
    client = _app(**{"figures.percent": "1"}).test_client()
    pi = _main(_get(client, "/institutions?lang=en"))
    assert 'class="card pi-kpi pi-ring"' in pi and 'class="pct">0%</text>' in pi and "<bdi>5 of 1,000</bdi>" in pi
    assert '<b>5</b><span class="muted small">100%</span></li>' in pi


def test_no_percentages_on_the_nodal_institutions():
    from kts.db import set_setting
    app = _with_officers()
    with app.app_context():
        set_setting("figures.percent", "0")
    page = app.test_client().get("/nodal-institutions?lang=en").get_data(as_text=True)
    rings = page[page.index('class="prog-rings no-rings'):page.index('class="no-steps-h"')]
    assert rings.count('class="card prog-ring') == 3 and "<svg" not in rings and "%" not in rings and 'class="pct"' not in rings
    assert '<div class="num">2</div>' in rings and "2 of 31" in rings and "29 of 31" in rings
    assert "Nodal Institutions with a Nodal Officer on the portal" in rings
    with app.app_context():
        set_setting("figures.percent", "1")
    page = app.test_client().get("/nodal-institutions?lang=en").get_data(as_text=True)
    rings = page[page.index('class="prog-rings no-rings'):page.index('class="no-steps-h"')]
    assert rings.count("<svg") == 3 and ">6%</text>" in rings


def test_the_switch_names_the_pages_it_covers():
    from kts.admin import SETTING_GROUPS
    label = {key: text for key, text, _kind in dict(SETTING_GROUPS)["Site"]}["figures.percent"]
    assert "Participating Institutions page" in label and "Nodal Institutions page" in label and "N of 1,000" in label


def test_the_heading_of_the_nomination_form():
    import fitz
    path = ROOT / "static" / "KTS5-nomination-form.pdf"
    doc = fitz.open(str(path))
    text = " ".join(doc[0].get_text().split())
    assert doc.page_count == 1 and "STUDENT NOMINATION FORM" in text and text.count("NOMINATION FORM") == 1
    # the rest of the form as it was: the day of the nomination twice, the four parts
    assert text.count("24 November 2026") == 2 and "A. Participating institution" in text and "D. Endorsement by the Head of the Institution" in text
    assert path.stat().st_size < 400_000

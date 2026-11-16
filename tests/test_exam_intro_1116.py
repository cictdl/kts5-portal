"""
The paragraph of "The assessment at the institution" (1.2.195). CICT, 16 November 2026, of /examination: "... The portal gives
every Participating Institution a ready online assessment available in our portal (provide web link) which the institution may
use: its Institutional Coordinator switches it on, and the students take it with the link and the access code of the institution.
modify as per the wordings". The words "online assessment" are the link, to the Online Assessment of the same page.

    python -m pytest tests/test_exam_intro_1116.py -q
"""
import re

from markupsafe import escape

from test_1110 import _app, _get, _main

FIRST = ("Each selected Participating Institution assesses its interested students on their interest in and understanding of the "
         "Thirukkural, by a short written test, an oral interaction, a presentation, an essay, a quiz or a suitable combination of "
         "these, in a fair and documented process approved by the Head of the Institution or an authorised committee, and nominates "
         "one student on merit.")
SECOND = ('The portal gives every Participating Institution a ready <a href="/examination#online-assessment">online assessment</a> '
          "available in our portal, which the institution may use: its Institutional Coordinator switches it on, and the students "
          "take it with the link and the access code of the institution.")
SHALL = "The Participating Institutions shall use the portal&#39;s online assessment for the selection of the students."


def test_the_paragraph_in_the_words_of_cict():
    client = _app().test_client()
    page = _main(_get(client, "/examination?lang=en"))
    assert f'<p class="dim">Kashi Tamil Sangamam 5.0 · Thirukkural Payilvom. {FIRST} {SECOND}</p>' in page
    card = page[page.index("<h2>The assessment at the institution</h2>"):page.index('id="online-assessment"')]
    assert FIRST in card and SECOND in card and SHALL not in page
    # the link leads to the Online Assessment of the page, which is there, once
    assert page.count('<div class="card" id="online-assessment"') == 1 and page.count('href="/examination#online-assessment"') == 1
    # the guide of the institutions keeps what the institutions shall use (1.2.192), with its own link to the Online Assessment
    guide = _main(_get(client, "/how-to-take-part?lang=en"))
    assert SHALL in guide and 'href="/examination#online-assessment"' in guide and FIRST not in guide


def test_in_every_language():
    from kts.i18n import CATALOG
    client = _app().test_client()
    en = CATALOG["en"]["exam.intro"]
    assert len(CATALOG) == 23
    for code, cat in CATALOG.items():
        text = cat["exam.intro"]
        # the words of the link between {a} and {/a}, once, and no other placeholder
        assert re.findall(r"\{[^}]*\}", text) == ["{a}", "{/a}"], code
        before, words, after = re.match(r"^(.*)\{a\}(.+?)\{/a\}(.*)$", text, re.S).groups()
        assert words.strip() == words and before.strip() and after.strip(), code
        assert code == "en" or text != en, code
        page = _main(_get(client, f"/examination?lang={code}"))
        assert f'{escape(before)}<a href="/examination#online-assessment">{escape(words)}</a>{escape(after)}</p>' in page, code
        assert "{a}" not in page and "{/a}" not in page and str(escape(cat["exam.shall"])) not in page, code
        # what the institutions shall use stays in their guide
        assert str(escape(cat["exam.shall"])) in _main(_get(client, f"/how-to-take-part?lang={code}")), code

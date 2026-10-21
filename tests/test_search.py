"""
Search across the whole portal (version 1.2.90): a search box at the top of every page, and /search, which finds every
word of a query in the pages of the portal, the notices, the Digital repository, the Thirukkural (Tamil, transliteration,
English and the visitor's language; a number from 1 to 1330 is that couplet), the seminars and workshops, the orientation
lectures and the reels; the words found are marked, and what the visitor typed is never taken as markup.

    python -m pytest tests -q
"""
import re

from markupsafe import escape

from conftest import make_app


def _client():
    return make_app(ADMIN_PASSWORD=None).test_client()


def _page(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


def _group(page, key):
    part = page.split(f'<section class="search-group" aria-labelledby="sg-{key}">')[1]
    return part[:part.index("</section>")]


def test_the_words_and_the_marks():
    from kts import search as S
    assert S.query_words("  Thiru‌KKURAL   Rain ") == ["thirukkural", "rain"]
    assert S.query_words("a") == [] and len(S.query_words(" ".join(["w"] * 20))) == 8
    assert S.matches(S.norm("The Excellence of Rain"), ["rain", "excel"]) and not S.matches("rain", ["rain", "snow"])
    # a word in Latin letters begins a word; one in an Indian script is found within words too
    assert not S.matches(S.norm("Tamil Typing Trainer, the brain"), ["rain"]) and S.matches(S.norm("rainfall"), ["rain"])
    assert S.matches(S.norm("வான்சிறப்பு"), ["வான்"]) and S.matches(S.norm("மழைவான்"), ["வான்"])
    assert str(S.highlight("brain rain", ["rain"])) == "brain <mark>rain</mark>"
    assert str(S.highlight("Rain <b>& rain", ["rain"])) == "<mark>Rain</mark> &lt;b&gt;&amp; <mark>rain</mark>"
    long = "x " * 200 + "the word here " + "y " * 200
    piece = str(S.snippet(long, ["word"]))
    assert "<mark>word</mark>" in piece and piece.startswith("… ") and piece.endswith(" …") and len(piece) < 260


def test_the_box_at_the_top_of_every_page_in_every_language():
    from kts.i18n import CATALOG
    client = _client()
    for code, catalogue in CATALOG.items():
        page = _page(client, f"/about?lang={code}")
        box = page[page.index('<form class="site-search" role="search" method="get" action="/search">'):]
        box = box[:box.index("</form>")]
        assert f'<label for="site-q" class="visually-hidden">{escape(catalogue["search.label"])}</label>' in box, code
        assert f'placeholder="{escape(catalogue["search.label"])}"' in box, code


def test_an_empty_search_explains_itself():
    from kts.i18n import CATALOG
    page = _page(_client(), "/search?lang=en")
    assert str(escape(CATALOG["en"]["search.hint"])) in page and "search-group" not in page


def test_the_thirukkural_by_its_number_and_by_its_words():
    client = _client()
    page = _page(client, "/search?lang=en&q=45")
    kural = _group(page, "kural")
    assert kural.index('href="/thirukkural/45"') < kural.index("</li>")
    # Tamil words of the first couplet, and English words of the chapter on rain (couplets 11-20)
    page = _page(client, "/search?lang=en&q=அகர முதல")
    assert 'href="/thirukkural/1"' in _group(page, "kural") and "<mark>அகர</mark>" in page
    page = _page(client, "/search?lang=en&q=rain")
    found = [int(n) for n in re.findall(r'href="/thirukkural/(\d+)"', _group(page, "kural"))]
    assert found and set(range(11, 21)) & set(found)


def test_the_language_of_the_visitor():
    from kts import kural as K
    k = K.kural(100)
    word = max(" ".join(K.lines(k, "hi")).split(), key=len)
    page = _page(_client(), f"/search?lang=hi&q={word}")
    assert 'href="/thirukkural/100"' in _group(page, "kural")
    assert '<span lang="hi" dir="ltr">' in _group(page, "kural")


def test_pages_seminars_lectures_and_reels():
    client = _client()
    page = _page(client, "/search?lang=en&q=stipend")
    assert 'href="/stipend"' in _group(page, "pages") or "/stipend" in _group(page, "pages")
    page = _page(client, "/search?lang=en&q=brahmi")
    assert "/seminars-workshops?y=" in _group(page, "events") and "<mark>Brahmi</mark>" in page
    page = _page(client, "/search?lang=en&q=Insights from the Thirukkural")
    assert "youtube.com/watch?v=Z3fGrbHLFr8" in _group(page, "lectures")
    page = _page(client, "/search?lang=en&q=malto")
    assert "youtube.com/shorts/EAvMVUp50-s" in _group(page, "reels")
    assert 'target="_blank" rel="noopener"' in _group(page, "reels")


def test_nothing_found_and_no_markup_from_the_visitor():
    from kts.i18n import CATALOG
    page = _page(_client(), "/search?lang=en&q=%3Cscript%3Ezzqqxx")
    assert "<script>zzqqxx" not in page and "&lt;script&gt;zzqqxx" in page
    assert str(escape(CATALOG["en"]["search.none"].replace("{q}", "<script>zzqqxx"))) in page
    assert "search-group" not in page
    # the query is read up to 80 characters
    page = _page(_client(), "/search?lang=en&q=" + "k" * 300)
    assert 'value="' + "k" * 80 + '"' in page


def test_the_results_line_and_the_limits():
    from kts.i18n import CATALOG
    page = _page(_client(), "/search?lang=en&q=the")
    n = int(re.search(r"(\d+) results for", page).group(1))
    assert n > 20
    kural = _group(page, "kural")
    assert kural.count('<li class="search-hit">') == 20
    assert CATALOG["en"]["search.more"].split("{n}")[0] in kural
    assert 'href="/search"' in _page(_client(), "/sitemap?lang=en")

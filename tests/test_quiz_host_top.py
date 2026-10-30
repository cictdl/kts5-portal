"""
The classroom quiz (version 1.2.121): "Host a quiz" is a large button at the top of the page /quiz, above the form by
which the students join, for every visitor and in every language.

    python -m pytest tests -q
"""
from markupsafe import escape

from conftest import make_app


def test_host_a_quiz_comes_first():
    from kts.i18n import CATALOG
    client = make_app(ADMIN_PASSWORD=None).test_client()
    for code, catalogue in CATALOG.items():
        page = client.get(f"/quiz/?lang={code}").get_data(as_text=True)
        button = (f'<a class="btn host-top" href="/quiz/host"><span class="host-ico" aria-hidden="true">🖥</span>'
                  f'<span>{escape(catalogue["quiz.host_title"])}</span>')
        assert page.count('href="/quiz/host"') == 1 and button in page, code
        assert page.index(button) < page.index('<div class="quiz-card join-card">') < page.index('class="join-form"'), code
        assert "host-line" not in page, code
    assert '<link rel="stylesheet" href="/static/css/quiz.css?v=2">' in page

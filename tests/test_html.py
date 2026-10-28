"""Newsletter HTML rendering and sanitizing (tools/html.py)."""

from tools.html import markdown_to_html


def render(markdown_text: str) -> str:
    return markdown_to_html.invoke({"markdown_text": markdown_text})


def test_renders_markdown_into_a_full_page():
    html = render("# This Week in Music\n\n## Rock\n\nNew **albums**.")
    assert html.startswith("<!doctype html>")
    assert "<h1>This Week in Music</h1>" in html
    assert "<strong>albums</strong>" in html
    assert "<title>This Week in Music</title>" in html


def test_strips_scripts_and_event_handlers():
    html = render('Hi <script>alert(1)</script> <img src="x.png" onerror="alert(2)">')
    assert "<script>alert(1)" not in html
    assert "onerror" not in html


def test_strips_javascript_links():
    html = render("[click](javascript:alert(1))")
    assert "javascript:" not in html


def test_keeps_tables():
    html = render("| Genre | Revenue |\n|---|---|\n| Rock | 826.65 |")
    assert "<table>" in html

"""Turn newsletter Markdown into a styled, sanitized HTML page.

The page template is ours and trusted. The newsletter body comes from web
search results, which we don't trust, so it's sanitized with nh3 to strip
anything like <script> tags or onerror= attributes before it's inserted.
"""

from __future__ import annotations

import markdown as md
import nh3
from langchain_core.tools import tool

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ max-width: 720px; margin: 48px auto; padding: 0 20px;
          font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
          line-height: 1.65; color: #1d1d1f; }}
  h1 {{ font-size: 2.1rem; border-bottom: 3px solid #7c3aed; padding-bottom: .3em; }}
  h2 {{ color: #7c3aed; margin-top: 1.8em; }}
  footer {{ margin-top: 3em; padding-top: 1em; border-top: 1px solid #e5e5e5;
            color: #6e6e73; font-size: .85rem; }}
</style>
</head>
<body>
{body}
<footer>Put together by the Deep Sales Assistant.</footer>
</body>
</html>"""


@tool
def markdown_to_html(markdown_text: str, title: str = "This Week in Music") -> str:
    """Convert newsletter Markdown into a complete, styled HTML page.
    Returns the whole HTML document as a string."""
    body = md.markdown(markdown_text, extensions=["tables", "fenced_code"])
    return _PAGE.format(title=title, body=nh3.clean(body))

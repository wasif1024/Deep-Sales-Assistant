"""Web search (Tavily) for the newsletter's genre-researcher subagent.

Needs TAVILY_API_KEY. Without it this module isn't imported at all (see
newsletter_agent_graph.py) and the rest of the assistant still works.
"""

from __future__ import annotations

import os
import time

from langchain_core.tools import tool
from requests.exceptions import ConnectionError as RequestsConnectionError
from tavily import TavilyClient

_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 2


@tool
def internet_search(query: str, max_results: int = 8) -> dict:
    """Search recent news on the web. Use it to find out what's new in a music
    genre: releases, artists, trends, and events."""
    # Researchers run several searches in parallel. A shared client can hand
    # out pooled connections the server has already closed, which shows up as
    # connection resets, so create a client per call and retry if one resets.
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    last_error: RequestsConnectionError | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return client.search(query, max_results=max_results, topic="news")
        except RequestsConnectionError as e:
            last_error = e
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_RETRY_DELAY_SECONDS)
    raise last_error

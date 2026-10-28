"""newsletter-agent: a separate graph the main agent runs in the background.

It has its own entry in langgraph.json, so the main agent can start it with
`start_async_task` and keep working instead of waiting for it.

It does the whole newsletter job itself. It calls a genre-researcher subagent
once per genre (all in one turn, so they run in parallel), then combines the
segments into HTML. The main agent picks up the result later with
`check_async_task`.

Storage: a `StoreBackend` namespaced by this run's thread_id. Each background
task gets a new thread, so each newsletter's research notes are kept separate.
The namespace is looked up when the store is first used, not when the module
is imported, which is why this graph can be a plain module-level object.
"""

from __future__ import annotations

import os

from deepagents import create_deep_agent
from deepagents.backends.store import StoreBackend
from langgraph.config import get_config

from models import model, strong_model
from subagents import GENRE_PROMPT
from tools.html import markdown_to_html

# langgraph.json registers this graph, so it's always imported. tools.search
# creates a Tavily client, so only import it when a key is configured.
if os.environ.get("TAVILY_API_KEY"):
    from tools.search import internet_search

    _research_tools = [internet_search]
else:
    _research_tools = []

NEWSLETTER_AGENT_PROMPT = """You write Chinook's weekly "This Week in Music" \
customer newsletter. You run in the background; the sales assistant collects \
your result when you finish.

You'll get a list of genres. Call the genre-researcher subagent once for each \
genre, all in the same turn so they run in parallel, and collect the segment \
each one returns.

When every call has returned:
1. Combine the segments that succeeded into one Markdown document: a \
"# This Week in Music" title, a one-sentence intro, then the segments in the \
order given. If any genre failed, leave it out and add one short line saying \
which genre(s) are missing this week. If every genre failed, don't build a \
newsletter; reply with one sentence saying research failed for all genres, \
and stop.
2. Pass the Markdown to `markdown_to_html`.

Reply with nothing but the HTML that tool returns. Your reply is saved \
directly to a file, so any extra text would end up in the newsletter."""

_genre_researcher = {
    "name": "genre-researcher",
    "description": (
        "Researches recent news in one music genre and writes its newsletter "
        "segment. Call once per genre, in parallel."
    ),
    "system_prompt": GENRE_PROMPT,
    "tools": _research_tools,
    "model": model,
}

_backend = StoreBackend(
    namespace=lambda rt: (get_config()["configurable"]["thread_id"], "research")
)

graph = create_deep_agent(
    model=strong_model,
    tools=[markdown_to_html],
    system_prompt=NEWSLETTER_AGENT_PROMPT,
    subagents=[_genre_researcher],
    backend=_backend,
    name="newsletter-agent",
)

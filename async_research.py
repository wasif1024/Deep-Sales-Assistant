"""Lets the main agent start newsletter-agent as a background (async) task."""

from deepagents.middleware.async_subagents import AsyncSubAgentMiddleware


def build_async_research_middleware() -> AsyncSubAgentMiddleware:
    """Give the main agent the async-task tools (`start_async_task`,
    `check_async_task`, `list_async_tasks`) for the newsletter-agent graph,
    which runs on the same LangGraph server."""
    return AsyncSubAgentMiddleware(
        async_subagents=[
            {
                "name": "newsletter-agent",
                "description": (
                    "Researches the chosen music genres and builds the styled "
                    "HTML newsletter in the background. Start it once per "
                    "request and carry on; later, collect the HTML with "
                    "`list_async_tasks` and `check_async_task`."
                ),
                "graph_id": "newsletter-agent",
            }
        ]
    )

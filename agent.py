"""Deep Sales Assistant: the main agent graph.

Every thread gets its own LangSmith sandbox. It holds the agent's whole
filesystem: the skills and AGENTS.md (copied in when the sandbox is created),
plus every file the agent writes or runs. Nothing the agent does touches the
host machine's disk.

Charts don't need a dedicated tool: the agent writes a Python script with
`write_file` and runs it with `execute`, which deepagents adds automatically
because the sandbox backend can run commands.

Run with ./start.sh
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.backends.langsmith import LangSmithSandbox
from langchain_core.runnables import RunnableConfig
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_quickjs import CodeInterpreterMiddleware
from langgraph_sdk.runtime import ServerRuntime

from async_research import build_async_research_middleware
from models import strong_model
from subagents import build_subagents
from tools.html import markdown_to_html

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent

SYSTEM_PROMPT = (
    "You are the Deep Sales Assistant, working for Jane Peacock, a Sales "
    "Support Agent at Chinook, an online music store. Your operating manual is "
    "loaded from memory; follow it, and for each task use the matching "
    "playbook in /skills/.\n\n"
    "Your filesystem lives entirely inside an isolated sandbox. To make a "
    "chart, write a Python script with write_file and run it with execute, "
    "saving the image under /outputs/. The sandbox's Python is externally "
    "managed, so install packages like this: "
    "`pip install --break-system-packages matplotlib && python3 <script>`."
)

MAIL_SERVER = {"transport": "streamable-http", "url": "http://127.0.0.1:5002/mcp"}

SANDBOX_IDLE_TTL_SECONDS = 600  # stop after 10 idle minutes
SANDBOX_DELETE_AFTER_STOP_SECONDS = 3600  # delete an hour after stopping

_enable_search = bool(os.environ.get("TAVILY_API_KEY"))
if not _enable_search:
    logger.info("TAVILY_API_KEY not set; the newsletter agent is disabled.")


def _get_or_create_sandbox(name: str) -> tuple:
    """Return (sandbox, is_new) for the sandbox with this name.

    Reuses it if it's ready, restarts it if it's stopped, waits if it's
    starting up, and creates it if it doesn't exist. That way every turn of a
    thread lands in the same sandbox.
    """
    from langsmith.sandbox import SandboxClient

    client = SandboxClient()
    matches = [s for s in client.list_sandboxes() if s.name == name]
    if matches:
        sb = matches[0]
        status = getattr(sb, "status", "ready")
        try:
            if status == "ready":
                logger.info("Reusing sandbox %s", name)
                return sb, False
            if status == "stopped":
                logger.info("Restarting sandbox %s", name)
                return client.start_sandbox(name, timeout=15), False
            logger.info("Waiting for sandbox %s (status: %s)", name, status)
            return client.wait_for_sandbox(name, timeout=15), False
        except Exception as exc:
            raise RuntimeError(
                "The sandbox isn't available yet. Please try again in a moment."
            ) from exc

    try:
        # Both limits keep costs down if a session is abandoned.
        sb = client.create_sandbox(
            name=name,
            idle_ttl_seconds=SANDBOX_IDLE_TTL_SECONDS,
            delete_after_stop_seconds=SANDBOX_DELETE_AFTER_STOP_SECONDS,
        )
        logger.info("Created sandbox %s", name)
        return sb, True
    except Exception:
        # A concurrent run may have created it after we listed; use theirs.
        matches = [s for s in client.list_sandboxes() if s.name == name]
        if matches:
            logger.info("Reusing sandbox %s created by a concurrent run", name)
            return matches[0], False
        raise


def _upload_skills_and_memory(backend: LangSmithSandbox) -> None:
    """Copy AGENTS.md and skills/ from this project into a new sandbox."""
    files: list[tuple[str, bytes]] = [
        ("/AGENTS.md", (PROJECT_DIR / "AGENTS.md").read_bytes())
    ]
    skills_dir = PROJECT_DIR / "skills"
    for path in skills_dir.rglob("*"):
        if path.is_file():
            files.append((f"/skills/{path.relative_to(skills_dir)}", path.read_bytes()))
    results = backend.upload_files(files)
    for (path, _), result in zip(files, results):
        if result.error:
            logger.warning("Could not upload %s to the sandbox: %s", path, result.error)


async def _sandbox_backend(thread_id: str) -> LangSmithSandbox:
    """Get this thread's sandbox backend, setting the sandbox up on first use."""
    sandbox, is_new = await asyncio.to_thread(_get_or_create_sandbox, f"thread-{thread_id}")
    backend = LangSmithSandbox(sandbox)
    if is_new:
        await asyncio.to_thread(_upload_skills_and_memory, backend)
    return backend


# A graph factory, rebuilt per run, so each thread gets its own sandbox:
# https://docs.langchain.com/langsmith/graph-rebuild#context-manager-factory
#
# The server also calls this for non-run requests (fetching the schema, drawing
# the graph, ...). For those, `runtime.execution_runtime` is None and we use an
# in-memory backend instead, so no sandbox is created just to describe the graph.
@contextlib.asynccontextmanager
async def make_graph(config: RunnableConfig, runtime: ServerRuntime):
    if runtime.execution_runtime:
        thread_id = config.get("configurable", {}).get("thread_id")
        backend = await _sandbox_backend(thread_id)
    else:
        backend = StateBackend()

    mail_client = MultiServerMCPClient({"mock-mail": MAIL_SERVER})
    mail_tools = await mail_client.get_tools()

    middleware = [CodeInterpreterMiddleware(ptc=["execute", "write_file"])]
    if _enable_search:
        middleware.append(build_async_research_middleware())

    yield create_deep_agent(
        model=strong_model,
        tools=[markdown_to_html] + mail_tools,
        system_prompt=SYSTEM_PROMPT,
        subagents=build_subagents(backend, mail_tools=mail_tools),
        skills=["/skills"],
        memory=["/AGENTS.md"],
        backend=backend,
        middleware=middleware,
        name="deep-sales-assistant",
    )

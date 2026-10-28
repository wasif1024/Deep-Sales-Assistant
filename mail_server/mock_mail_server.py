"""A local mock mail server, exposed as an MCP server over HTTP on port 5002.

Tools:
    mail_list_messages(query)            -> short summaries of inbox messages
    mail_read_message(message_id)        -> one full message
    mail_create_draft(to, subject, body) -> save a reply as a draft

start.sh starts this before langgraph dev, so the agent can find the tools
when it starts up.
"""

from __future__ import annotations

from mail_store import load_store, next_id, save_store
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mock-mail", host="127.0.0.1", port=5002)


@mcp.tool()
def mail_list_messages(query: str = "") -> list[dict]:
    """List inbox messages.

    Returns a summary (id, sender, subject, date, snippet) of each message,
    not the full text; use mail_read_message to open one. `query` is an
    optional case-insensitive search on subject and sender. Leave it empty to
    list everything.
    """
    store = load_store()
    q = query.strip().lower()
    summaries = []
    for m in store["inbox"]:
        if q and q not in f"{m.get('subject', '')} {m.get('from', '')}".lower():
            continue
        body = m.get("body", "")
        summaries.append(
            {
                "id": m.get("id"),
                "from": m.get("from"),
                "subject": m.get("subject"),
                "date": m.get("date"),
                "snippet": body[:140] + ("…" if len(body) > 140 else ""),
            }
        )
    return summaries


@mcp.tool()
def mail_read_message(message_id: str) -> dict:
    """Return one message in full (sender, subject, date, body) by its id."""
    for m in load_store()["inbox"]:
        if m.get("id") == message_id:
            return m
    return {"error": f"No message with id {message_id!r}."}


@mcp.tool()
def mail_create_draft(to: str, subject: str, body: str) -> dict:
    """Save a reply in the drafts folder. This never sends anything.

    The agent asks Jane to approve before calling this, so a draft is only
    saved once she's agreed.
    """
    store = load_store()
    draft = {
        "id": next_id(store["drafts"], "draft"),
        "to": to,
        "subject": subject,
        "body": body,
    }
    store["drafts"].append(draft)
    save_store(store)
    return {"status": "draft_saved", "draft_id": draft["id"], "to": to, "subject": subject}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

"""The main agent's specialist subagents.

- chinook-analyst: the only agent with database access. It learns the schema
  once and stores it in its own AGENTS.md. Adding a customer needs approval.
- inbox-manager: the only agent with the mail tools. Saving a draft needs
  approval.
- quote-reviewer: checks a quote's numbers before it goes out.

Why gated tools live only on subagents: deepagents always adds a
general-purpose subagent that inherits the main agent's tools. If
`add_customer` or `mail_create_draft` were on the main agent, that subagent
could call them and skip the approval step. Keeping them on these specialists
means every write goes through its approval gate.

The subagents are built by a function, not at import time, because
chinook-analyst's memory must be on the same backend (the thread's sandbox)
as the main agent's.

`GENRE_PROMPT` is used by the newsletter agent (newsletter_agent_graph.py).
"""

from __future__ import annotations

from deepagents import MemoryMiddleware
from deepagents.backends.protocol import BackendProtocol

from models import model, strong_model
from tools.sql import add_customer, introspect_schema, query_chinook

# Jane can approve, edit, or reject a gated call.
_APPROVAL = {"allowed_decisions": ["approve", "edit", "reject"]}


# The final paragraph matters most for smaller models, which tend to guess
# plural table names (e.g. "invoices" for Invoice).
ANALYST_PROMPT = """You are chinook-analyst, the Deep Sales Assistant's \
database specialist. No other agent can query the Chinook database.

Your memory (loaded automatically) holds your working notes and the schema. \
The essentials:
- Answer with exact figures from `query_chinook`.
- If your memory has no schema yet, call `introspect_schema` once and save \
the result to your memory.
- Call `add_customer` only to add someone who is truly new. Jane approves \
that write before it runs.

Use table and column names exactly as they appear in your memory or in the \
`introspect_schema` output. Chinook table names are singular (`Invoice`, \
not `invoices`). If a query fails with "no such table" or "no such column", \
re-check the schema with `introspect_schema` and retry. Never guess a name."""

INBOX_PROMPT = """You are inbox-manager, the Deep Sales Assistant's email \
specialist. No other agent can access Jane's mailbox.

Your tools:
- `mail_list_messages`: list inbox messages, optionally filtered by a search \
string.
- `mail_read_message`: open one message by its id.
- `mail_create_draft`: save a reply in the drafts folder. It never sends.

When asked to find or read mail, reply with a short summary (sender, subject, \
and what they want), not the raw message.

When asked to save a draft, call `mail_create_draft` with the recipient, \
subject, and body you were given. The call pauses on its own for Jane to \
approve, edit, or reject it, and that pause is the approval. Don't ask for \
permission in a message first. You can only create drafts; there is no send \
tool."""

REVIEWER_PROMPT = """You are quote-reviewer. You get a draft quote (line \
items with description, quantity, unit price, and line total, plus any \
discount and the grand total) and check it before it reaches the customer.

Check:
- Math: every quantity × unit price, and the grand total.
- Consistency: any stated discount is really applied, and no line is missing \
or counted twice.
- Sanity: unit prices look like catalogue prices (tracks are usually about \
$0.99), and no total is off by an order of magnitude.

Keep it short. Reply either "Looks correct" with one line of confirmation, \
or a brief list of specific fixes. Review only the numbers and terms; don't \
rewrite the customer email."""

GENRE_PROMPT = """You research one music genre for an online music store's \
weekly customer newsletter.

You'll be given one genre and a private folder for your notes.

Steps:
1. Run a few `internet_search` queries for recent news in the genre: new \
releases, artists getting attention, trends, and events.
2. Save the full, unedited results of every search to \
`/research/<genre>/sources.md` with write_file. Don't summarize or trim them. \
Keeping the raw results in a file keeps them out of the editor's context.
3. Write one newsletter segment based on what you found.

Your reply must be only the segment:
- a "## <Genre>" heading, then about 120 to 180 words
- engaging but accurate, naming specific artists and releases
- no raw search results (those belong in your file)"""


def build_subagents(
    backend: BackendProtocol,
    *,
    mail_tools: list,
) -> list[dict]:
    """Build the subagent specs, sharing the main agent's backend."""

    chinook_analyst = {
        "name": "chinook-analyst",
        "description": (
            "Database specialist. Looks up catalogue prices, customer records, "
            "purchase history, and sales metrics, and adds new customers "
            "(with Jane's approval). Send every database question here."
        ),
        "system_prompt": ANALYST_PROMPT,
        "tools": [query_chinook, introspect_schema, add_customer],
        "model": model,
        # Its own AGENTS.md on the shared backend, so the schema it saves on
        # one turn is there on the next.
        "middleware": [
            MemoryMiddleware(
                backend=backend,
                sources=["/agents/chinook-analyst/AGENTS.md"],
            )
        ],
        "interrupt_on": {"add_customer": _APPROVAL},
    }

    quote_reviewer = {
        "name": "quote-reviewer",
        "description": (
            "Checks a draft quote's math and pricing before it's sent. Send it "
            "the line items, discount, and total."
        ),
        "system_prompt": REVIEWER_PROMPT,
        "model": strong_model,
    }

    inbox_manager = {
        "name": "inbox-manager",
        "description": (
            "Email specialist. Finds and reads messages in Jane's inbox and "
            "saves reply drafts (with Jane's approval). Send all email work here."
        ),
        "system_prompt": INBOX_PROMPT,
        "tools": mail_tools,
        "model": model,
        "interrupt_on": {"mail_create_draft": _APPROVAL},
    }

    return [chinook_analyst, quote_reviewer, inbox_manager]

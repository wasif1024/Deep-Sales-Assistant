"""The mock mailbox: one JSON file with an `inbox` list and a `drafts` list.

Shared by mock_mail_server.py and send_to_inbox.py. It lets the assistant's
email features run locally with no Gmail account or OAuth, behind the same
kind of tools a real mail MCP server would offer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_STORE_PATH = _HERE / "mail_store.json"
_SEEDS_DIR = _HERE / "seeds"


def _empty_store() -> dict[str, list[dict[str, Any]]]:
    return {"inbox": [], "drafts": []}


def load_store() -> dict[str, list[dict[str, Any]]]:
    """Load the mailbox. On first use, fill the inbox from seeds/*.json."""
    if _STORE_PATH.exists():
        with _STORE_PATH.open(encoding="utf-8") as f:
            return json.load(f)

    store = _empty_store()
    for seed in sorted(_SEEDS_DIR.glob("*.json")):
        with seed.open(encoding="utf-8") as f:
            store["inbox"].append(json.load(f))
    save_store(store)
    return store


def save_store(store: dict[str, list[dict[str, Any]]]) -> None:
    """Write the mailbox to disk."""
    with _STORE_PATH.open("w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)


def next_id(messages: list[dict[str, Any]], prefix: str) -> str:
    """Return the next id in sequence, e.g. `msg-2` or `draft-1`."""
    n = 1 + sum(1 for m in messages if str(m.get("id", "")).startswith(prefix))
    return f"{prefix}-{n}"

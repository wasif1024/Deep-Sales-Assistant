"""Add a message to the mock inbox, as if a customer had just emailed Jane.

With no arguments, makes sure the sample emails in seeds/ are in the inbox.
With --from / --subject / --body, adds your own message. --reset empties the
inbox and drafts and reloads the samples.

Examples:
    uv run python mail_server/send_to_inbox.py
    uv run python mail_server/send_to_inbox.py --reset
    uv run python mail_server/send_to_inbox.py --from "a@b.example" \\
        --subject "Quote please" --body "Could I get 12 Jazz tracks?"
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from mail_store import _SEEDS_DIR, _empty_store, load_store, next_id, save_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a message to the mock inbox.")
    parser.add_argument("--from", dest="sender", help="Sender address.")
    parser.add_argument("--subject", help="Subject line.")
    parser.add_argument("--body", help="Message text.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Empty the inbox and drafts, then reload the samples from seeds/.",
    )
    args = parser.parse_args()

    if args.reset:
        store = _empty_store()
        for seed in sorted(_SEEDS_DIR.glob("*.json")):
            store["inbox"].append(json.loads(seed.read_text(encoding="utf-8")))
        save_store(store)
        print(f"Mailbox reset. The inbox has {len(store['inbox'])} message(s).")
        return

    store = load_store()  # also loads the samples on first use
    if args.sender or args.subject or args.body:
        msg = {
            "id": next_id(store["inbox"], "msg"),
            "from": args.sender or "unknown@example.com",
            "subject": args.subject or "(no subject)",
            "date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "body": args.body or "",
        }
        store["inbox"].append(msg)
        save_store(store)
        print(f"Added {msg['id']} from {msg['from']!r}.")
    else:
        print(f"The inbox has {len(store['inbox'])} message(s). Use --reset to start over.")


if __name__ == "__main__":
    main()

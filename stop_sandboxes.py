"""Stop this project's running sandboxes.

start.sh runs this on exit so you stop paying for sandbox compute right away,
instead of waiting for the idle timeout. It only touches sandboxes that agent.py
created (named "thread-*") and that are currently running.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values
from langsmith.sandbox import SandboxClient

# Read the key from this project's .env, not the shell environment, which might
# hold a LANGSMITH_API_KEY for a different workspace.
ENV_PATH = Path(__file__).resolve().parent / ".env"


def main() -> None:
    api_key = dotenv_values(ENV_PATH).get("LANGSMITH_API_KEY")
    client = SandboxClient(api_key=api_key)
    running = [
        sb
        for sb in client.list_sandboxes()
        if sb.name.startswith("thread-") and getattr(sb, "status", None) == "ready"
    ]
    for sb in running:
        try:
            client.stop_sandbox(sb.name)
            print(f"Stopped sandbox {sb.name}")
        except Exception as exc:
            print(f"Could not stop sandbox {sb.name}: {exc}")


if __name__ == "__main__":
    main()

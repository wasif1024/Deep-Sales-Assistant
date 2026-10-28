"""Chat models used by the agent and its subagents.

- `model`: fast and cheap, used by the narrow specialist subagents.
- `strong_model`: more capable, used by the main agent and harder subagents.

To use a different provider, change the model strings below (see
https://python.langchain.com/docs/integrations/chat/) and add its API key to `.env`.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=True)

from langchain.chat_models import init_chat_model

# Requires ANTHROPIC_API_KEY in .env
model = init_chat_model("anthropic:claude-haiku-4-5", timeout=300, max_retries=2)

strong_model = init_chat_model(
    "anthropic:claude-sonnet-5-5", timeout=300, max_retries=2
)

#!/usr/bin/env bash
# Start the chat UI on http://localhost:3000.
#
# LANGSMITH_API_KEY is read from the project's .env (override with ENV_FILE)
# and takes precedence over any value already set in the shell, so the UI
# can't pick up a key for a different LangSmith workspace.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d node_modules ]; then
    echo "Installing UI dependencies (pnpm install) ..."
    pnpm install
fi

ENV_FILE="${ENV_FILE:-$SCRIPT_DIR/../.env}"
# quiet: true stops dotenv printing a banner into the captured value.
LANGSMITH_KEY=$(node -e "const parsed = require('dotenv').config({path: '$ENV_FILE', override: true, quiet: true}).parsed || {}; process.stdout.write(parsed.LANGSMITH_API_KEY || '')")

if [ -z "$LANGSMITH_KEY" ]; then
    echo "Could not read LANGSMITH_API_KEY from $ENV_FILE." >&2
    exit 1
fi

echo "Starting the chat UI on http://localhost:3000 ..."
exec env -u LANGSMITH_API_KEY LANGSMITH_API_KEY="$LANGSMITH_KEY" pnpm run dev

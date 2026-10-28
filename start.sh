#!/usr/bin/env bash
# Start everything: the mock mail server, the chat UI, and langgraph dev.
# Ctrl-C stops them all and stops any running sandboxes.
# Run from the project root: ./start.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f .env ]; then
    echo "No .env found. Run: cp .env.example .env  and fill in your keys." >&2
    exit 1
fi
if ! grep -q '^LANGSMITH_API_KEY=.' .env || ! grep -q '^ANTHROPIC_API_KEY=.' .env; then
    echo "ANTHROPIC_API_KEY and LANGSMITH_API_KEY must be set in .env." >&2
    exit 1
fi
# The UI runs in the background, so check its requirements now rather than
# letting its error scroll past.
if ! command -v node >/dev/null 2>&1 || ! command -v pnpm >/dev/null 2>&1; then
    echo "The chat UI needs Node.js 20+ and pnpm (npm install -g pnpm)." >&2
    exit 1
fi

# Free the ports from a previous run.
for PORT in 5002 3000; do
    OLD_PID=$(lsof -ti ":$PORT" 2>/dev/null || true)
    if [ -n "$OLD_PID" ]; then
        echo "Port $PORT is in use (PID $OLD_PID); stopping it ..."
        kill $OLD_PID 2>/dev/null || true
        sleep 1
    fi
done

echo "Starting the mock mail server on http://127.0.0.1:5002 ..."
uv run python mail_server/mock_mail_server.py &
MAIL_PID=$!

ui/start.sh &
UI_PID=$!

# Runs on Ctrl-C, TERM, or normal exit. Every kill tolerates an already-dead
# process: Ctrl-C often kills the children first, and under `set -e` a failed
# kill would end cleanup before the sandboxes are stopped.
cleanup() {
    kill "$MAIL_PID" "$UI_PID" 2>/dev/null || true
    # pnpm starts `next dev` as a child process, so stop it directly too.
    pkill -f "next dev" 2>/dev/null || true
    wait "$MAIL_PID" "$UI_PID" 2>/dev/null || true
    echo "Stopping any running sandboxes ..."
    uv run python stop_sandboxes.py || true
}
trap cleanup EXIT INT TERM

for i in $(seq 1 10); do
    if curl -s --max-time 1 http://127.0.0.1:5002/ >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

echo
echo "Once langgraph dev is up, open:"
echo "  http://localhost:3000/?apiUrl=http://localhost:2024&assistantId=agent"
echo

# Each background newsletter task holds a worker slot for its whole run. With
# the default of 1 slot, the main chat couldn't run while one was in progress.
uv run langgraph dev --n-jobs-per-worker 10

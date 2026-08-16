#!/usr/bin/env bash
# One command for Operational Intelligence: API + console together.
#
#   ./ops/dev.sh          → http://localhost:3010
#
# Why this exists: the API and the console were started separately and lived for
# days, so a process could outlive the .env that configured it — that is exactly
# how the console ended up talking to a Grafana MCP server the .env had already
# moved away from. Here both are children of this script, `--reload` picks up
# backend edits, and the trap kills the whole process group on Ctrl-C so nothing
# is left running with stale configuration.
set -euo pipefail
cd "$(dirname "$0")/.."

API_PORT="${API_PORT:-8010}"
WEB_PORT="${WEB_PORT:-3010}"

trap 'kill 0' EXIT INT TERM

if [ ! -x .venv/bin/uvicorn ]; then
  echo "!! .venv/bin/uvicorn not found — create the venv first" >&2
  exit 1
fi

echo "→ API     http://localhost:$API_PORT  (reloads on save)"
echo "→ console http://localhost:$WEB_PORT  (reloads on save)"
echo

.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" --reload &

# The Temporal worker executes the loop when a durable workflow is dispatched.
# Without it the API hands work to Temporal and nothing ever picks it up.
if nc -z localhost "${TEMPORAL_PORT:-7234}" 2>/dev/null; then
  echo "→ worker  connected to Temporal :${TEMPORAL_PORT:-7234}"
  .venv/bin/python -m app.workflows.worker &
else
  echo "→ worker  skipped (no Temporal on :${TEMPORAL_PORT:-7234}) — the API runs the loop in-process"
fi
( cd frontend && GENESIS_API_URL="http://127.0.0.1:$API_PORT" npx next dev -p "$WEB_PORT" ) &

wait

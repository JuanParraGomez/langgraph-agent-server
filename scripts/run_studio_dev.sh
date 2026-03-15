#!/usr/bin/env bash
# scripts/run_studio_dev.sh
# Starts the LangGraph Studio-compatible server in DEV mode (local, hot-reload).
# Port: 8123  |  Does NOT touch 8070 or its Docker container.
#
# Usage:
#   ./scripts/run_studio_dev.sh
#   ./scripts/run_studio_dev.sh --port 2024
#
# Studio URL after start:
#   https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:8123

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PORT="${STUDIO_PORT:-8123}"
HOST="${STUDIO_HOST:-127.0.0.1}"

if [ -f /home/juan/.config/langsmith/env.sh ]; then
  # shellcheck disable=SC1090
  . /home/juan/.config/langsmith/env.sh
fi

# Activate venv if present
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  . .venv/bin/activate
fi

# Ensure LANGSMITH_PROJECT for Studio is distinct
export LANGSMITH_PROJECT="${LANGSMITH_STUDIO_PROJECT:-langgraph-agent-server-studio}"
export LANGCHAIN_PROJECT="$LANGSMITH_PROJECT"

echo "=== Starting LangGraph Studio server on ${HOST}:${PORT} ==="
echo "=== Studio URL: https://smith.langchain.com/studio/?baseUrl=http://${HOST}:${PORT} ==="
echo "=== LangSmith project: $LANGSMITH_PROJECT ==="
echo ""

exec langgraph dev \
  --host "$HOST" \
  --port "$PORT" \
  --config langgraph.json \
  --no-browser \
  "$@"

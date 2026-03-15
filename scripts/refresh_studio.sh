#!/usr/bin/env bash
# scripts/refresh_studio.sh
# Refresh / reload the LangGraph Studio server.
#
# REFRESH STRATEGY:
# ─────────────────────────────────────────────────────────────────────────
# Case 1 – New assistant on an EXISTING graph
#   LangGraph Studio manages assistants automatically via its internal DB.
#   Creating a new assistant (via POST /assistants on port 8123) does NOT
#   require any server restart. This happens automatically.
#
# Case 2 – STRUCTURAL change to a graph (new node, edge, or new graph)
#   langgraph dev does NOT hot-reload compiled graph objects at module level.
#   A restart of ONLY the Studio server is needed.
#   This script does exactly that — it restarts ONLY langgraph-studio-server
#   and does NOT touch langgraph-agent-server (8070).
#
# Case 3 – New graph added to langgraph.json
#   Same as Case 2: restart Studio server only.
# ─────────────────────────────────────────────────────────────────────────
#
# Usage:
#   ./scripts/refresh_studio.sh               # Docker mode (default)
#   ./scripts/refresh_studio.sh --local       # Kill and restart local dev process

set -euo pipefail

MODE="${1:-}"

CONTAINER="langgraph-studio-server"
PORT="${STUDIO_PORT:-8123}"
HOST="${STUDIO_HOST:-127.0.0.1}"

if [ "$MODE" = "--local" ]; then
  echo "=== Refreshing Studio dev server (local mode) ==="
  OLD_PID=$(pgrep -f "langgraph dev.*8123" 2>/dev/null || true)
  if [ -n "$OLD_PID" ]; then
    echo "Stopping PID $OLD_PID..."
    kill "$OLD_PID"
    sleep 2
  fi
  ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  cd "$ROOT_DIR"
  exec bash scripts/run_studio_dev.sh
else
  echo "=== Refreshing Studio Docker container ($CONTAINER) ==="
  echo "=== NOTE: 8070 container is NOT affected ==="
  if docker restart "$CONTAINER" 2>/dev/null; then
    echo "Restarted $CONTAINER"
    sleep 3
    HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/ok" --max-time 10 2>/dev/null || echo "000")
    echo "Health check after restart: HTTP $HTTP_CODE"
  else
    echo "Docker not available or container not found. Use --local mode:"
    echo "  ./scripts/refresh_studio.sh --local"
  fi
fi

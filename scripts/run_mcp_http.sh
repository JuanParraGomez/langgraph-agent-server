#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "MCP HTTP endpoint exposed at /mcp/tools and /mcp/tools/{tool_name} via FastAPI"
uvicorn app.main:app --host "${AGENT_SERVER_HOST:-127.0.0.1}" --port "${AGENT_SERVER_PORT:-8070}"

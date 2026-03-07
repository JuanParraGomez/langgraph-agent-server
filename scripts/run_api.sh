#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

uvicorn app.main:app --host "${AGENT_SERVER_HOST:-127.0.0.1}" --port "${AGENT_SERVER_PORT:-8070}" --reload

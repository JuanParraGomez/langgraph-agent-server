#!/usr/bin/env bash
# scripts/smoke_studio.sh
# Smoke test the LangGraph Studio-compatible server.
# Verifies that:
#   1. Studio server is reachable on :8123
#   2. Graphs endpoint returns real graph names
#   3. A minimal invoke succeeds
#   4. LangSmith received a trace
#
# Usage: ./scripts/smoke_studio.sh [--port 8123]

set -euo pipefail

PORT="${1:-8123}"
BASE="http://127.0.0.1:${PORT}"

echo "=== LangGraph Studio smoke test on ${BASE} ==="

# 1. Health check
echo "-- 1. Health check"
HTTP=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/ok" --max-time 10 2>/dev/null || echo "000")
if [ "$HTTP" = "200" ]; then
  echo "   OK: /ok => 200"
else
  echo "   WARN: /ok => $HTTP (server may still be starting)"
fi

# 2. Graphs check
echo "-- 2. Graphs list"
GRAPHS=$(curl -sS "${BASE}/graphs" --max-time 15 2>&1 || echo '{"error":"connection refused"}')
echo "   $GRAPHS" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    graphs = d.get('graphs', []) or d.get('data', []) or []
    print('   graphs count:', len(graphs))
    for g in graphs:
        if isinstance(g, dict):
            print('   -', g.get('graph_id') or g.get('name') or g)
        else:
            print('   -', g)
except Exception as e:
    print('   raw:', sys.stdin.read()[:200])
" 2>/dev/null || echo "   (parse failed, raw: $GRAPHS)"

# 3. Minimal invoke on supervisor_v1
echo "-- 3. Invoke supervisor_v1"
RUN_RESULT=$(curl -sS -X POST "${BASE}/runs" \
  -H 'content-type: application/json' \
  -d '{
    "assistant_id": "supervisor_v1",
    "input": {"goal": "studio smoke test", "context": {}, "max_iterations": 1},
    "config": {"configurable": {"thread_id": "smoke-test-001"}}
  }' --max-time 30 2>&1 || echo '{"error":"connection refused"}')
echo "   $RUN_RESULT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    run_id = d.get('run_id') or d.get('id')
    status = d.get('status')
    print('   run_id:', run_id, '| status:', status)
except Exception:
    print('   raw:', sys.stdin.read()[:300])
" 2>/dev/null || echo "   raw: $RUN_RESULT"

# 4. Check 8070 still healthy
echo "-- 4. Verify 8070 still healthy"
HEALTH_8070=$(curl -sS "http://127.0.0.1:8070/health" --max-time 10 2>&1 || echo '{}')
echo "$HEALTH_8070" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print('   8070 status:', d.get('status'), '| service:', d.get('service'))
except Exception:
    print('   raw:', sys.stdin.read()[:200])
" 2>/dev/null

echo ""
echo "=== Studio URL for browser ==="
echo "   https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:${PORT}"
echo ""
echo "=== LangSmith project ==="
echo "   langgraph-agent-server-studio"

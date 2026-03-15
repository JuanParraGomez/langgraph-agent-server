#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8070}"
OUT_DIR="${1:-$(cat /tmp/ui-factory-batch.latest)}"

if [[ ! -d "$OUT_DIR" ]]; then
  echo "missing_out_dir: $OUT_DIR" >&2
  exit 1
fi

echo "out_dir=$OUT_DIR"

for name in easy hard very_hard; do
  out_file="$OUT_DIR/$name.out.json"
  if [[ ! -f "$out_file" ]]; then
    echo "--- $name"
    echo "missing_output"
    continue
  fi
  run_id="$(python3 - "$out_file" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
print(data["run"]["run_id"])
PY
)"
  echo "--- $name run_id=$run_id"
  curl -fsS "$API_BASE_URL/runs/$run_id"
  echo
done

echo "--- latest_log"
latest="$(ls -t /home/juan/Documents/langgraph-agent-server/data/logs/*.log 2>/dev/null | head -n1 || true)"
echo "$latest"
if [[ -n "$latest" ]]; then
  tail -n 120 "$latest"
fi

#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT_FILE="${1:-/tmp/ui-factory-batch.latest}"

if [[ ! -f "$RUN_ROOT_FILE" ]]; then
  echo "missing_run_root_file: $RUN_ROOT_FILE" >&2
  exit 1
fi

RUN_ROOT="$(cat "$RUN_ROOT_FILE")"

if [[ ! -d "$RUN_ROOT" ]]; then
  echo "missing_run_root_dir: $RUN_ROOT" >&2
  exit 1
fi

for f in "$RUN_ROOT"/*.out.json; do
  if [[ ! -f "$f" ]]; then
    continue
  fi
  echo "--- $f"
  python3 - "$f" <<'PY'
import json
import sys

path = sys.argv[1]
data = json.load(open(path))
run = data["run"]
print("run_id=", run["run_id"])
print("status=", run["status"])
print("goal=", run["requested_goal"])
PY
done

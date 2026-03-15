#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8070}"
OUT_DIR="${OUT_DIR:-/tmp/ui-factory-batch-$(date +%Y%m%d-%H%M%S)}"
TENANT_ID="${TENANT_ID:-tenant-ui-factory-batch}"

mkdir -p "$OUT_DIR"

health() {
  curl -fsS "$API_BASE_URL/health" >/dev/null
}

post_run() {
  local name="$1"
  local payload_file="$2"
  local out_file="$OUT_DIR/$name.out.json"
  curl -fsS -X POST "$API_BASE_URL/run/ui-factory" \
    -H "Content-Type: application/json" \
    --data @"$payload_file" > "$out_file"
  python3 - "$name" "$out_file" <<'PY'
import json, sys
name = sys.argv[1]
path = sys.argv[2]
data = json.load(open(path))
run = data["run"]
print(f"{name}: run_id={run['run_id']} status={run['status']} graph={run['selected_graph']}")
PY
}

health

cat > "$OUT_DIR/easy.json" <<EOF
{
  "goal": "crea una landing simple para ventas por region con titulo, subtitulo, tres cards, una tabla corta y un CTA final usando datos simulados",
  "app_name": "Sales Landing Batch",
  "slug": "sales-landing-batch",
  "project_type": "long_lived",
  "deploy": true,
  "publish_memory": true,
  "tenant_id": "$TENANT_ID",
  "max_iterations": 4,
  "context": {
    "priority": "easy"
  }
}
EOF

cat > "$OUT_DIR/hard.json" <<EOF
{
  "goal": "crea una app para ver ventas por region con filtros, graficos, tabla, drill-down por region, navegacion y datos simulados en Next.js",
  "app_name": "Sales Region Analyzer Batch",
  "slug": "sales-region-analyzer-batch",
  "project_type": "long_lived",
  "deploy": true,
  "publish_memory": true,
  "tenant_id": "$TENANT_ID",
  "max_iterations": 5,
  "context": {
    "priority": "hard",
    "framework": "nextjs"
  }
}
EOF

cat > "$OUT_DIR/very_hard.json" <<EOF
{
  "goal": "crea una aplicacion analitica multipagina para ventas, inventario y cumplimiento comercial con dashboard ejecutivo, filtros globales, tablas, comparativos por region, vistas por producto, resumen de alertas, exportes simulados, detalle por vendedor y datos simulados en Next.js",
  "app_name": "Commercial Ops Control Center Batch",
  "slug": "commercial-ops-control-center-batch",
  "project_type": "long_lived",
  "deploy": true,
  "publish_memory": true,
  "tenant_id": "$TENANT_ID",
  "max_iterations": 6,
  "context": {
    "priority": "very_hard",
    "framework": "nextjs"
  }
}
EOF

post_run easy "$OUT_DIR/easy.json"
post_run hard "$OUT_DIR/hard.json"
post_run very_hard "$OUT_DIR/very_hard.json"

printf "%s\n" "$OUT_DIR" > /tmp/ui-factory-batch.latest
echo "out_dir=$OUT_DIR"

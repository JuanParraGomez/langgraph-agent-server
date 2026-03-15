# langgraph-agent-server

Servicio nuevo y desacoplado para orquestar tareas complejas con patrón supervisor + subagentes sobre LangGraph, expuesto por FastAPI + herramientas MCP HTTP.

## Objetivo

`langgraph-agent-server` centraliza orquestación stateful para:

- investigación profunda
- tareas multi-paso
- plan + ejecución + revisión
- combinación de RAG + terminal + scripts + síntesis

No reemplaza ni modifica:

- `rag-server`
- `CanonDock`
- `celery-server`
- `terminal-tools`

## Arquitectura

Patrón:

`cliente/OpenClaw -> langgraph-agent-server -> terminal-tools / rag-server / celery-server`

Separación de responsabilidades:

- `terminal-tools`: operaciones terminal/CLI
- `rag-server`: retrieval/contexto documental
- `celery-server`: operaciones de scripts `.sh`
- `langgraph-agent-server`: planificación, delegación, iteración y síntesis

## Agentes V1

- `supervisor_agent`: planifica, decide delegación y controla iteraciones
- `research_agent`: consulta `rag-server`
- `memory_review_agent`: revisa memoria/versiones previas en `rag-server`
- `prompt_engineer_agent`: genera paquetes de prompts para tareas de código
- `terminal_agent`: delega subtareas operativas a `terminal-tools`
- `script_ops_agent`: delega `validate/create/run/get_logs` a `celery-server`
- `synthesis_agent`: consolida resultados y entrega salida final limpia

## Graph V1 (LangGraph)

`supervisor -> route -> {research|terminal|script_ops}* -> synthesis`

- estado persistente por corrida (`run_id`)
- iteración limitada por `max_iterations`
- fallback limpio si LangGraph no está disponible (servicio no cae)

Flujo adicional:

`prompt_workflow_v1 = memory_review_agent -> prompt_engineer_agent -> publish to rag-server`

- usa `DeepSeek` para razonamiento/prompting
- consulta memoria similar y versiones previas en `rag-server`
- publica el aprendizaje final en `rag-server`

Flujo adicional:

`ui_factory_v1 = discover -> plan -> data strategy -> tool strategy -> build/update -> validate -> git publish -> hapi public-plane -> rag memory`

- `langgraph-agent-server` sigue siendo el único orquestador
- `terminal-tools` ejecuta edición/build/git
- `hapi` resuelve bootstrap de proyecto, estado público y Coolify handoff
- `rag-server` se usa para discovery y memoria final de la UI

## API HTTP

- `GET /health`
- `GET /capabilities`
- `GET /agents`
- `GET /graphs`
- `POST /run/complex`
- `POST /run/plan`
- `POST /run/prompt-workflow`
- `POST /run/ui-factory`
- `POST /run/research`
- `POST /run/terminal`
- `POST /run/script-ops`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/logs`

## MCP Tools (HTTP)

Expuestas en:

- `GET /mcp/tools`
- `POST /mcp/tools/{tool_name}`

Tools incluidas:

1. `agent_health`
2. `agent_list_capabilities`
3. `agent_run_complex_task`
4. `agent_plan_task`
5. `agent_run_prompt_workflow`
6. `agent_run_ui_factory`
7. `agent_run_research`
8. `agent_run_terminal_subtask`
9. `agent_run_script_ops_subtask`
10. `agent_summarize_findings`
11. `agent_get_run`
12. `agent_get_run_logs`
13. `agent_list_graphs`
14. `agent_list_agents`

## Variables de entorno y env global

El servicio carga configuración desde `GLOBAL_ENV_PATH` (por defecto `/home/juan/Documents/.env`) usando `python-dotenv`.

No depende del `.env` local del repo.

Ver plantilla en `.env.example`.

### LangSmith obligatorio (persistente en VM)

Este repo deja LangSmith **activo por defecto** y la app falla al arrancar si falta configuración crítica (excepto runtime de `pytest`).

Variables requeridas:

- `LANGSMITH_ENABLED=true`
- `LANGSMITH_TRACING=true`
- `LANGSMITH_ENFORCE=true`
- `LANGSMITH_PROJECT=langgraph-agent-server` (o el proyecto que quieras)
- `LANGSMITH_WORKSPACE_ID=ec45ad58-425c-4956-ada0-2cba64190c20`
- `LANGSMITH_ENDPOINT=https://api.smith.langchain.com`
- `LANGSMITH_API_KEY` (secreto, nunca en archivos versionados)

Persistencia recomendada en esta VM:

1. Crear `/home/juan/.config/langsmith/langsmith.env` (sin secreto).
2. Mantener `LANGSMITH_API_KEY` en `/home/juan/Documents/.env` o en otro secreto privado del host.
3. `docker-compose.yml` ya referencia `env_file: /home/juan/.config/langsmith/langsmith.env`.

Ejemplo de archivo persistente no secreto:

```bash
mkdir -p /home/juan/.config/langsmith
cat >/home/juan/.config/langsmith/langsmith.env <<'EOF'
LANGSMITH_ENABLED=true
LANGSMITH_TRACING=true
LANGSMITH_ENFORCE=true
LANGSMITH_PROJECT=langgraph-agent-server
LANGSMITH_WORKSPACE_ID=ec45ad58-425c-4956-ada0-2cba64190c20
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
EOF
```

## Backends externos configurables

- `TERMINAL_TOOLS_BASE_URL`
- `TERMINAL_TOOLS_MCP_URL`
- `RAG_SERVER_BASE_URL`
- `RAG_SERVER_MCP_URL`
- `CELERY_SERVER_BASE_URL`
- `CELERY_SERVER_MCP_URL`
- `HAPI_BASE_URL`
- `HAPI_MCP_URL`
- `UI_FACTORY_REPO_ROOT`
- `UI_FACTORY_REPO_URL`
- `UI_FACTORY_DEFAULT_BRANCH`

Si algún backend/provider no está disponible, se reporta en capacidades como `available: false` sin romper el servicio.

## Persistencia

- SQLite: `data/runs/runs.db`
- Trazas por corrida: `data/logs/{run_id}.log`

Cada run guarda:

- `run_id`, timestamps, `status`
- `requested_goal`
- `selected_graph`, `selected_agents`
- `providers_used`, `external_tools_used`
- `summary`, `result`, `error`, `logs_path`

Estados:

- `pending`
- `running`
- `succeeded`
- `failed`
- `cancelled`

## Instalación y ejecución

```bash
cd /home/juan/Documents/langgraph-agent-server
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Correr API:

```bash
./scripts/run_api.sh
```

Correr modo MCP HTTP:

```bash
./scripts/run_mcp_http.sh
```

## Ejecución con Docker

Build y run:

```bash
cd /home/juan/Documents/langgraph-agent-server
docker compose up --build -d
```

Ver logs:

```bash
docker compose logs -f langgraph-agent-server
```

Parar:

```bash
docker compose down
```

Notas:

- El contenedor monta `/home/juan/Documents/.env` como `/host_global.env`.
- `GLOBAL_ENV_PATH` se define a `/host_global.env`.
- Se usa `host.docker.internal` para llegar a `terminal-tools`, `rag-server`, `celery-server` que corren en host.
- LangSmith queda persistido vía `/home/juan/.config/langsmith/langsmith.env` + `LANGSMITH_API_KEY` en entorno privado del host.

Reiniciar servicio (runtime docker-compose actual):

```bash
cd /home/juan/Documents/langgraph-agent-server
docker compose up -d --build
docker compose logs -f langgraph-agent-server
```

> Descubrimiento de runtime: actualmente este proyecto corre en contenedor Docker (`uvicorn app.main:app --port 8070`) desde `/home/juan/Documents/langgraph-agent-server`, y además existe un proceso manual de pruebas en `:8071`.

## LangGraph Studio (server paralelo en puerto 8123)

Studio permite visualizar los grafos reales del proyecto, depurar invocaciones e inspectar estado de threads.

### URL de acceso

```
https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:8123
```

Grafos disponibles:
- `supervisor_v1` — grafo principal de orquestación multi-agente
- `ui_factory_v1` — grafo de generación de UI (macro-nodos)

### Arranque

```bash
# Opción A: systemd (recomendado, arranca con el usuario)
systemctl --user start langgraph-studio
systemctl --user status langgraph-studio

# Opción B: script de dev (con hot-log en terminal)
./scripts/run_studio_dev.sh

# Opción C: Docker (producción)
docker compose -f docker-compose.studio.yml up -d
```

### Refresh / actualización

| Tipo de cambio | Requiere reinicio |
|---|---|
| Nuevo assistant sobre grafo existente | **No** (automático) |
| Cambio estructural en un grafo | **Sí** (solo Studio) |
| Nuevo grafo en langgraph.json | **Sí** (solo Studio) |

```bash
# Reiniciar Studio sin tocar 8070:
systemctl --user restart langgraph-studio

# O con Docker:
docker restart langgraph-studio-server
```

Ver estrategia completa en [`docs/STUDIO_REFRESH_STRATEGY.md`](docs/STUDIO_REFRESH_STRATEGY.md).

### LangSmith para Studio

El servidor Studio envía trazas al proyecto `langgraph-agent-server-studio` (separado de `langgraph-agent-server`).

### Smoke test

```bash
bash scripts/smoke_studio.sh
```

---

## Verificación de trazas LangSmith

Prueba mínima:

```bash
cd /home/juan/Documents/langgraph-agent-server
python scripts/check_langsmith.py
```

Resultado esperado: `LANGSMITH_PROBE_OK` y `run_id/trace_id`.

También puedes validar una ejecución real:

```bash
curl -sS -X POST http://127.0.0.1:8070/run/plan \
  -H 'content-type: application/json' \
  -d '{"goal":"langsmith smoke test","context":{"source":"check_langsmith"}}'
```

Si usas Python `<3.11` con flujos async/streaming, actualiza a `>=3.11` para evitar comportamiento no soportado.

## Ejemplos curl

Health:

```bash
curl -sS http://127.0.0.1:8070/health
```

Plan:

```bash
curl -sS -X POST http://127.0.0.1:8070/run/plan \
  -H 'content-type: application/json' \
  -d '{"goal":"investiga logs y valida script de backup","context":{}}'
```

Complex run:

```bash
curl -sS -X POST http://127.0.0.1:8070/run/complex \
  -H 'content-type: application/json' \
  -d '{"goal":"usa RAG, terminal y scripts para diagnosticar fallo en backup nocturno","context":{},"max_iterations":3}'
```

MCP tool call:

```bash
curl -sS -X POST http://127.0.0.1:8070/mcp/tools/agent_run_research \
  -H 'content-type: application/json' \
  -d '{"question":"resumen de estrategia de backups","top_k":5}'
```

Prompt workflow:

```bash
curl -sS -X POST http://127.0.0.1:8070/run/prompt-workflow \
  -H 'content-type: application/json' \
  -d '{
    "goal":"crear un agente para mejorar prompts de codigo y dejar flujo barato",
    "tenant_id":"tenant-stack-probe",
    "agent_name":"prompt_optimizer_agent",
    "current_version":"v1",
    "publish_learning":true,
    "context":{"complexity":4}
  }'
```

UI factory:

```bash
curl -sS -X POST http://127.0.0.1:8070/run/ui-factory \
  -H 'content-type: application/json' \
  -d '{
    "goal":"crea una app para ver ventas por region con filtros y graficos",
    "tenant_id":"tenant-ui",
    "app_name":"Sales Region UI",
    "project_type":"long_lived",
    "deploy":true,
    "publish_memory":true
  }'
```

## Estructura

```text
langgraph-agent-server/
  app/
    api/
    core/
    agents/
    graphs/
    services/
    adapters/
    mcp_server/
    storage/
    models/
    prompts/
  tests/
  data/
  scripts/
  README.md
  pyproject.toml
  .env.example
```

## Extensión

- agregar agentes: `app/agents/`
- extender grafo: `app/graphs/complex_graph.py`
- agregar tools MCP: `app/mcp_server/tool_registry.py`
- integrar nuevos backends: `app/adapters/`

Docs de integración:
- `docs/UI_FACTORY_ARCHITECTURE.md`
- `docs/LANGGRAPH_HAPI_CONTRACT.md`
- `docs/PUBLIC_APP_REGISTRY.md`
- `docs/FAILURE_AND_RETRY_MODEL.md`
- `docs/AGENT_OBSERVABILITY_RULES.md`

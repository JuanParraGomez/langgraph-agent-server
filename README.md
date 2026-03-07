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

## API HTTP

- `GET /health`
- `GET /capabilities`
- `GET /agents`
- `GET /graphs`
- `POST /run/complex`
- `POST /run/plan`
- `POST /run/prompt-workflow`
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
6. `agent_run_research`
7. `agent_run_terminal_subtask`
8. `agent_run_script_ops_subtask`
9. `agent_summarize_findings`
10. `agent_get_run`
11. `agent_get_run_logs`
12. `agent_list_graphs`
13. `agent_list_agents`

## Variables de entorno y env global

El servicio carga configuración desde `GLOBAL_ENV_PATH` (por defecto `/home/juan/Documents/.env`) usando `python-dotenv`.

No depende del `.env` local del repo.

Ver plantilla en `.env.example`.

## Backends externos configurables

- `TERMINAL_TOOLS_BASE_URL`
- `TERMINAL_TOOLS_MCP_URL`
- `RAG_SERVER_BASE_URL`
- `RAG_SERVER_MCP_URL`
- `CELERY_SERVER_BASE_URL`
- `CELERY_SERVER_MCP_URL`

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

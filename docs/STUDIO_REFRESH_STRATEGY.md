# LangGraph Studio – Refresh Strategy

## Overview

The Studio server (port 8123) is a **LangGraph API dev server** running in parallel with the
production server on 8070. The two runtimes are fully isolated — Studio can crash, restart or be
rebuilt **without any impact on 8070**.

---

## Two types of updates

### Case 1 — New assistant on an existing graph (automatic)

When a new assistant is created (via the Studio UI or `POST /assistants` on 8123), the Studio
server stores it in its own in-memory DB and makes it visible **immediately**. No restart needed.

**Examples**: new assistant with different config/system prompt on `supervisor_v1` or `ui_factory_v1`.

### Case 2 — Structural graph change or new graph (requires Studio restart)

When the graph's structure changes (new node, edge, or a new graph is added to `langgraph.json`),
`langgraph dev` cannot hot-reload the compiled graph objects. A Studio server restart is required.

**The restart only restarts the Studio container / process. Port 8070 is untouched.**

---

## Refresh commands

### Local dev (manual process)

```bash
# Stop existing Studio process, then restart:
./scripts/refresh_studio.sh --local

# Or just restart the systemd user service:
systemctl --user restart langgraph-studio
```

### Docker (production)

```bash
# Rebuild + restart Studio container only (8070 untouched):
docker compose -f docker-compose.studio.yml up -d --build

# Or just restart without rebuild (for config-only changes):
docker restart langgraph-studio-server
```

---

## How to add a new graph to Studio

1. Create the compiled graph in `app/studio/graphs.py`:

```python
def _build_my_new_graph():
    g = StateGraph(MyState)
    # ... add nodes and edges ...
    return g.compile()  # no checkpointer — LangGraph API manages persistence

my_new_graph = _build_my_new_graph()
```

2. Register it in `langgraph.json`:

```json
{
  "graphs": {
    "my_new_graph_v1": "./app/studio/graphs.py:my_new_graph"
  }
}
```

3. Restart Studio server (Case 2):

```bash
systemctl --user restart langgraph-studio
```

---

## Summary table

| Change type | 8070 impact | Studio restart needed |
|---|---|---|
| New assistant config on existing graph | None | No (automatic) |
| New graph added to langgraph.json | None | Yes |
| Node/edge change in existing graph | None | Yes |
| New env var added | None | Yes (for Studio) |
| LangSmith project name change | None | Yes (for Studio) |

---

## Studio URL

```
https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:8123
```

Replace `127.0.0.1` with your VPS host / public IP if accessing remotely.

---

## Service management

```bash
# Start
systemctl --user start langgraph-studio

# Stop
systemctl --user stop langgraph-studio

# Restart
systemctl --user restart langgraph-studio

# Status + logs
systemctl --user status langgraph-studio
journalctl --user -u langgraph-studio -f

# Enable on boot (already done)
systemctl --user enable langgraph-studio
```

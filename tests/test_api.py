from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient


def _reset_caches() -> None:
    from app.core.settings import get_settings
    from app.services.container import (
        get_capabilities_service,
        get_celery_adapter,
        get_provider_service,
        get_rag_adapter,
        get_research_agent,
        get_run_service,
        get_script_ops_agent,
        get_store,
        get_supervisor_agent,
        get_synthesis_agent,
        get_terminal_adapter,
        get_terminal_agent,
    )

    get_settings.cache_clear()
    get_store.cache_clear()
    get_provider_service.cache_clear()
    get_terminal_adapter.cache_clear()
    get_rag_adapter.cache_clear()
    get_celery_adapter.cache_clear()
    get_supervisor_agent.cache_clear()
    get_research_agent.cache_clear()
    get_terminal_agent.cache_clear()
    get_script_ops_agent.cache_clear()
    get_synthesis_agent.cache_clear()
    get_run_service.cache_clear()
    get_capabilities_service.cache_clear()


def test_health_and_mcp_tools(tmp_path: Path, monkeypatch):
    os.environ["AGENT_DATA_DIR"] = str(tmp_path / "data")
    _reset_caches()

    from app.main import app
    from app.services.container import get_capabilities_service

    caps = get_capabilities_service()

    async def fake_backend_health():
        return {
            "terminal_tools": {"available": False},
            "rag_server": {"available": False},
            "celery_server": {"available": False},
        }

    monkeypatch.setattr(caps, "backend_health", fake_backend_health)

    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["service"] == "langgraph-agent-server"

    tools = client.get("/mcp/tools")
    assert tools.status_code == 200
    names = [t["name"] for t in tools.json()["tools"]]
    assert "agent_run_complex_task" in names


def test_run_plan_endpoint(tmp_path: Path):
    os.environ["AGENT_DATA_DIR"] = str(tmp_path / "data")
    _reset_caches()

    from app.main import app

    client = TestClient(app)
    resp = client.post("/run/plan", json={"goal": "investiga logs y revisa script de backup", "context": {}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["graph"] == "supervisor_v1"
    assert "selected_agents" in body["plan"]

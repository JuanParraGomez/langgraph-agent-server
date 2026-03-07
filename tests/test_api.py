from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient


def _reset_caches() -> None:
    from app.core.settings import get_settings
    from app.services.container import (
        get_capabilities_service,
        get_celery_adapter,
        get_deepseek_service,
        get_memory_review_agent,
        get_provider_service,
        get_prompt_engineer_agent,
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
    get_deepseek_service.cache_clear()
    get_terminal_adapter.cache_clear()
    get_rag_adapter.cache_clear()
    get_celery_adapter.cache_clear()
    get_supervisor_agent.cache_clear()
    get_research_agent.cache_clear()
    get_memory_review_agent.cache_clear()
    get_terminal_agent.cache_clear()
    get_script_ops_agent.cache_clear()
    get_synthesis_agent.cache_clear()
    get_prompt_engineer_agent.cache_clear()
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
    assert "agent_run_prompt_workflow" in names


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


def test_run_prompt_workflow_endpoint(tmp_path: Path, monkeypatch):
    os.environ["AGENT_DATA_DIR"] = str(tmp_path / "data")
    _reset_caches()

    from app.main import app
    from app.services.container import get_deepseek_service, get_memory_review_agent, get_rag_adapter

    async def fake_memory_run(goal: str, tenant_id: str | None = None, context: dict | None = None):
        return {
            "ok": True,
            "source": "rag-server",
            "data": {
                "answer": "Found a similar workflow",
                "sources": [
                    {
                        "chunk_id": "c1",
                        "score": 0.9,
                        "text": "old workflow",
                        "metadata": {
                            "document_id": "doc1",
                            "title": "agent memory",
                            "workflow_version": "v2",
                            "artifact_type": "agent_learning",
                        },
                    }
                ],
            },
        }

    async def fake_upload_learning(**kwargs):
        return {
            "document_id": "learning-doc",
            "tenant_id": kwargs["tenant_id"],
            "chunks_indexed": 1,
            "metadata": kwargs["metadata"],
        }

    async def fake_generate_prompt_package(**kwargs):
        return {
            "workflow": "copilot_plan_then_codex",
            "rationale": "complex code flow",
            "planning_prompt": "plan prompt",
            "execution_prompt": "execution prompt",
            "validation_prompt": "validation prompt",
            "rag_learning_text": "learning text",
            "recommended_sequence": [{"step": 1, "tool": "terminal-tools", "endpoint": "/run/copilot-plan"}],
            "provider_used": "deepseek",
            "model_used": "deepseek-chat",
        }

    monkeypatch.setattr(get_memory_review_agent(), "run", fake_memory_run)
    monkeypatch.setattr(get_rag_adapter(), "upload_learning", fake_upload_learning)
    monkeypatch.setattr(get_deepseek_service(), "available", lambda: True)
    monkeypatch.setattr(get_deepseek_service(), "generate_prompt_package", fake_generate_prompt_package)

    client = TestClient(app)
    resp = client.post(
        "/run/prompt-workflow",
        json={
            "goal": "crear un agente para mejorar prompts de codigo",
            "agent_name": "prompt_optimizer_agent",
            "current_version": "v3",
            "tenant_id": "tenant-test",
            "publish_learning": True,
            "context": {"complexity": 4},
        },
    )
    assert resp.status_code == 200
    body = resp.json()["run"]
    assert body["selected_graph"] == "prompt_workflow_v1"
    assert body["status"] == "succeeded"
    assert body["result"]["prompt_package"]["workflow"] == "copilot_plan_then_codex"
    assert body["providers_used"] == ["deepseek"]
    assert body["result"]["rag_publication"]["document_id"] == "learning-doc"

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
        get_hapi_client,
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
        get_voice_pair_adapter,
    )

    get_settings.cache_clear()
    get_store.cache_clear()
    get_provider_service.cache_clear()
    get_deepseek_service.cache_clear()
    get_hapi_client.cache_clear()
    get_terminal_adapter.cache_clear()
    get_rag_adapter.cache_clear()
    get_celery_adapter.cache_clear()
    get_voice_pair_adapter.cache_clear()
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
            "hapi": {"available": False},
            "voice_pair": {"available": False},
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
    assert "agent_run_ui_factory" in names
    assert "agent_synthesize_voice" in names


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


def test_run_ui_factory_endpoint(tmp_path: Path, monkeypatch):
    os.environ["AGENT_DATA_DIR"] = str(tmp_path / "data")
    _reset_caches()

    from app.main import app
    from app.services.container import get_hapi_client, get_rag_adapter, get_terminal_adapter

    async def fake_hapi_create_project(payload):
        return {
            "project": {
                "slug": "sales-region-ui",
                "project_root": "apps/sales-region-ui",
                "domain": "sales-region-ui.apps.uniflexa.cloud",
            }
        }

    async def fake_hapi_get_project(slug):
        return {
            "slug": slug,
            "project_root": f"apps/{slug}",
            "domain": f"{slug}.apps.uniflexa.cloud",
        }

    async def fake_hapi_render_context(slug):
        return {"slug": slug, "notes_for_agent": ["project lives in apps/sales-region-ui"]}

    async def fake_hapi_get_public_app_by_slug(slug):
        return None

    async def fake_hapi_get_public_app_by_domain(domain):
        return None

    async def fake_hapi_deploy_project(slug, payload):
        return {"slug": slug, "status": "ready_for_coolify", "details": {"base_directory": f"/apps/{slug}"}}

    async def fake_hapi_register_public_app(payload):
        return {**payload, "app_id": "app_123"}

    async def fake_hapi_record_deployment(app_id, payload):
        return {"app_id": app_id, **payload}

    async def fake_hapi_record_sync(app_id, payload):
        return {"ok": True, "event": {"app_id": app_id, **payload}}

    async def fake_rag_research(**kwargs):
        return {"answer": "none", "sources": []}

    async def fake_rag_upload_learning(**kwargs):
        return {"document_id": "ui-doc-1", "tenant_id": kwargs["tenant_id"], "metadata": kwargs["metadata"]}

    async def fake_terminal_plan(**kwargs):
        return {"task_id": "plan-1", "status": "succeeded", "result": {"ok": True, "stdout": "plan ok"}}

    async def fake_terminal_codex(**kwargs):
        return {"task_id": "codex-1", "status": "succeeded", "result": {"ok": True, "stdout": "codex ok"}}

    async def fake_terminal_command(**kwargs):
        command = kwargs["command"]
        stdout = "ok\n"
        if command[:3] == ["git", "status", "--short"]:
            stdout = " M apps/sales-region-ui/README.md\n"
        elif command[:3] == ["git", "rev-parse", "HEAD"]:
            stdout = "abc123def456\n"
        return {"task_id": "cmd-1", "status": "succeeded", "result": {"ok": True, "stdout": stdout}}

    hapi = get_hapi_client()
    monkeypatch.setattr(hapi, "create_project", fake_hapi_create_project)
    monkeypatch.setattr(hapi, "get_project", fake_hapi_get_project)
    monkeypatch.setattr(hapi, "render_project_context", fake_hapi_render_context)
    monkeypatch.setattr(hapi, "get_public_app_by_slug", fake_hapi_get_public_app_by_slug)
    monkeypatch.setattr(hapi, "get_public_app_by_domain", fake_hapi_get_public_app_by_domain)
    monkeypatch.setattr(hapi, "deploy_project", fake_hapi_deploy_project)
    monkeypatch.setattr(hapi, "register_public_app", fake_hapi_register_public_app)
    monkeypatch.setattr(hapi, "record_deployment", fake_hapi_record_deployment)
    monkeypatch.setattr(hapi, "record_sync", fake_hapi_record_sync)
    monkeypatch.setattr(get_rag_adapter(), "research", fake_rag_research)
    monkeypatch.setattr(get_rag_adapter(), "upload_learning", fake_rag_upload_learning)
    monkeypatch.setattr(get_terminal_adapter(), "run_copilot_plan", fake_terminal_plan)
    monkeypatch.setattr(get_terminal_adapter(), "run_codex", fake_terminal_codex)
    monkeypatch.setattr(get_terminal_adapter(), "run_copilot", fake_terminal_plan)
    monkeypatch.setattr(get_terminal_adapter(), "run_command", fake_terminal_command)

    client = TestClient(app)
    resp = client.post(
        "/run/ui-factory",
        json={
            "goal": "crea una app para ver ventas por región con filtros y gráficos",
            "tenant_id": "tenant-ui",
            "app_name": "Sales Region UI",
            "project_type": "long_lived",
            "deploy": True,
            "publish_memory": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()["run"]
    assert body["selected_graph"] == "ui_factory_v1"
    assert body["status"] == "succeeded"
    assert body["result"]["final"]["app_id"] == "app_123"
    assert body["result"]["final"]["deployment_status"] == "ready_for_coolify"
    assert body["result"]["final"]["rag_ingested"] is True


def test_run_ui_factory_recovers_public_app_before_deployment(tmp_path: Path, monkeypatch):
    os.environ["AGENT_DATA_DIR"] = str(tmp_path / "data")
    _reset_caches()

    from app.adapters.hapi_client import HapiClientError
    from app.main import app
    from app.services.container import get_hapi_client, get_rag_adapter, get_terminal_adapter

    async def fake_hapi_create_project(payload):
        return {
            "project": {
                "slug": "sales-region-ui-recover",
                "project_root": "apps/sales-region-ui-recover",
                "domain": "sales-region-ui-recover.apps.uniflexa.cloud",
            }
        }

    async def fake_hapi_get_project(slug):
        return {
            "slug": slug,
            "project_root": f"apps/{slug}",
            "domain": f"{slug}.apps.uniflexa.cloud",
        }

    async def fake_hapi_render_context(slug):
        return {"slug": slug, "notes_for_agent": ["project lives in apps/sales-region-ui-recover"]}

    async def fake_hapi_get_public_app_by_slug(slug):
        if slug == "sales-region-ui-recover":
            return {"app_id": "app_recovered", "slug": slug}
        return None

    async def fake_hapi_get_public_app_by_domain(domain):
        return None

    async def fake_hapi_get_public_app(app_id):
        if app_id == "app_recovered":
            return {"app_id": app_id, "slug": "sales-region-ui-recover"}
        return None

    async def fake_hapi_deploy_project(slug, payload):
        return {"slug": slug, "status": "ready_for_coolify", "details": {"base_directory": f"/apps/{slug}"}}

    async def fake_hapi_register_public_app(payload):
        return {**payload, "app_id": "app_missing"}

    calls = {"deployment": 0}

    async def fake_hapi_record_deployment(app_id, payload):
        calls["deployment"] += 1
        if calls["deployment"] == 1:
            raise HapiClientError(
                "hapi_request_failed:/public/apps/app_missing/deployment",
                status_code=404,
                payload={"detail": "public_app_not_found"},
            )
        return {"app_id": app_id, **payload}

    async def fake_hapi_record_sync(app_id, payload):
        return {"ok": True, "event": {"app_id": app_id, **payload}}

    async def fake_rag_research(**kwargs):
        return {"answer": "none", "sources": []}

    async def fake_rag_upload_learning(**kwargs):
        return {"document_id": "ui-doc-recover", "tenant_id": kwargs["tenant_id"], "metadata": kwargs["metadata"]}

    async def fake_terminal_plan(**kwargs):
        return {"task_id": "plan-1", "status": "succeeded", "result": {"ok": True, "stdout": "plan ok"}}

    async def fake_terminal_codex(**kwargs):
        return {"task_id": "codex-1", "status": "succeeded", "result": {"ok": True, "stdout": "codex ok"}}

    async def fake_terminal_command(**kwargs):
        command = kwargs["command"]
        stdout = "ok\n"
        if command[:3] == ["git", "status", "--short"]:
            stdout = " M apps/sales-region-ui-recover/README.md\n"
        elif command[:3] == ["git", "rev-parse", "HEAD"]:
            stdout = "recoveredsha123\n"
        return {"task_id": "cmd-1", "status": "succeeded", "result": {"ok": True, "stdout": stdout}}

    async def fake_terminal_fail(**kwargs):
        return {"task_id": "cmd-fail", "status": "failed", "summary": "Execution failed", "error": "codex crashed", "result": {"ok": False, "stderr": "codex crashed"}}

    hapi = get_hapi_client()
    monkeypatch.setattr(hapi, "create_project", fake_hapi_create_project)
    monkeypatch.setattr(hapi, "get_project", fake_hapi_get_project)
    monkeypatch.setattr(hapi, "render_project_context", fake_hapi_render_context)
    monkeypatch.setattr(hapi, "get_public_app_by_slug", fake_hapi_get_public_app_by_slug)
    monkeypatch.setattr(hapi, "get_public_app_by_domain", fake_hapi_get_public_app_by_domain)
    monkeypatch.setattr(hapi, "get_public_app", fake_hapi_get_public_app)
    monkeypatch.setattr(hapi, "deploy_project", fake_hapi_deploy_project)
    monkeypatch.setattr(hapi, "register_public_app", fake_hapi_register_public_app)
    monkeypatch.setattr(hapi, "record_deployment", fake_hapi_record_deployment)
    monkeypatch.setattr(hapi, "record_sync", fake_hapi_record_sync)
    monkeypatch.setattr(get_rag_adapter(), "research", fake_rag_research)
    monkeypatch.setattr(get_rag_adapter(), "upload_learning", fake_rag_upload_learning)
    monkeypatch.setattr(get_terminal_adapter(), "run_copilot_plan", fake_terminal_plan)
    monkeypatch.setattr(get_terminal_adapter(), "run_codex", fake_terminal_codex)
    monkeypatch.setattr(get_terminal_adapter(), "run_copilot", fake_terminal_plan)
    monkeypatch.setattr(get_terminal_adapter(), "run_command", fake_terminal_command)

    client = TestClient(app)
    resp = client.post(
        "/run/ui-factory",
        json={
            "goal": "crea una app para ver ventas por región con filtros y gráficos",
            "tenant_id": "tenant-ui",
            "app_name": "Sales Region UI Recover",
            "project_type": "long_lived",
            "deploy": True,
            "publish_memory": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()["run"]
    assert body["status"] == "succeeded"
    assert body["result"]["final"]["app_id"] == "app_recovered"
    assert calls["deployment"] == 2


def test_run_ui_factory_fails_when_terminal_task_fails(tmp_path: Path, monkeypatch):
    os.environ["AGENT_DATA_DIR"] = str(tmp_path / "data")
    _reset_caches()

    from app.main import app
    from app.services.container import get_hapi_client, get_rag_adapter, get_terminal_adapter

    async def fake_hapi_create_project(payload):
        return {"project": {"slug": "sales-region-ui-fail", "project_root": "apps/sales-region-ui-fail", "domain": "sales-region-ui-fail.apps.uniflexa.cloud"}}

    async def fake_hapi_render_context(slug):
        return {"slug": slug}

    async def fake_hapi_get_public_app_by_slug(slug):
        return None

    async def fake_hapi_get_public_app_by_domain(domain):
        return None

    async def fake_rag_research(**kwargs):
        return {"answer": "none", "sources": []}

    async def fake_terminal_plan(**kwargs):
        return {"task_id": "plan-1", "status": "failed", "summary": "Execution failed", "error": "copilot crashed", "result": {"ok": False, "stderr": "copilot crashed"}}

    hapi = get_hapi_client()
    monkeypatch.setattr(hapi, "create_project", fake_hapi_create_project)
    monkeypatch.setattr(hapi, "render_project_context", fake_hapi_render_context)
    monkeypatch.setattr(hapi, "get_public_app_by_slug", fake_hapi_get_public_app_by_slug)
    monkeypatch.setattr(hapi, "get_public_app_by_domain", fake_hapi_get_public_app_by_domain)
    monkeypatch.setattr(get_rag_adapter(), "research", fake_rag_research)
    monkeypatch.setattr(get_terminal_adapter(), "run_copilot_plan", fake_terminal_plan)

    client = TestClient(app)
    resp = client.post(
        "/run/ui-factory",
        json={
            "goal": "crea una app para ver ventas por región con filtros y gráficos",
            "tenant_id": "tenant-ui",
            "app_name": "Sales Region UI Fail",
            "project_type": "long_lived",
            "deploy": True,
            "publish_memory": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()["run"]
    assert body["status"] == "failed"
    assert "run_ui_planning" in (body["error"] or "")


def test_run_ui_factory_deferred_deploy_is_recovered_without_hard_failure(tmp_path: Path, monkeypatch):
    os.environ["AGENT_DATA_DIR"] = str(tmp_path / "data")
    _reset_caches()

    from app.main import app
    from app.services.container import get_hapi_client, get_rag_adapter, get_terminal_adapter

    async def fake_hapi_create_project(payload):
        return {
            "project": {
                "slug": "sales-region-ui-deferred",
                "project_root": "apps/sales-region-ui-deferred",
                "domain": "sales-region-ui-deferred.apps.uniflexa.cloud",
            }
        }

    async def fake_hapi_get_project(slug):
        return {
            "slug": slug,
            "project_root": f"apps/{slug}",
            "domain": f"{slug}.apps.uniflexa.cloud",
        }

    async def fake_hapi_render_context(slug):
        return {"slug": slug, "notes_for_agent": ["project lives in apps/sales-region-ui-deferred"]}

    async def fake_hapi_get_public_app_by_slug(slug):
        return None

    async def fake_hapi_get_public_app_by_domain(domain):
        return None

    async def fake_hapi_deploy_project(slug, payload):
        return {
            "slug": slug,
            "provider": "coolify",
            "deployed": False,
            "status": "deferred",
            "error": None,
            "details": {"reason": "coolify_temporarily_unavailable", "retry_recommended": True},
        }

    async def fake_hapi_health():
        return {"available": True, "base_url": "http://hapi", "data": {"status": "ok"}}

    async def fake_hapi_coolify_health():
        return {"enabled": True, "configured": True, "reachable": False, "reason": "maintenance"}

    async def fake_hapi_register_public_app(payload):
        return {**payload, "app_id": "app_deferred"}

    async def fake_hapi_record_deployment(app_id, payload):
        return {"app_id": app_id, **payload}

    async def fake_hapi_record_sync(app_id, payload):
        return {"ok": True, "event": {"app_id": app_id, **payload}}

    async def fake_rag_research(**kwargs):
        return {"answer": "none", "sources": []}

    async def fake_rag_upload_learning(**kwargs):
        return {"document_id": "ui-doc-deferred", "tenant_id": kwargs["tenant_id"], "metadata": kwargs["metadata"]}

    async def fake_terminal_plan(**kwargs):
        return {"task_id": "plan-1", "status": "succeeded", "result": {"ok": True, "stdout": "plan ok"}}

    async def fake_terminal_codex(**kwargs):
        return {"task_id": "codex-1", "status": "succeeded", "result": {"ok": True, "stdout": "codex ok"}}

    async def fake_terminal_command(**kwargs):
        command = kwargs["command"]
        stdout = "ok\n"
        if command[:3] == ["git", "status", "--short"]:
            stdout = " M apps/sales-region-ui-deferred/README.md\n"
        elif command[:3] == ["git", "rev-parse", "HEAD"]:
            stdout = "deferredsha123\n"
        return {"task_id": "cmd-1", "status": "succeeded", "result": {"ok": True, "stdout": stdout}}

    hapi = get_hapi_client()
    monkeypatch.setattr(hapi, "create_project", fake_hapi_create_project)
    monkeypatch.setattr(hapi, "get_project", fake_hapi_get_project)
    monkeypatch.setattr(hapi, "render_project_context", fake_hapi_render_context)
    monkeypatch.setattr(hapi, "get_public_app_by_slug", fake_hapi_get_public_app_by_slug)
    monkeypatch.setattr(hapi, "get_public_app_by_domain", fake_hapi_get_public_app_by_domain)
    monkeypatch.setattr(hapi, "deploy_project", fake_hapi_deploy_project)
    monkeypatch.setattr(hapi, "health", fake_hapi_health)
    monkeypatch.setattr(hapi, "coolify_health", fake_hapi_coolify_health)
    monkeypatch.setattr(hapi, "register_public_app", fake_hapi_register_public_app)
    monkeypatch.setattr(hapi, "record_deployment", fake_hapi_record_deployment)
    monkeypatch.setattr(hapi, "record_sync", fake_hapi_record_sync)
    monkeypatch.setattr(get_rag_adapter(), "research", fake_rag_research)
    monkeypatch.setattr(get_rag_adapter(), "upload_learning", fake_rag_upload_learning)
    monkeypatch.setattr(get_terminal_adapter(), "run_copilot_plan", fake_terminal_plan)
    monkeypatch.setattr(get_terminal_adapter(), "run_codex", fake_terminal_codex)
    monkeypatch.setattr(get_terminal_adapter(), "run_copilot", fake_terminal_plan)
    monkeypatch.setattr(get_terminal_adapter(), "run_command", fake_terminal_command)

    client = TestClient(app)
    resp = client.post(
        "/run/ui-factory",
        json={
            "goal": "crea una app para ver ventas por región con filtros y gráficos",
            "tenant_id": "tenant-ui",
            "app_name": "Sales Region UI Deferred",
            "project_type": "long_lived",
            "deploy": True,
            "publish_memory": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()["run"]
    assert body["status"] == "succeeded"
    assert body["result"]["final"]["status"] == "succeeded"
    assert body["result"]["final"]["deployment_status"] == "deferred"
    assert body["result"]["final"]["requires_followup"] is True


def test_mcp_synthesize_voice_tool_registered(tmp_path: Path, monkeypatch):
    """voice-pair tool is registered in the MCP registry and callable (mocked)."""
    os.environ["AGENT_DATA_DIR"] = str(tmp_path / "data")
    _reset_caches()

    from app.main import app
    from app.services.container import get_voice_pair_adapter

    adapter = get_voice_pair_adapter()

    async def fake_synthesize(text, voice_id="default", format="wav"):
        return {"audio_id": "test-audio-id-123", "path": "/tmp/test-audio-id-123.wav"}

    monkeypatch.setattr(adapter, "synthesize", fake_synthesize)

    client = TestClient(app)

    # Verify tool is listed
    tools = client.get("/mcp/tools")
    names = [t["name"] for t in tools.json()["tools"]]
    assert "agent_synthesize_voice" in names

    # Call the tool
    resp = client.post(
        "/mcp/tools/agent_synthesize_voice",
        json={"text": "hola desde open claw", "voice_id": "openclaw-user"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["audio_id"] == "test-audio-id-123"
    assert "download_url" in body["data"]
    assert body["data"]["voice_id"] == "openclaw-user"

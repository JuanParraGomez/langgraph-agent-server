from __future__ import annotations

from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from app.models.schemas import (
    CancelRunRequest,
    ComplexTaskRequest,
    PlanTaskRequest,
    PromptWorkflowRequest,
    ResearchSubtaskRequest,
    ScriptOpsSubtaskRequest,
    SummarizeFindingsRequest,
    TerminalSubtaskRequest,
    UIFactoryRequest,
    VoiceSynthesisRequest,
)
from app.services.container import get_capabilities_service, get_run_service, get_voice_pair_adapter


ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


async def _agent_health(_: dict[str, Any]) -> dict[str, Any]:
    caps = get_capabilities_service()
    return {
        "service": "langgraph-agent-server",
        "providers": caps.provider_service.capabilities(),
        "backends": await caps.backend_health(),
    }


async def _agent_list_capabilities(_: dict[str, Any]) -> dict[str, Any]:
    return await get_capabilities_service().full_capabilities()


async def _agent_run_complex_task(payload: dict[str, Any]) -> dict[str, Any]:
    req = ComplexTaskRequest.model_validate(payload)
    run = await get_run_service().run_complex(req)
    return run.model_dump(mode="json")


async def _agent_plan_task(payload: dict[str, Any]) -> dict[str, Any]:
    req = PlanTaskRequest.model_validate(payload)
    return await get_run_service().plan_only(req)


async def _agent_run_prompt_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    req = PromptWorkflowRequest.model_validate(payload)
    run = await get_run_service().run_prompt_workflow(req)
    return run.model_dump(mode="json")


async def _agent_run_ui_factory(payload: dict[str, Any]) -> dict[str, Any]:
    req = UIFactoryRequest.model_validate(payload)
    run = await get_run_service().run_ui_factory(req)
    return run.model_dump(mode="json")


async def _agent_run_research(payload: dict[str, Any]) -> dict[str, Any]:
    req = ResearchSubtaskRequest.model_validate(payload)
    return await get_run_service().run_research(req)


async def _agent_run_terminal_subtask(payload: dict[str, Any]) -> dict[str, Any]:
    req = TerminalSubtaskRequest.model_validate(payload)
    return await get_run_service().run_terminal(req)


async def _agent_run_script_ops_subtask(payload: dict[str, Any]) -> dict[str, Any]:
    req = ScriptOpsSubtaskRequest.model_validate(payload)
    return await get_run_service().run_script_ops(req)


async def _agent_summarize_findings(payload: dict[str, Any]) -> dict[str, Any]:
    req = SummarizeFindingsRequest.model_validate(payload)
    return await get_run_service().summarize_findings(req)


async def _agent_get_run(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = str(payload.get("run_id", "")).strip()
    run = get_run_service().get_run(run_id)
    if run is None:
        return {"ok": False, "error": "run_not_found", "run_id": run_id}
    return {"ok": True, "run": run.model_dump(mode="json")}


async def _agent_get_run_logs(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = str(payload.get("run_id", "")).strip()
    return {"ok": True, "run_id": run_id, "logs": get_run_service().get_run_logs(run_id)}


async def _agent_cancel_run(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = str(payload.get("run_id", "")).strip()
    req = CancelRunRequest.model_validate({"reason": payload.get("reason")})
    run = get_run_service().cancel_run(run_id, req.reason)
    if run is None:
        return {"ok": False, "error": "run_not_found", "run_id": run_id}
    return {"ok": True, "run": run.model_dump(mode="json")}


async def _agent_synthesize_voice(payload: dict[str, Any]) -> dict[str, Any]:
    req = VoiceSynthesisRequest.model_validate(payload)
    adapter = get_voice_pair_adapter()
    result = await adapter.synthesize(req.text, voice_id=req.voice_id, format=req.format)
    audio_id = result.get("audio_id", "")
    download_url = await adapter.download_url(audio_id) if audio_id else None
    return {
        "ok": True,
        "audio_id": audio_id,
        "download_url": download_url,
        "voice_id": req.voice_id,
        "text": req.text,
    }


async def _agent_list_graphs(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "graphs": [
            {
                "name": "supervisor_v1",
                "engine": "langgraph",
                "description": "Supervisor + specialized subagents + synthesis",
            },
            {
                "name": "ui_factory_v1",
                "engine": "service-workflow",
                "description": "Discover/create/update UI, build via terminal-tools, register public state in hapi, ingest memory in rag",
            },
        ]
    }


async def _agent_list_agents(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "agents": [
            {"name": "supervisor_agent", "role": "planning/delegation/control"},
            {"name": "research_agent", "role": "rag/document context"},
            {"name": "memory_review_agent", "role": "similarity/version check against rag memory"},
            {"name": "prompt_engineer_agent", "role": "build prompt package and tool flow"},
            {"name": "failure_recovery_agent", "role": "classify runtime failures and provide remediation hints"},
            {"name": "ui_factory_graph", "role": "create/update/publish UI using terminal-tools, hapi and rag"},
            {"name": "terminal_agent", "role": "terminal operations via terminal-tools"},
            {"name": "script_ops_agent", "role": "script ops via celery-server"},
            {"name": "synthesis_agent", "role": "final synthesis"},
        ]
    }


TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(name="agent_health", description="Service health and provider/backend availability", input_schema={"type": "object", "properties": {}}),
    ToolSpec(name="agent_list_capabilities", description="List providers, agents, graphs and connected backends", input_schema={"type": "object", "properties": {}}),
    ToolSpec(name="agent_run_complex_task", description="Main tool: run complex task through supervisor graph", input_schema=ComplexTaskRequest.model_json_schema()),
    ToolSpec(name="agent_plan_task", description="Produce structured plan without full execution", input_schema=PlanTaskRequest.model_json_schema()),
    ToolSpec(name="agent_run_prompt_workflow", description="Review similar memory, generate code-task prompts, and publish learning to rag-server", input_schema=PromptWorkflowRequest.model_json_schema()),
    ToolSpec(name="agent_run_ui_factory", description="Create or update a UI project, publish state through hapi, and ingest memory into rag-server", input_schema=UIFactoryRequest.model_json_schema()),
    ToolSpec(name="agent_run_research", description="Run research-focused subtask with research_agent", input_schema=ResearchSubtaskRequest.model_json_schema()),
    ToolSpec(name="agent_run_terminal_subtask", description="Run operational subtask through terminal_agent", input_schema=TerminalSubtaskRequest.model_json_schema()),
    ToolSpec(name="agent_run_script_ops_subtask", description="Run script operation through script_ops_agent", input_schema=ScriptOpsSubtaskRequest.model_json_schema()),
    ToolSpec(name="agent_summarize_findings", description="Synthesize findings from a previous run", input_schema=SummarizeFindingsRequest.model_json_schema()),
    ToolSpec(name="agent_get_run", description="Get run status by run_id", input_schema={"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"]}),
    ToolSpec(name="agent_get_run_logs", description="Get run logs by run_id", input_schema={"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"]}),
    ToolSpec(name="agent_cancel_run", description="Cancel an active run by run_id", input_schema={"type": "object", "properties": {"run_id": {"type": "string"}, "reason": {"type": "string"}}, "required": ["run_id"]}),
    ToolSpec(name="agent_list_graphs", description="List available graphs", input_schema={"type": "object", "properties": {}}),
    ToolSpec(name="agent_list_agents", description="List specialized agents and roles", input_schema={"type": "object", "properties": {}}),
    ToolSpec(
        name="agent_synthesize_voice",
        description="Synthesize text to audio using voice-pair service; returns audio_id and download_url",
        input_schema=VoiceSynthesisRequest.model_json_schema(),
    ),
]

TOOL_HANDLERS: dict[str, ToolHandler] = {
    "agent_health": _agent_health,
    "agent_list_capabilities": _agent_list_capabilities,
    "agent_run_complex_task": _agent_run_complex_task,
    "agent_plan_task": _agent_plan_task,
    "agent_run_prompt_workflow": _agent_run_prompt_workflow,
    "agent_run_ui_factory": _agent_run_ui_factory,
    "agent_run_research": _agent_run_research,
    "agent_run_terminal_subtask": _agent_run_terminal_subtask,
    "agent_run_script_ops_subtask": _agent_run_script_ops_subtask,
    "agent_summarize_findings": _agent_summarize_findings,
    "agent_get_run": _agent_get_run,
    "agent_get_run_logs": _agent_get_run_logs,
    "agent_cancel_run": _agent_cancel_run,
    "agent_list_graphs": _agent_list_graphs,
    "agent_list_agents": _agent_list_agents,
    "agent_synthesize_voice": _agent_synthesize_voice,
}

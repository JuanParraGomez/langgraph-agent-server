from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.settings import get_settings
from app.models.schemas import (
    CancelRunRequest,
    CapabilitiesResponse,
    ComplexTaskRequest,
    HealthResponse,
    PlanTaskRequest,
    PromptWorkflowRequest,
    ResearchSubtaskRequest,
    RunLogsResponse,
    RunResponse,
    ScriptOpsSubtaskRequest,
    TerminalSubtaskRequest,
    UIFactoryRequest,
)
from app.services.container import get_capabilities_service, get_run_service

router = APIRouter(tags=["agent-server"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    caps = get_capabilities_service()
    backends = await caps.backend_health()
    return HealthResponse(
        status="ok",
        service=get_settings().server_name,
        providers=caps.provider_service.capabilities(),
        backends=backends,
    )


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities() -> CapabilitiesResponse:
    data = await get_capabilities_service().full_capabilities()
    return CapabilitiesResponse(
        agents=data["agents"],
        graphs=data["graphs"],
        providers=data["providers"],
        backends=data["backends"],
    )


@router.get("/agents")
async def list_agents() -> dict:
    data = await get_capabilities_service().full_capabilities()
    return {"agents": data["agents"]}


@router.get("/graphs")
async def list_graphs() -> dict:
    data = await get_capabilities_service().full_capabilities()
    return {"graphs": data["graphs"]}


@router.post("/run/complex", response_model=RunResponse)
async def run_complex(req: ComplexTaskRequest) -> RunResponse:
    run = await get_run_service().run_complex(req)
    return RunResponse(run=run)


@router.post("/run/plan")
async def run_plan(req: PlanTaskRequest) -> dict:
    return await get_run_service().plan_only(req)


@router.post("/run/prompt-workflow", response_model=RunResponse)
async def run_prompt_workflow(req: PromptWorkflowRequest) -> RunResponse:
    run = await get_run_service().run_prompt_workflow(req)
    return RunResponse(run=run)


@router.post("/run/ui-factory", response_model=RunResponse)
async def run_ui_factory(req: UIFactoryRequest) -> RunResponse:
    run = await get_run_service().run_ui_factory(req)
    return RunResponse(run=run)


@router.post("/run/research")
async def run_research(req: ResearchSubtaskRequest) -> dict:
    return await get_run_service().run_research(req)


@router.post("/run/terminal")
async def run_terminal(req: TerminalSubtaskRequest) -> dict:
    return await get_run_service().run_terminal(req)


@router.post("/run/script-ops")
async def run_script_ops(req: ScriptOpsSubtaskRequest) -> dict:
    return await get_run_service().run_script_ops(req)


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str) -> RunResponse:
    run = get_run_service().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return RunResponse(run=run)


@router.get("/runs/{run_id}/logs", response_model=RunLogsResponse)
async def get_run_logs(run_id: str) -> RunLogsResponse:
    return RunLogsResponse(run_id=run_id, logs=get_run_service().get_run_logs(run_id))


@router.post("/runs/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(run_id: str, req: CancelRunRequest) -> RunResponse:
    run = get_run_service().cancel_run(run_id, req.reason)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return RunResponse(run=run)

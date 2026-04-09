from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.settings import get_settings
from app.models.schemas import (
    BotFactoryRequest,
    CancelRunRequest,
    CapabilitiesResponse,
    CodeExecutionRequest,
    ComplexTaskRequest,
    HealthResponse,
    OnboardingRequest,
    PersonalCoachRequest,
    PlanTaskRequest,
    PromptWorkflowRequest,
    ResearchSubtaskRequest,
    RunLogsResponse,
    RunResponse,
    ScriptOpsSubtaskRequest,
    TerminalSubtaskRequest,
    UIFactoryRequest,
)
from app.services.container import get_capabilities_service, get_coordinator_agent, get_run_service
from app.services.agent_registry import AgentCapability, get_agent_registry

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


@router.post("/run/bot-factory", response_model=RunResponse)
async def run_bot_factory(req: BotFactoryRequest) -> RunResponse:
    run = await get_run_service().run_bot_factory(req)
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


@router.post("/run/onboarding")
async def run_onboarding(req: OnboardingRequest) -> dict:
    return await get_run_service().run_onboarding(req)


@router.post("/run/personal-coach")
async def run_personal_coach(req: PersonalCoachRequest) -> dict:
    return await get_run_service().run_personal_coach(req)


@router.post("/run/code")
async def run_code(req: CodeExecutionRequest) -> dict:
    svc = get_run_service()
    result = await svc.code_graph.run(
        objective=req.objective,
        cwd=req.cwd,
        complexity=req.complexity,
    )
    return result


@router.post("/run/coordinate")
async def run_coordinate(req: ComplexTaskRequest) -> dict:
    """Run a command through the coordinator agent with full decomposition + feedback loop."""
    coordinator = get_coordinator_agent()
    svc = get_run_service()
    agent_runners = {
        "research_agent": svc.research,
        "terminal_agent": svc.terminal,
        "script_ops_agent": svc.script_ops,
        "memory_review_agent": svc.memory_review,
        "prompt_engineer_agent": svc.prompt_engineer,
    }
    return await coordinator.run(
        command=req.goal,
        agent_runners=agent_runners,
        context=req.context,
    )


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str) -> RunResponse:
    run = get_run_service().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return RunResponse(run=run)


# ── Agent Registry + Dynamic Tool Registration ──────────────────

@router.get("/agents/registry")
async def list_agent_registry() -> dict:
    """List all registered agents and their capabilities."""
    registry = get_agent_registry()
    return {"agents": registry.to_dict()}


@router.post("/agents/registry")
async def register_agent(body: dict) -> dict:
    """Register a new agent or update an existing one."""
    registry = get_agent_registry()
    try:
        cap = AgentCapability(
            agent_name=body["agent_name"],
            capabilities=body.get("capabilities", []),
            description=body.get("description", ""),
            metadata=body.get("metadata", {}),
        )
        registry.register(cap)
        return {"ok": True, "agent_name": cap.agent_name}
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Missing field: {exc}")


@router.delete("/agents/registry/{agent_name}")
async def unregister_agent(agent_name: str) -> dict:
    """Remove an agent from the registry."""
    registry = get_agent_registry()
    if registry.unregister(agent_name):
        return {"ok": True, "removed": agent_name}
    raise HTTPException(status_code=404, detail="agent_not_found")


@router.post("/agents/registry/query")
async def query_agent_registry(body: dict) -> dict:
    """Find agents best suited for a task description."""
    registry = get_agent_registry()
    task = body.get("task", "")
    if not task:
        raise HTTPException(status_code=400, detail="task is required")
    matches = registry.find_best_for_task(task)
    return {"task": task, "matches": [{"agent": a, "score": s} for a, s in matches]}


@router.post("/tools/register")
async def register_dynamic_tool(body: dict) -> dict:
    """Register a dynamic tool at runtime. Tool calls are proxied to handler_url."""
    import threading
    from urllib.parse import urlparse
    from app.mcp_server.tool_registry import ToolSpec, TOOL_SPECS, TOOL_HANDLERS

    name = body.get("name")
    description = body.get("description", "")
    schema = body.get("schema", {"type": "object", "properties": {}})
    handler_url = body.get("handler_url")

    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not handler_url:
        raise HTTPException(status_code=400, detail="handler_url is required")

    # Validate handler_url — block private/internal IPs (SSRF protection)
    try:
        parsed = urlparse(handler_url)
        if parsed.scheme not in ("http", "https"):
            raise HTTPException(status_code=400, detail="handler_url must use http or https")
        hostname = parsed.hostname or ""
        import ipaddress
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise HTTPException(status_code=400, detail="handler_url cannot target private/internal addresses")
        except ValueError:
            # It's a hostname, not an IP — block obvious internal names
            blocked = ("localhost", "127.0.0.1", "0.0.0.0", "metadata.google", "169.254.169.254")
            if any(hostname == b or hostname.endswith("." + b) for b in blocked):
                raise HTTPException(status_code=400, detail="handler_url cannot target internal addresses")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid handler_url")

    # Thread-safe registration
    _tool_reg_lock = getattr(register_dynamic_tool, "_lock", None)
    if _tool_reg_lock is None:
        register_dynamic_tool._lock = threading.Lock()  # type: ignore[attr-defined]
        _tool_reg_lock = register_dynamic_tool._lock

    with _tool_reg_lock:
        if name in TOOL_HANDLERS:
            raise HTTPException(status_code=409, detail=f"Tool '{name}' already registered")

        import httpx

        async def proxy_handler(payload: dict) -> dict:
            # Re-validate resolved IP at request time (DNS rebinding protection)
            import socket
            parsed_url = urlparse(handler_url)
            try:
                resolved_ip = socket.getaddrinfo(parsed_url.hostname, parsed_url.port or 443)[0][4][0]
                resolved = ipaddress.ip_address(resolved_ip)
                if resolved.is_private or resolved.is_loopback or resolved.is_link_local or resolved.is_reserved:
                    raise ValueError(f"handler resolved to private IP: {resolved_ip}")
            except (socket.gaierror, ValueError) as e:
                raise httpx.HTTPStatusError(
                    f"SSRF blocked: {e}", request=None, response=None  # type: ignore[arg-type]
                )
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(handler_url, json=payload)
                resp.raise_for_status()
                return resp.json()

        TOOL_SPECS.append(ToolSpec(name=name, description=description, input_schema=schema))
        TOOL_HANDLERS[name] = proxy_handler

    return {"ok": True, "tool": name, "handler_url": handler_url}


@router.get("/runs/{run_id}/logs", response_model=RunLogsResponse)
async def get_run_logs(run_id: str) -> RunLogsResponse:
    return RunLogsResponse(run_id=run_id, logs=get_run_service().get_run_logs(run_id))


@router.post("/runs/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(run_id: str, req: CancelRunRequest) -> RunResponse:
    run = get_run_service().cancel_run(run_id, req.reason)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return RunResponse(run=run)

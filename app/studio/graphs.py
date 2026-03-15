"""
LangGraph Studio – graph exports.

This module exposes the real compiled graphs from this project so that
LangGraph Studio can visualize, inspect and invoke them.

Rules:
  - This module MUST NOT import from app.main or anything that boots 8070.
  - Uses the same DI container as 8070 so graphs are structurally identical.
  - LangSmith tracing is inherited from env vars already set by configure_langsmith().
  - Two graphs are exported:
      * supervisor_graph  (StateGraph compiled via ComplexTaskGraph._build_graph)
      * ui_factory_stub   (a lightweight StateGraph that mirrors UIFactoryGraph steps)

# AI AGENT NOTE: see docs/AGENT_OBSERVABILITY_RULES.md — all graph invocations
# must remain instrumented via invoke_graph_traced or traceable wrappers.
"""
from __future__ import annotations

import os
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from app.core.settings import get_settings
from app.observability.langsmith_setup import configure_langsmith
from app.services.container import (
    get_research_agent,
    get_script_ops_agent,
    get_supervisor_agent,
    get_synthesis_agent,
    get_terminal_agent,
)

# ── Boot LangSmith for Studio runtime ───────────────────────────────────────
_settings = get_settings()
# Override project to keep Studio traces separate from 8070 traces.
_studio_project = os.getenv("LANGSMITH_STUDIO_PROJECT", "langgraph-agent-server-studio")
os.environ["LANGSMITH_PROJECT"] = _studio_project
os.environ["LANGCHAIN_PROJECT"] = _studio_project
configure_langsmith(_settings)


# ────────────────────────────────────────────────────────────────────────────
# Graph 1: supervisor_v1
# Identical structure to ComplexTaskGraph._build_graph, but compiled standalone
# with a MemorySaver checkpointer so Studio can persist thread state.
# ────────────────────────────────────────────────────────────────────────────

class SupervisorState(TypedDict, total=False):
    goal: str
    context: dict[str, Any]
    plan: dict[str, Any]
    outputs: dict[str, Any]
    active_agents: list[str]
    next_agent_idx: int
    max_iterations: int
    iterations: int
    final: dict[str, Any]


def _build_supervisor_graph():
    supervisor = get_supervisor_agent()
    research = get_research_agent()
    terminal = get_terminal_agent()
    script_ops = get_script_ops_agent()
    synthesis = get_synthesis_agent()

    g = StateGraph(SupervisorState)

    async def supervisor_node(state: SupervisorState) -> SupervisorState:
        plan = await supervisor.create_plan(state["goal"], state.get("context", {}))
        active = [a for a in plan.get("selected_agents", []) if a != "synthesis_agent"]
        return {
            "plan": plan,
            "outputs": {},
            "active_agents": active,
            "next_agent_idx": 0,
            "iterations": 0,
        }

    async def route_node(state: SupervisorState) -> SupervisorState:
        return state

    async def research_node(state: SupervisorState) -> SupervisorState:
        out = dict(state.get("outputs", {}))
        ctx = state.get("context", {})
        out["research"] = await research.run(
            question=state["goal"],
            top_k=5,
            tenant_id=ctx.get("tenant_id"),
            filters=ctx.get("filters", {}),
        )
        return {
            "outputs": out,
            "next_agent_idx": state.get("next_agent_idx", 0) + 1,
            "iterations": state.get("iterations", 0) + 1,
        }

    async def terminal_node(state: SupervisorState) -> SupervisorState:
        out = dict(state.get("outputs", {}))
        out["terminal"] = await terminal.run(task=state["goal"])
        return {
            "outputs": out,
            "next_agent_idx": state.get("next_agent_idx", 0) + 1,
            "iterations": state.get("iterations", 0) + 1,
        }

    async def script_ops_node(state: SupervisorState) -> SupervisorState:
        out = dict(state.get("outputs", {}))
        out["script_ops"] = await script_ops.run(
            action="script_requirements", payload={"goal": state["goal"]}
        )
        return {
            "outputs": out,
            "next_agent_idx": state.get("next_agent_idx", 0) + 1,
            "iterations": state.get("iterations", 0) + 1,
        }

    async def synthesis_node(state: SupervisorState) -> SupervisorState:
        final = await synthesis.run(
            goal=state["goal"],
            plan=state.get("plan", {}),
            outputs=state.get("outputs", {}),
        )
        return {"final": final}

    def next_step(
        state: SupervisorState,
    ) -> Literal["research", "terminal", "script_ops", "synthesis"]:
        idx = state.get("next_agent_idx", 0)
        agents = state.get("active_agents", [])
        if idx >= len(agents):
            return "synthesis"
        if state.get("iterations", 0) >= state.get("max_iterations", 3):
            return "synthesis"
        agent = agents[idx]
        if agent == "research_agent":
            return "research"
        if agent == "terminal_agent":
            return "terminal"
        if agent == "script_ops_agent":
            return "script_ops"
        return "synthesis"

    g.add_node("supervisor", supervisor_node)
    g.add_node("route", route_node)
    g.add_node("research", research_node)
    g.add_node("terminal", terminal_node)
    g.add_node("script_ops", script_ops_node)
    g.add_node("synthesis", synthesis_node)

    g.set_entry_point("supervisor")
    g.add_edge("supervisor", "route")
    g.add_conditional_edges("route", next_step)
    g.add_edge("research", "route")
    g.add_edge("terminal", "route")
    g.add_edge("script_ops", "route")
    g.add_edge("synthesis", END)

    # NOTE: no custom checkpointer — LangGraph API manages persistence itself.
    return g.compile()


# ────────────────────────────────────────────────────────────────────────────
# Graph 2: ui_factory_v1  (Studio-compatible stub)
#
# UIFactoryGraph is implemented as a sequential Python orchestrator, NOT as
# a LangGraph StateGraph.  This means it cannot be compiled by LangGraph
# directly.  Instead, we expose a lightweight StateGraph that mirrors the
# UIFactory step sequence so Studio can visualize and invoke the pipeline.
#
# Important: this stub delegates each step to the real UIFactoryGraph logic
# when invoked, so traces are real.  The only difference is that Studio sees
# discrete nodes rather than a black-box async loop.
# ────────────────────────────────────────────────────────────────────────────

class UIFactoryState(TypedDict, total=False):
    # inputs
    goal: str
    app_name: str | None
    tenant_id: str | None
    project_type: str | None
    deploy: bool
    publish_memory: bool
    context: dict[str, Any]
    # internal
    run_id: str
    node_results: dict[str, Any]
    last_completed_step: str | None
    # output
    final_result: dict[str, Any]


def _build_ui_factory_graph():
    from app.adapters.hapi_client import HapiClient
    from app.adapters.rag_server_adapter import RagServerAdapter
    from app.adapters.terminal_tools_adapter import TerminalToolsAdapter
    from app.agents.failure_recovery_agent import FailureRecoveryAgent
    from app.graphs.ui_factory_graph import UIFactoryGraph
    from app.services.container import (
        get_failure_recovery_agent,
        get_hapi_client,
        get_rag_adapter,
        get_terminal_adapter,
    )
    import uuid

    settings = get_settings()
    ui_factory = UIFactoryGraph(
        settings=settings,
        terminal=get_terminal_adapter(),
        rag=get_rag_adapter(),
        hapi=get_hapi_client(),
        recovery=get_failure_recovery_agent(),
    )

    # Group UIFactory STEPS into Studio-visible macro-nodes
    MACRO_NODES = [
        ("discover", ["discover_existing_ui"]),
        ("plan", ["plan_ui_solution", "classify_ui_complexity", "decide_data_strategy", "decide_tool_strategy"]),
        ("workspace", ["ensure_project_workspace", "plan_workspace_changes"]),
        ("build", ["run_ui_planning", "consolidate_ui_plan", "create_ui_task_list", "run_ui_execution", "integrate_ui_work"]),
        ("validate", ["validate_ui"]),
        ("publish", ["publish_to_git"]),
        ("deploy", ["resolve_public_state_with_hapi", "deploy_via_coolify", "ensure_public_availability", "register_public_result_in_hapi"]),
        ("memory", ["ingest_ui_memory_to_rag", "synthesize_result"]),
    ]

    g = StateGraph(UIFactoryState)

    def _make_macro_node(name: str, steps: list[str]):
        async def macro_node(state: UIFactoryState) -> UIFactoryState:
            run_id = state.get("run_id") or str(uuid.uuid4())
            node_results = dict(state.get("node_results") or {})
            last = state.get("last_completed_step")

            logs: list[dict[str, Any]] = []

            def _log(event: str, payload: dict[str, Any]) -> None:
                logs.append({"event": event, "payload": payload})

            # Build minimal state for UIFactory
            ui_state: dict[str, Any] = {
                "run_id": run_id,
                "goal": state.get("goal", ""),
                "request": {
                    "goal": state.get("goal", ""),
                    "app_name": state.get("app_name"),
                    "tenant_id": state.get("tenant_id"),
                    "project_type": state.get("project_type", "long_lived"),
                    "deploy": state.get("deploy", True),
                    "publish_memory": state.get("publish_memory", False),
                    "context": state.get("context", {}),
                },
                "context": state.get("context", {}),
                "node_results": node_results,
                "last_completed_step": last,
            }

            for step in steps:
                try:
                    step_fn = getattr(ui_factory, step)
                    result = await step_fn(ui_state)
                    ui_state["node_results"][step] = result
                    ui_state["last_completed_step"] = step
                    _log(f"step_completed:{step}", {})
                except Exception as exc:
                    _log(f"step_failed:{step}", {"error": str(exc)})
                    # Don't abort all steps – capture error and continue
                    ui_state["node_results"][step] = {"error": str(exc)}

            final = ui_state.get("final_result") or ui_state.get("node_results", {}).get("synthesize_result", {})
            return {
                "run_id": run_id,
                "node_results": ui_state["node_results"],
                "last_completed_step": ui_state.get("last_completed_step"),
                "final_result": final,
            }

        macro_node.__name__ = name
        return macro_node

    # Register nodes
    node_names = [name for name, _ in MACRO_NODES]
    for name, steps in MACRO_NODES:
        g.add_node(name, _make_macro_node(name, steps))

    g.set_entry_point(node_names[0])
    for i in range(len(node_names) - 1):
        g.add_edge(node_names[i], node_names[i + 1])
    g.add_edge(node_names[-1], END)

    # NOTE: no custom checkpointer — LangGraph API manages persistence itself.
    return g.compile()


# ── Module-level compiled graph singletons ────────────────────────────────
# LangGraph Studio imports these by name from langgraph.json entries.
supervisor_graph = _build_supervisor_graph()
ui_factory_graph = _build_ui_factory_graph()

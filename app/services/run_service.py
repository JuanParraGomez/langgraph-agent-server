from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.agents.research_agent import ResearchAgent
from app.agents.script_ops_agent import ScriptOpsAgent
from app.agents.supervisor_agent import SupervisorAgent
from app.agents.synthesis_agent import SynthesisAgent
from app.agents.terminal_agent import TerminalAgent
from app.graphs.complex_graph import ComplexTaskGraph, LANGGRAPH_AVAILABLE
from app.models.schemas import (
    ComplexTaskRequest,
    PlanTaskRequest,
    ResearchSubtaskRequest,
    RunRecord,
    RunStatus,
    ScriptOpsSubtaskRequest,
    SummarizeFindingsRequest,
    TerminalSubtaskRequest,
)
from app.services.provider_service import ProviderService
from app.storage.run_store import RunStore


class RunService:
    def __init__(
        self,
        store: RunStore,
        provider_service: ProviderService,
        supervisor: SupervisorAgent,
        research: ResearchAgent,
        terminal: TerminalAgent,
        script_ops: ScriptOpsAgent,
        synthesis: SynthesisAgent,
    ) -> None:
        self.store = store
        self.provider_service = provider_service
        self.supervisor = supervisor
        self.research = research
        self.terminal = terminal
        self.script_ops = script_ops
        self.synthesis = synthesis
        self.graph = ComplexTaskGraph(
            supervisor=supervisor,
            research=research,
            terminal=terminal,
            script_ops=script_ops,
            synthesis=synthesis,
        )

    async def run_complex(self, req: ComplexTaskRequest) -> RunRecord:
        run = self._create_pending_run(goal=req.goal, graph="supervisor_v1")
        started_at = datetime.now(timezone.utc)
        self.store.update_run(run.run_id, status=RunStatus.running, started_at=started_at)
        self.store.append_log(run.run_id, "run_started", {"goal": req.goal})

        try:
            graph_result = await self.graph.run(req.goal, req.context, req.max_iterations)
            plan = graph_result.get("plan", {})
            outputs = graph_result.get("outputs", {})
            final = graph_result.get("final", {})

            selected_agents = plan.get("selected_agents", ["synthesis_agent"])
            tools_used = self._extract_tools_used(outputs)
            providers_used = self._extract_providers_used()

            self.store.append_log(run.run_id, "graph_completed", {"engine": graph_result.get("engine")})
            self.store.append_log(run.run_id, "finalized", final)

            self.store.update_run(
                run.run_id,
                status=RunStatus.succeeded,
                finished_at=datetime.now(timezone.utc),
                selected_agents=selected_agents,
                providers_used=providers_used,
                external_tools_used=tools_used,
                summary=_build_summary(final),
                result={
                    "plan": plan,
                    "outputs": outputs,
                    "final": final,
                    "engine": graph_result.get("engine"),
                },
            )
        except Exception as exc:
            self.store.append_log(run.run_id, "run_failed", {"error": str(exc)})
            self.store.update_run(
                run.run_id,
                status=RunStatus.failed,
                finished_at=datetime.now(timezone.utc),
                error=str(exc),
            )

        final_run = self.store.get_run(run.run_id)
        if final_run is None:
            raise RuntimeError("run not found after completion")
        return final_run

    async def plan_only(self, req: PlanTaskRequest) -> dict[str, Any]:
        plan = await self.supervisor.create_plan(goal=req.goal, context=req.context)
        return {"plan": plan, "graph": "supervisor_v1", "langgraph_available": LANGGRAPH_AVAILABLE}

    async def run_research(self, req: ResearchSubtaskRequest) -> dict[str, Any]:
        return await self.research.run(question=req.question, top_k=req.top_k)

    async def run_terminal(self, req: TerminalSubtaskRequest) -> dict[str, Any]:
        return await self.terminal.run(task=req.task)

    async def run_script_ops(self, req: ScriptOpsSubtaskRequest) -> dict[str, Any]:
        return await self.script_ops.run(action=req.action, payload=req.payload)

    async def summarize_findings(self, req: SummarizeFindingsRequest) -> dict[str, Any]:
        run = self.store.get_run(req.run_id)
        if run is None:
            return {"ok": False, "error": "run_not_found"}
        if run.result is None:
            return {"ok": False, "error": "run_has_no_result"}

        final = await self.synthesis.run(
            goal=run.requested_goal,
            plan=run.result.get("plan", {}),
            outputs=run.result.get("outputs", {}),
        )
        return {"ok": True, "summary": final.get("final", {})}

    def get_run(self, run_id: str) -> RunRecord | None:
        return self.store.get_run(run_id)

    def get_run_logs(self, run_id: str) -> list[dict[str, Any]]:
        return self.store.read_logs(run_id)

    def _create_pending_run(self, goal: str, graph: str) -> RunRecord:
        run = RunRecord(
            run_id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            status=RunStatus.pending,
            requested_goal=goal,
            selected_graph=graph,
            selected_agents=[],
            providers_used=[],
            external_tools_used=[],
        )
        self.store.create_run(run)
        return run

    def _extract_tools_used(self, outputs: dict[str, Any]) -> list[str]:
        mapping = {
            "research": "rag-server",
            "terminal": "terminal-tools",
            "script_ops": "celery-server",
        }
        return [tool for key, tool in mapping.items() if key in outputs]

    def _extract_providers_used(self) -> list[str]:
        caps = self.provider_service.capabilities()
        used: list[str] = []
        for name, meta in caps.items():
            if meta.get("available"):
                used.append(name)
        return used


def _build_summary(final: dict[str, Any]) -> str:
    if not final:
        return "No synthesis output"
    content = final.get("final")
    if isinstance(content, dict):
        return content.get("recommendation", "Completed")
    return "Completed"

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.agents.research_agent import ResearchAgent
from app.agents.memory_review_agent import MemoryReviewAgent
from app.agents.prompt_engineer_agent import PromptEngineerAgent
from app.agents.script_ops_agent import ScriptOpsAgent
from app.agents.supervisor_agent import SupervisorAgent
from app.agents.synthesis_agent import SynthesisAgent
from app.agents.terminal_agent import TerminalAgent
from app.adapters.rag_server_adapter import RagServerAdapter
from app.graphs.complex_graph import ComplexTaskGraph, LANGGRAPH_AVAILABLE
from app.models.schemas import (
    ComplexTaskRequest,
    PlanTaskRequest,
    PromptWorkflowRequest,
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
        memory_review: MemoryReviewAgent,
        terminal: TerminalAgent,
        script_ops: ScriptOpsAgent,
        synthesis: SynthesisAgent,
        prompt_engineer: PromptEngineerAgent,
        rag_adapter: RagServerAdapter,
    ) -> None:
        self.store = store
        self.provider_service = provider_service
        self.supervisor = supervisor
        self.research = research
        self.memory_review = memory_review
        self.terminal = terminal
        self.script_ops = script_ops
        self.synthesis = synthesis
        self.prompt_engineer = prompt_engineer
        self.rag_adapter = rag_adapter
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

    async def run_prompt_workflow(self, req: PromptWorkflowRequest) -> RunRecord:
        run = self._create_pending_run(goal=req.goal, graph="prompt_workflow_v1")
        started_at = datetime.now(timezone.utc)
        self.store.update_run(run.run_id, status=RunStatus.running, started_at=started_at)
        self.store.append_log(run.run_id, "prompt_workflow_started", {"goal": req.goal})

        try:
            context = dict(req.context)
            if req.agent_name:
                context["agent_name"] = req.agent_name
            if req.current_version:
                context["current_version"] = req.current_version

            memory = await self.memory_review.run(
                goal=req.goal,
                tenant_id=req.tenant_id,
                context=context,
            )
            self.store.append_log(run.run_id, "memory_review_completed", memory)

            prompt_package = await self.prompt_engineer.run(
                goal=req.goal,
                context=context,
                similar_results=memory,
            )
            self.store.append_log(run.run_id, "prompt_package_created", prompt_package)

            publication: dict[str, Any] | None = None
            if req.publish_learning:
                publication = await self.rag_adapter.upload_learning(
                    text=prompt_package["prompts"]["rag_learning_text"],
                    tenant_id=req.tenant_id or context.get("tenant_id") or "tenant-stack-probe",
                    title=f"{prompt_package['agent_name']} {prompt_package['current_version']} workflow memory",
                    metadata={
                        "artifact_type": "agent_learning",
                        "agent_name": prompt_package["agent_name"],
                        "workflow_version": prompt_package["current_version"],
                        "source_service": "langgraph-agent-server",
                        "workflow": prompt_package["workflow"],
                    },
                )
                self.store.append_log(run.run_id, "rag_learning_published", publication)

            result = {
                "memory_review": memory,
                "prompt_package": prompt_package,
                "rag_publication": publication,
            }
            self.store.update_run(
                run.run_id,
                status=RunStatus.succeeded,
                finished_at=datetime.now(timezone.utc),
                selected_agents=["memory_review_agent", "prompt_engineer_agent"],
                providers_used=[prompt_package["provider_used"]] if prompt_package.get("provider_used") else [],
                external_tools_used=["rag-server"],
                summary="Prompt workflow completed and learning prepared for reuse.",
                result=result,
            )
        except Exception as exc:
            self.store.append_log(run.run_id, "prompt_workflow_failed", {"error": str(exc)})
            self.store.update_run(
                run.run_id,
                status=RunStatus.failed,
                finished_at=datetime.now(timezone.utc),
                error=str(exc),
            )

        final_run = self.store.get_run(run.run_id)
        if final_run is None:
            raise RuntimeError("run not found after prompt workflow")
        return final_run

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

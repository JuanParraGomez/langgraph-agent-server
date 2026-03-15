from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.agents.research_agent import ResearchAgent
from app.agents.memory_review_agent import MemoryReviewAgent
from app.agents.failure_recovery_agent import FailureRecoveryAgent
from app.agents.prompt_engineer_agent import PromptEngineerAgent
from app.agents.script_ops_agent import ScriptOpsAgent
from app.agents.supervisor_agent import SupervisorAgent
from app.agents.synthesis_agent import SynthesisAgent
from app.agents.terminal_agent import TerminalAgent
from app.adapters.hapi_client import HapiClient
from app.adapters.rag_server_adapter import RagServerAdapter
from app.core.settings import Settings
from app.graphs.complex_graph import ComplexTaskGraph, LANGGRAPH_AVAILABLE
from app.graphs.ui_factory_graph import UIFactoryCancelledError, UIFactoryGraph, UIFactoryStepError
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
    UIFactoryRequest,
)
from app.observability.langsmith_setup import invoke_graph_traced
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
        failure_recovery: FailureRecoveryAgent,
        rag_adapter: RagServerAdapter,
        hapi_client: HapiClient,
        settings: Settings,
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
        self.failure_recovery = failure_recovery
        self.rag_adapter = rag_adapter
        self.hapi_client = hapi_client
        self.settings = settings
        self.graph = ComplexTaskGraph(
            supervisor=supervisor,
            research=research,
            terminal=terminal,
            script_ops=script_ops,
            synthesis=synthesis,
        )
        self.ui_factory = UIFactoryGraph(
            settings=settings,
            terminal=terminal.terminal_adapter,
            rag=rag_adapter,
            hapi=hapi_client,
            recovery=failure_recovery,
            is_cancelled=store.is_cancelled,
        )

    async def run_complex(self, req: ComplexTaskRequest) -> RunRecord:
        run = self._create_pending_run(goal=req.goal, graph="supervisor_v1")
        started_at = datetime.now(timezone.utc)
        self.store.update_run(run.run_id, status=RunStatus.running, started_at=started_at)
        self.store.append_log(run.run_id, "run_started", {"goal": req.goal})

        try:
            graph_result = await invoke_graph_traced(
                "supervisor_graph_run",
                self.graph.run,
                req.goal,
                req.context,
                req.max_iterations,
                trace_tags=["graph:supervisor_v1", "run:complex"],
                trace_metadata=self._trace_metadata(run_id=run.run_id, goal=req.goal, max_iterations=req.max_iterations),
            )
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
        plan = await invoke_graph_traced(
            "supervisor_plan_only",
            self.supervisor.create_plan,
            goal=req.goal,
            context=req.context,
            trace_tags=["graph:supervisor_v1", "run:plan_only"],
            trace_metadata=self._trace_metadata(goal=req.goal),
        )
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

            memory = await invoke_graph_traced(
                "prompt_workflow_memory_review",
                self.memory_review.run,
                goal=req.goal,
                tenant_id=req.tenant_id,
                context=context,
                trace_run_type="tool",
                trace_tags=["graph:prompt_workflow_v1", "agent:memory_review_agent"],
                trace_metadata=self._trace_metadata(run_id=run.run_id, goal=req.goal, tenant_id=req.tenant_id),
            )
            self.store.append_log(run.run_id, "memory_review_completed", memory)

            prompt_package = await invoke_graph_traced(
                "prompt_workflow_prompt_engineer",
                self.prompt_engineer.run,
                goal=req.goal,
                context=context,
                similar_results=memory,
                trace_run_type="tool",
                trace_tags=["graph:prompt_workflow_v1", "agent:prompt_engineer_agent"],
                trace_metadata=self._trace_metadata(run_id=run.run_id, goal=req.goal, tenant_id=req.tenant_id),
            )
            self.store.append_log(run.run_id, "prompt_package_created", prompt_package)

            publication: dict[str, Any] | None = None
            if req.publish_learning:
                learning_metadata = {
                    "artifact_type": "agent_learning",
                    "agent_name": prompt_package["agent_name"],
                    "workflow_version": prompt_package["current_version"],
                    "source_service": "langgraph-agent-server",
                    "workflow": prompt_package["workflow"],
                }
                publication = await invoke_graph_traced(
                    "prompt_workflow_publish_rag_memory",
                    self.rag_adapter.upload_learning,
                    text=prompt_package["prompts"]["rag_learning_text"],
                    tenant_id=req.tenant_id or context.get("tenant_id") or "tenant-stack-probe",
                    title=f"{prompt_package['agent_name']} {prompt_package['current_version']} workflow memory",
                    metadata=learning_metadata,
                    trace_run_type="tool",
                    trace_tags=["graph:prompt_workflow_v1", "tool:rag-server"],
                    trace_metadata=self._trace_metadata(run_id=run.run_id, tenant_id=req.tenant_id),
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

    async def run_ui_factory(self, req: UIFactoryRequest) -> RunRecord:
        run = self._create_pending_run(goal=req.goal, graph="ui_factory_v1")
        resume_state = None
        if req.resume_run_id:
            previous = self.store.get_run(req.resume_run_id)
            if previous and previous.result:
                resume_state = previous.result.get("state")
        started_at = datetime.now(timezone.utc)
        self.store.update_run(run.run_id, status=RunStatus.running, started_at=started_at)
        self.store.append_log(run.run_id, "ui_factory_started", {"goal": req.goal, "resume_run_id": req.resume_run_id})

        def _log(event: str, payload: dict[str, Any]) -> None:
            self.store.append_log(run.run_id, event, payload)

        try:
            state = await invoke_graph_traced(
                "ui_factory_graph_run",
                self.ui_factory.run,
                request=req.model_dump(mode="python"),
                run_id=run.run_id,
                previous_state=resume_state,
                log=_log,
                trace_tags=["graph:ui_factory_v1", "run:ui_factory"],
                trace_metadata=self._trace_metadata(run_id=run.run_id, goal=req.goal, app_name=req.app_name, tenant_id=req.tenant_id),
            )
            final = state.get("final_result", {})
            tools_used = ["terminal-tools", "hapi", "rag-server"]
            self.store.update_run(
                run.run_id,
                status=RunStatus.succeeded,
                finished_at=datetime.now(timezone.utc),
                selected_agents=[
                    "discover_existing_ui",
                    "plan_ui_solution",
                    "ui_complexity_agent",
                    "workspace_planner_agent",
                    "build_or_update_ui",
                    "ui_integrator_agent",
                    "deploy_via_coolify",
                    "register_public_result_in_hapi",
                    "ingest_ui_memory_to_rag",
                ],
                providers_used=[],
                external_tools_used=tools_used,
                summary=final.get("summary", "UI factory completed"),
                result={"state": state, "final": final},
            )
        except UIFactoryCancelledError as exc:
            partial_state = locals().get("state", resume_state or {})
            self.store.update_run(
                run.run_id,
                status=RunStatus.cancelled,
                finished_at=datetime.now(timezone.utc),
                selected_agents=["ui_factory_v1"],
                external_tools_used=["terminal-tools", "hapi", "rag-server"],
                error=str(exc),
                result={"state": partial_state, "cancelled_step": exc.step},
            )
            self.store.append_log(run.run_id, "ui_factory_cancelled", {"step": exc.step, "error": str(exc)})
        except UIFactoryStepError as exc:
            partial_state = locals().get("state", resume_state or {})
            self.store.append_log(
                run.run_id,
                "ui_factory_failure_detail",
                {
                    "failed_step": exc.step,
                    "error": str(exc),
                    "partial_state_keys": sorted(partial_state.keys()) if isinstance(partial_state, dict) else [],
                },
            )
            self.store.update_run(
                run.run_id,
                status=RunStatus.failed,
                finished_at=datetime.now(timezone.utc),
                selected_agents=["ui_factory_v1"],
                external_tools_used=["terminal-tools", "hapi", "rag-server"],
                error=f"{exc.step}:{exc}",
                result={"state": partial_state, "failed_step": exc.step},
            )
            self.store.append_log(run.run_id, "ui_factory_failed", {"step": exc.step, "error": str(exc)})
        except Exception as exc:
            self.store.update_run(
                run.run_id,
                status=RunStatus.failed,
                finished_at=datetime.now(timezone.utc),
                selected_agents=["ui_factory_v1"],
                external_tools_used=["terminal-tools", "hapi", "rag-server"],
                error=str(exc),
            )
            self.store.append_log(run.run_id, "ui_factory_failed", {"error": str(exc)})

        final_run = self.store.get_run(run.run_id)
        if final_run is None:
            raise RuntimeError("run not found after ui factory")
        return final_run

    def cancel_run(self, run_id: str, reason: str | None = None) -> RunRecord | None:
        return self.store.cancel_run(run_id, reason)

    async def run_research(self, req: ResearchSubtaskRequest) -> dict[str, Any]:
        return await invoke_graph_traced(
            "subtask_research",
            self.research.run,
            question=req.question,
            top_k=req.top_k,
            trace_run_type="tool",
            trace_tags=["subtask:research", "agent:research_agent"],
            trace_metadata=self._trace_metadata(question=req.question, top_k=req.top_k),
        )

    async def run_terminal(self, req: TerminalSubtaskRequest) -> dict[str, Any]:
        return await invoke_graph_traced(
            "subtask_terminal",
            self.terminal.run,
            task=req.task,
            trace_run_type="tool",
            trace_tags=["subtask:terminal", "agent:terminal_agent"],
            trace_metadata=self._trace_metadata(task=req.task),
        )

    async def run_script_ops(self, req: ScriptOpsSubtaskRequest) -> dict[str, Any]:
        return await invoke_graph_traced(
            "subtask_script_ops",
            self.script_ops.run,
            action=req.action,
            payload=req.payload,
            trace_run_type="tool",
            trace_tags=["subtask:script_ops", "agent:script_ops_agent"],
            trace_metadata=self._trace_metadata(action=req.action),
        )

    async def summarize_findings(self, req: SummarizeFindingsRequest) -> dict[str, Any]:
        run = self.store.get_run(req.run_id)
        if run is None:
            return {"ok": False, "error": "run_not_found"}
        if run.result is None:
            return {"ok": False, "error": "run_has_no_result"}

        final = await invoke_graph_traced(
            "summarize_run_findings",
            self.synthesis.run,
            goal=run.requested_goal,
            plan=run.result.get("plan", {}),
            outputs=run.result.get("outputs", {}),
            trace_run_type="tool",
            trace_tags=["agent:synthesis_agent", "run:summarize_findings"],
            trace_metadata=self._trace_metadata(run_id=req.run_id),
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

    def _trace_metadata(self, **values: Any) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for key, value in values.items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                metadata[key] = value
            else:
                metadata[key] = str(value)
        metadata["service"] = self.settings.server_name
        return metadata


def _build_summary(final: dict[str, Any]) -> str:
    if not final:
        return "No synthesis output"
    content = final.get("final")
    if isinstance(content, dict):
        return content.get("recommendation", "Completed")
    return "Completed"

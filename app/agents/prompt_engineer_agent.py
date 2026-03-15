from __future__ import annotations

from typing import Any

from app.services.deepseek_service import DeepSeekService


class PromptEngineerAgent:
    name = "prompt_engineer_agent"

    def __init__(self, deepseek_service: DeepSeekService | None = None) -> None:
        self.deepseek_service = deepseek_service

    async def run(
        self,
        goal: str,
        context: dict[str, Any],
        similar_results: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        text = goal.lower()
        complexity = int(context.get("complexity", 3))
        agent_name = str(context.get("agent_name") or "generated_agent").strip() or "generated_agent"
        current_version = str(context.get("current_version") or "v1").strip() or "v1"

        workflow = self._select_workflow(text=text, complexity=complexity)
        similar_summary = self._summarize_similar(similar_results)

        if self.deepseek_service and self.deepseek_service.available():
            try:
                generated = await self.deepseek_service.generate_prompt_package(
                    goal=goal,
                    agent_name=agent_name,
                    current_version=current_version,
                    context=context,
                    similar_summary=similar_summary,
                    fallback_workflow=workflow,
                )
                return {
                    "ok": True,
                    "agent": self.name,
                    "workflow": generated.get("workflow", workflow),
                    "agent_name": agent_name,
                    "current_version": current_version,
                    "recommended_sequence": generated.get("recommended_sequence", self._recommended_sequence(workflow)),
                    "prompts": {
                        "planning_prompt": generated.get("planning_prompt", ""),
                        "execution_prompt": generated.get("execution_prompt", ""),
                        "validation_prompt": generated.get("validation_prompt", ""),
                        "rag_learning_text": generated.get("rag_learning_text", ""),
                    },
                    "similar_summary": similar_summary,
                    "provider_used": generated.get("provider_used", "deepseek"),
                    "model_used": generated.get("model_used"),
                    "rationale": generated.get("rationale"),
                }
            except Exception:
                pass

        planning_prompt = self._planning_prompt(goal, agent_name, current_version, context, similar_summary)
        execution_prompt = self._execution_prompt(goal, agent_name, current_version, workflow, context, similar_summary)
        validation_prompt = self._validation_prompt(agent_name, workflow)
        learning_text = self._learning_text(goal, agent_name, current_version, workflow, similar_summary)

        return {
            "ok": True,
            "agent": self.name,
            "workflow": workflow,
            "agent_name": agent_name,
            "current_version": current_version,
            "recommended_sequence": self._recommended_sequence(workflow),
            "prompts": {
                "planning_prompt": planning_prompt,
                "execution_prompt": execution_prompt,
                "validation_prompt": validation_prompt,
                "rag_learning_text": learning_text,
            },
            "similar_summary": similar_summary,
            "provider_used": "heuristic",
        }

    def _select_workflow(self, text: str, complexity: int) -> str:
        if any(token in text for token in ["plan", "arquitect", "estrateg", "diseña", "diseña"]) and complexity >= 4:
            return "copilot_plan_then_codex"
        if complexity >= 4 or any(token in text for token in ["varios archivos", "itera", "estabiliza", "multiarchivo", "refactor grande"]):
            return "copilot_plan_then_codex"
        if any(token in text for token in ["test pequeño", "cambio puntual", "fix corto", "bug pequeño", "ajuste corto"]) or complexity <= 2:
            return "copilot_small_change"
        return "copilot_plan_then_codex"

    def _recommended_sequence(self, workflow: str) -> list[dict[str, Any]]:
        if workflow == "copilot_small_change":
            return [
                {
                    "step": 1,
                    "tool": "terminal-tools",
                    "endpoint": "/run/copilot",
                    "purpose": "Apply a small code change with the cheapest Copilot profile available",
                },
                {
                    "step": 2,
                    "tool": "terminal-tools",
                    "endpoint": "/run/codex",
                    "optional": True,
                    "purpose": "Only escalate if Copilot leaves the task incomplete or tests unstable",
                },
            ]
        return [
            {
                "step": 1,
                "tool": "terminal-tools",
                "endpoint": "/run/copilot-plan",
                "purpose": "Produce plan with cheap-model policy: Claude Haiku 4.5 for planning",
            },
            {
                "step": 2,
                "tool": "terminal-tools",
                "endpoint": "/run/codex",
                "purpose": "Execute the multi-step code change iteratively until stable",
            },
            {
                "step": 3,
                "tool": "terminal-tools",
                "endpoint": "/run/copilot",
                "optional": True,
                "purpose": "Use Copilot for cheap follow-up fixes or micro-edits after Codex finishes",
            },
        ]

    def _planning_prompt(
        self,
        goal: str,
        agent_name: str,
        current_version: str,
        context: dict[str, Any],
        similar_summary: dict[str, Any],
    ) -> str:
        return "\n".join(
            [
                f"Task: Create or improve the code workflow for '{agent_name}' version {current_version}.",
                f"Goal: {goal}",
                f"Constraints: {context.get('constraints') or 'Keep the change minimal and testable.'}",
                f"ExistingSimilarWork: {similar_summary}",
                "ModelPolicy: use only GPT-5 mini or GPT-4.1 for Copilot coding; use Claude Haiku 4.5 for planning/review.",
                "Return only a concrete implementation plan.",
                "Include impacted files, order of work, validation steps, rollback notes, and risk checkpoints.",
                "Do not edit files in this phase.",
            ]
        )

    def _execution_prompt(
        self,
        goal: str,
        agent_name: str,
        current_version: str,
        workflow: str,
        context: dict[str, Any],
        similar_summary: dict[str, Any],
    ) -> str:
        return "\n".join(
            [
                f"Objective: implement the required code change for '{agent_name}' version {current_version}.",
                f"Goal: {goal}",
                f"Workflow: {workflow}",
                f"ExistingSimilarWork: {similar_summary}",
                f"AcceptanceCriteria: {context.get('acceptance_criteria') or 'Tests for the touched behavior must pass.'}",
                "ModelPolicy: use only GPT-5 mini or GPT-4.1 for Copilot coding; use Claude Haiku 4.5 for planning/review.",
                "Prefer the smallest correct change.",
                "If the task spans multiple files or requires stabilization, iterate until the result is consistent.",
                "At the end, summarize exactly what changed, how it works, and what remains risky.",
            ]
        )

    def _validation_prompt(self, agent_name: str, workflow: str) -> str:
        return "\n".join(
            [
                f"Validate the implementation for '{agent_name}'.",
                f"WorkflowUsed: {workflow}",
                "List the exact tests or commands that should run.",
                "State pass/fail criteria.",
                "If failures remain, identify the smallest next corrective action.",
            ]
        )

    def _learning_text(
        self,
        goal: str,
        agent_name: str,
        current_version: str,
        workflow: str,
        similar_summary: dict[str, Any],
    ) -> str:
        return "\n".join(
            [
                f"AgentName: {agent_name}",
                f"Version: {current_version}",
                f"Workflow: {workflow}",
                f"Goal: {goal}",
                f"SimilarContext: {similar_summary}",
                "Learning:",
                "- For complex code tasks, route first to Copilot plan mode and then execute with Codex.",
                "- For small code fixes, prefer cheap Copilot execution before escalating.",
                "- Persist implementation notes, validation summary, and remaining risks after execution.",
            ]
        )

    def _summarize_similar(self, similar_results: dict[str, Any] | None) -> dict[str, Any]:
        if not similar_results or not similar_results.get("ok"):
            return {"found": False, "items": []}

        data = similar_results.get("data", {})
        sources = data.get("sources") or []
        items: list[dict[str, Any]] = []
        for source in sources[:3]:
            meta = source.get("metadata", {})
            items.append(
                {
                    "document_id": meta.get("document_id"),
                    "title": meta.get("title"),
                    "version": meta.get("workflow_version") or meta.get("version"),
                    "artifact_type": meta.get("artifact_type"),
                    "score": source.get("score"),
                }
            )
        return {"found": bool(items), "items": items}

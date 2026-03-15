from __future__ import annotations

from typing import Any

from app.services.claude_api_service import ClaudeApiService


class PromptEngineerAgent:
    name = "prompt_engineer_agent"

    def __init__(self, claude_service: ClaudeApiService | None = None) -> None:
        self.claude_service = claude_service

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

        if self.claude_service and self.claude_service.available():
            try:
                generated = await self.claude_service.generate_prompt_package(
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
                    "provider_used": generated.get("provider_used", "anthropic"),
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
            return "claude_plan_then_claude"
        if complexity >= 4 or any(token in text for token in ["varios archivos", "itera", "estabiliza", "multiarchivo", "refactor grande"]):
            return "claude_plan_then_claude"
        if any(token in text for token in ["test pequeño", "cambio puntual", "fix corto", "bug pequeño", "ajuste corto"]) or complexity <= 2:
            return "claude_small_change"
        return "claude_plan_then_claude"

    def _recommended_sequence(self, workflow: str) -> list[dict[str, Any]]:
        if workflow == "claude_small_change":
            return [
                {
                    "step": 1,
                    "tool": "terminal-tools",
                    "endpoint": "/run/claude",
                    "purpose": "Apply a small code change using Claude Haiku (fast, cheap)",
                },
            ]
        return [
            {
                "step": 1,
                "tool": "terminal-tools",
                "endpoint": "/run/claude-plan",
                "purpose": "Plan and apply multi-step code changes using Claude Sonnet",
            },
            {
                "step": 2,
                "tool": "terminal-tools",
                "endpoint": "/run/claude",
                "optional": True,
                "purpose": "Use Claude Haiku for follow-up fixes or micro-edits",
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
                "ModelPolicy: use Claude Haiku 4.5 for small/fast tasks; use Claude Sonnet 4.6 for planning, architecture, and complex code execution.",
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
                "ModelPolicy: use Claude Haiku 4.5 for small/fast tasks; use Claude Sonnet 4.6 for planning, architecture, and complex code execution.",
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
                "- For complex code tasks, route to Claude Sonnet (claude-plan endpoint) for planning and execution.",
                "- For small code fixes, prefer Claude Haiku (claude endpoint) before escalating.",
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

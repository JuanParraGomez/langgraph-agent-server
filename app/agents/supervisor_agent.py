from __future__ import annotations

from typing import Any


class SupervisorAgent:
    name = "supervisor_agent"

    async def create_plan(self, goal: str, context: dict[str, Any]) -> dict[str, Any]:
        text = goal.lower()
        steps: list[str] = []
        selected_agents: list[str] = []

        if any(k in text for k in ["investiga", "research", "document", "rag", "contexto"]):
            steps.append("Collect documentary context from rag-server")
            selected_agents.append("research_agent")

        if any(k in text for k in ["terminal", "repo", "inspeccion", "inspección", "logs", "archivo"]):
            steps.append("Run operational inspection through terminal-tools")
            selected_agents.append("terminal_agent")

        if any(k in text for k in ["script", ".sh", "deploy", "backup", "schedule", "job"]):
            steps.append("Execute script operations through celery-server")
            selected_agents.append("script_ops_agent")

        if not steps:
            steps = [
                "Collect concise context from rag-server",
                "Perform lightweight terminal inspection",
            ]
            selected_agents = ["research_agent", "terminal_agent"]

        selected_agents.append("synthesis_agent")

        return {
            "plan": steps,
            "selected_agents": selected_agents,
            "planner_used": "supervisor_v1_heuristic",
            "context_keys": list(context.keys()),
        }

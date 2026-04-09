from __future__ import annotations

import json
import logging
from typing import Any

from app.services.deepseek_service import DeepSeekService

logger = logging.getLogger(__name__)

AVAILABLE_AGENTS = [
    {
        "name": "research_agent",
        "capabilities": "RAG retrieval, document search, context gathering from rag-server",
    },
    {
        "name": "terminal_agent",
        "capabilities": "Shell commands, file inspection, repo operations via terminal-tools",
    },
    {
        "name": "script_ops_agent",
        "capabilities": "Script execution, scheduled jobs, deploy ops via celery-server",
    },
    {
        "name": "memory_review_agent",
        "capabilities": "Review and consolidate session memory stored in CanonDock",
    },
    {
        "name": "prompt_engineer_agent",
        "capabilities": "Generate prompt packages and code workflow plans for other agents",
    },
    {
        "name": "synthesis_agent",
        "capabilities": "Aggregate outputs from multiple agents into a coherent response (always last)",
    },
]

PLAN_SYSTEM_PROMPT = """\
You are a task planner for a multi-agent system. Given a user goal and available agents, \
produce a JSON execution plan.

Available agents:
{agents_json}

Rules:
- Select the minimum agents needed. Don't use agents unnecessarily.
- synthesis_agent is always appended automatically — do not include it.
- Order matters: agents execute sequentially in the order listed.
- For CODE tasks (programming, debugging, refactoring, tests, scripts):
    use terminal_agent with copilot_mode=true for best results.
- For research/docs/retrieval, prefer research_agent.
- For ops/deploy/scripts/cron, prefer script_ops_agent.

Return ONLY valid JSON with this schema:
{{"plan": ["step 1 description", "step 2 description"], "selected_agents": ["agent_name_1", "agent_name_2"], "rationale": "brief reason", "copilot_for_code": true|false}}
"""


class SupervisorAgent:
    name = "supervisor_agent"

    def __init__(self, deepseek_service: DeepSeekService | None = None) -> None:
        self.deepseek_service = deepseek_service

    async def create_plan(self, goal: str, context: dict[str, Any]) -> dict[str, Any]:
        if self.deepseek_service and self.deepseek_service.available():
            try:
                return await self._llm_plan(goal, context)
            except Exception as exc:
                logger.warning("LLM planner failed, falling back to heuristic: %s", exc)

        return self._heuristic_plan(goal, context)

    async def _llm_plan(self, goal: str, context: dict[str, Any]) -> dict[str, Any]:
        agents_json = json.dumps(AVAILABLE_AGENTS, indent=2)
        system = PLAN_SYSTEM_PROMPT.format(agents_json=agents_json)

        user_msg = json.dumps({
            "goal": goal,
            "context_keys": list(context.keys()),
            "session_id": context.get("session_id", "unknown"),
        })

        result = await self.deepseek_service.chat_completion(
            system_prompt=system,
            user_prompt=user_msg,
            temperature=0.1,
        )

        parsed = self._parse_plan(result)
        parsed["planner_used"] = "supervisor_v2_llm"
        parsed["context_keys"] = list(context.keys())

        if "synthesis_agent" not in parsed.get("selected_agents", []):
            parsed["selected_agents"].append("synthesis_agent")

        return parsed

    def _heuristic_plan(self, goal: str, context: dict[str, Any]) -> dict[str, Any]:
        """V1 fallback — keyword matching."""
        text = goal.lower()
        steps: list[str] = []
        selected_agents: list[str] = []

        # CODE tasks → terminal_agent with Copilot mode
        is_code_task = any(k in text for k in [
            "code", "debug", "refactor", "implement", "función", "function",
            "class", "test", "typescript", "python", "javascript", "build",
            "compile", "lint", "fix", "error", "bug", "script", "repo",
        ])
        if is_code_task:
            steps.append("Execute code task via terminal-tools using Copilot endpoint")
            selected_agents.append("terminal_agent")

        if any(k in text for k in ["investiga", "research", "document", "rag", "contexto", "busca", "find"]):
            steps.append("Collect documentary context from rag-server")
            selected_agents.append("research_agent")

        if not is_code_task and any(k in text for k in ["terminal", "inspeccion", "logs", "archivo", "file"]):
            steps.append("Run operational inspection through terminal-tools")
            selected_agents.append("terminal_agent")

        if any(k in text for k in [".sh", "deploy", "backup", "schedule", "job", "cron"]):
            steps.append("Execute script operations through celery-server")
            selected_agents.append("script_ops_agent")

        if not steps:
            steps = ["Collect concise context from rag-server"]
            selected_agents = ["research_agent"]

        selected_agents.append("synthesis_agent")

        return {
            "plan": steps,
            "selected_agents": selected_agents,
            "planner_used": "supervisor_v1_heuristic",
            "context_keys": list(context.keys()),
            "copilot_for_code": is_code_task,
        }

    @staticmethod
    def _parse_plan(raw: str) -> dict[str, Any]:
        """Extract JSON plan from LLM response, tolerating markdown fences."""
        text = raw.strip()
        if "```" in text:
            parts = text.split("```")
            for part in parts[1:]:
                candidate = part.strip()
                if candidate.startswith("json"):
                    candidate = candidate[4:].strip()
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "plan": ["Unable to parse LLM plan — executing default workflow"],
                "selected_agents": ["research_agent", "terminal_agent"],
                "rationale": f"Parse failure on: {text[:200]}",
            }

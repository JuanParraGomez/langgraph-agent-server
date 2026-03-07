from __future__ import annotations

from typing import Any

from app.adapters.base import HttpAdapter


class TerminalToolsAdapter(HttpAdapter):
    async def run_subtask(self, task: str) -> dict[str, Any]:
        payload = {
            "user_goal": task,
            "execution_mode": "sync",
            "complexity": 3,
            "needs_plan": False,
            "needs_second_opinion": False,
            "target_environment": "local",
            "requires_iteration": False,
            "requires_code_changes": False,
            "allowed_mutation_level": "readonly",
        }
        return await self._post("/run", payload)

    async def inspect_task(self, task_id: str) -> dict[str, Any]:
        return await self._get(f"/tasks/{task_id}")

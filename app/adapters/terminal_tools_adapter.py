from __future__ import annotations

from typing import Any

from app.adapters.base import HttpAdapter


class TerminalToolsAdapter(HttpAdapter):
    async def run_subtask(self, task: str) -> dict[str, Any]:
        payload = {"task": task}
        # Fallback endpoint: if backend does not implement this exact route,
        # caller still receives a structured error.
        return await self._post("/tasks/dispatch", payload)

    async def inspect_task(self, task_id: str) -> dict[str, Any]:
        return await self._get(f"/tasks/{task_id}")

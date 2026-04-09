from __future__ import annotations

from typing import Any

from app.adapters.base import HttpAdapter


class TerminalToolsAdapter(HttpAdapter):
    @staticmethod
    def _effective_timeout(timeout_seconds: int) -> int:
        return max(timeout_seconds + 120, 180)

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
        return await self._post("/run", payload, timeout_seconds=60)

    async def inspect_task(self, task_id: str) -> dict[str, Any]:
        return await self._get(f"/tasks/{task_id}")

    async def run_claude(self, *, objective: str, cwd: str | None = None, timeout_seconds: int = 900) -> dict[str, Any]:
        # Delegate to copilot endpoint — Claude CLI removed, Copilot (openai-codex) is the code runner
        return await self._post(
            "/run/copilot",
            {
                "user_goal": objective,
                "execution_mode": "sync",
                "cwd": cwd,
                "timeout_seconds": timeout_seconds,
            },
            timeout_seconds=self._effective_timeout(timeout_seconds),
        )

    async def run_claude_plan(self, *, objective: str, cwd: str | None = None, timeout_seconds: int = 1800) -> dict[str, Any]:
        # Delegate to copilot-plan endpoint — Claude CLI removed
        return await self._post(
            "/run/copilot-plan",
            {
                "user_goal": objective,
                "execution_mode": "sync",
                "cwd": cwd,
                "timeout_seconds": timeout_seconds,
            },
            timeout_seconds=self._effective_timeout(timeout_seconds),
        )

    # Legacy aliases — delegate to claude equivalents
    async def run_copilot_plan(self, *, objective: str, cwd: str | None = None, timeout_seconds: int = 900) -> dict[str, Any]:
        return await self.run_claude_plan(objective=objective, cwd=cwd, timeout_seconds=timeout_seconds)

    async def run_copilot(self, *, objective: str, cwd: str | None = None, timeout_seconds: int = 900) -> dict[str, Any]:
        return await self.run_claude(objective=objective, cwd=cwd, timeout_seconds=timeout_seconds)

    async def run_codex(self, *, objective: str, cwd: str | None = None, timeout_seconds: int = 1800) -> dict[str, Any]:
        return await self.run_claude_plan(objective=objective, cwd=cwd, timeout_seconds=timeout_seconds)

    async def run_command(
        self,
        *,
        objective: str,
        command: list[str],
        cwd: str | None = None,
        allow_mutative: bool = False,
        timeout_seconds: int = 600,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return await self._post(
            "/run/command",
            {
                "user_goal": objective,
                "command": command,
                "cwd": cwd,
                "allow_mutative": allow_mutative,
                "timeout_seconds": timeout_seconds,
                "execution_mode": "sync",
                "env": env or {},
            },
            timeout_seconds=self._effective_timeout(timeout_seconds),
        )

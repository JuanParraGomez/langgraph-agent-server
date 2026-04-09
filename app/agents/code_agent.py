"""CodeAgent — delegates code tasks to terminal-tools /run/codex (GitHub Copilot OAuth).

Replaces any previous Claude CLI routing for code tasks.
"""
from __future__ import annotations

from app.adapters.terminal_tools_adapter import TerminalToolsAdapter


class CodeAgent:
    name = "code_agent"

    def __init__(self, terminal_adapter: TerminalToolsAdapter) -> None:
        self.terminal_adapter = terminal_adapter

    async def run(self, goal: str, context: dict | None = None, **_kwargs) -> dict:
        """Execute a code task via GitHub Copilot (openai-codex) through terminal-tools."""
        try:
            result = await self.terminal_adapter.run_codex(
                objective=goal,
                timeout_seconds=300,
            )
            return {"ok": True, "source": "terminal-tools/codex", "data": result}
        except Exception as exc:
            return {"ok": False, "source": "terminal-tools/codex", "error": str(exc)}

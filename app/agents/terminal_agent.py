from __future__ import annotations

from app.adapters.terminal_tools_adapter import TerminalToolsAdapter


class TerminalAgent:
    name = "terminal_agent"

    def __init__(self, terminal_adapter: TerminalToolsAdapter) -> None:
        self.terminal_adapter = terminal_adapter

    async def run(self, task: str) -> dict:
        try:
            result = await self.terminal_adapter.run_subtask(task=task)
            return {"ok": True, "source": "terminal-tools", "data": result}
        except Exception as exc:
            return {"ok": False, "source": "terminal-tools", "error": str(exc)}

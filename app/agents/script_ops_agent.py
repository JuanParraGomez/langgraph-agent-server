from __future__ import annotations

from typing import Any

from app.adapters.celery_server_adapter import CeleryServerAdapter


class ScriptOpsAgent:
    name = "script_ops_agent"

    def __init__(self, celery_adapter: CeleryServerAdapter) -> None:
        self.celery_adapter = celery_adapter

    async def run(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await self.celery_adapter.call_action(action=action, payload=payload)
            return {"ok": True, "source": "celery-server", "data": result}
        except Exception as exc:
            return {"ok": False, "source": "celery-server", "error": str(exc)}

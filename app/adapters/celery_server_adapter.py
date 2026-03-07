from __future__ import annotations

from typing import Any

from app.adapters.base import HttpAdapter


class CeleryServerAdapter(HttpAdapter):
    async def script_requirements(self, goal: str) -> dict[str, Any]:
        return await self._post("/scripts/requirements", {"goal": goal})

    async def validate_script(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/scripts/validate", payload)

    async def run_script(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/scripts/run", payload)

    async def get_logs(self, job_id: str) -> dict[str, Any]:
        return await self._get(f"/jobs/{job_id}/logs")

    async def call_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        routes = {
            "script_requirements": ("/scripts/requirements", {"goal": payload.get("goal", "")}),
            "validate_script": ("/scripts/validate", payload),
            "create_script": ("/scripts/create", payload),
            "update_script": ("/scripts/update", payload),
            "schedule_script": ("/scripts/schedule", payload),
            "run_script": ("/scripts/run", payload),
            "get_job": (f"/jobs/{payload.get('job_id', '')}", None),
            "get_logs": (f"/jobs/{payload.get('job_id', '')}/logs", None),
        }
        if action not in routes:
            return {"ok": False, "error": f"unsupported action: {action}"}

        path, body = routes[action]
        if body is None:
            return await self._get(path)
        return await self._post(path, body)

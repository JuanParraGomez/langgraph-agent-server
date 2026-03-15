from __future__ import annotations

from typing import Any

import httpx


class HttpAdapter:
    def __init__(self, base_url: str, timeout_seconds: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def _get(self, path: str, timeout_seconds: int | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout_seconds or self.timeout_seconds) as client:
            response = await client.get(f"{self.base_url}{path}")
            response.raise_for_status()
            return response.json()

    async def _post(self, path: str, payload: dict[str, Any], timeout_seconds: int | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout_seconds or self.timeout_seconds) as client:
            response = await client.post(f"{self.base_url}{path}", json=payload)
            response.raise_for_status()
            return response.json()

    async def health(self) -> dict[str, Any]:
        try:
            data = await self._get("/health")
            return {"available": True, "base_url": self.base_url, "data": data}
        except Exception as exc:  # pragma: no cover - network variability
            return {"available": False, "base_url": self.base_url, "error": str(exc)}

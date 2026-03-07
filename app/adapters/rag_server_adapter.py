from __future__ import annotations

from typing import Any

from app.adapters.base import HttpAdapter


class RagServerAdapter(HttpAdapter):
    async def research(self, question: str, top_k: int = 5) -> dict[str, Any]:
        return await self._post("/query", {"query": question, "top_k": top_k})

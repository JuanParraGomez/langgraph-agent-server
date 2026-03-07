from __future__ import annotations

from typing import Any

from app.adapters.rag_server_adapter import RagServerAdapter


class ResearchAgent:
    name = "research_agent"

    def __init__(self, rag_adapter: RagServerAdapter) -> None:
        self.rag_adapter = rag_adapter

    async def run(self, question: str, top_k: int = 5) -> dict[str, Any]:
        try:
            result = await self.rag_adapter.research(question=question, top_k=top_k)
            return {"ok": True, "source": "rag-server", "data": result}
        except Exception as exc:
            return {"ok": False, "source": "rag-server", "error": str(exc)}

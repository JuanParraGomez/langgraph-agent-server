from __future__ import annotations

from typing import Any

from app.adapters.rag_server_adapter import RagServerAdapter


class MemoryReviewAgent:
    name = "memory_review_agent"

    def __init__(self, rag_adapter: RagServerAdapter, default_tenant_id: str) -> None:
        self.rag_adapter = rag_adapter
        self.default_tenant_id = default_tenant_id

    async def run(
        self,
        goal: str,
        tenant_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        effective_context = context or {}
        question = (
            "Find previous agent implementations, prompt workflows, execution notes, "
            f"or similar coding tasks related to: {goal}"
        )
        try:
            result = await self.rag_adapter.research(
                question=question,
                tenant_id=tenant_id or self.default_tenant_id,
                filters=effective_context.get("filters", {}),
                top_k=min(int(effective_context.get("top_k", 3)), 5),
            )
            return {"ok": True, "source": "rag-server", "data": result}
        except Exception as exc:
            return {"ok": False, "source": "rag-server", "error": str(exc)}

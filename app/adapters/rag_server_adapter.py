from __future__ import annotations

from typing import Any

from app.adapters.base import HttpAdapter


class RagServerAdapter(HttpAdapter):
    async def research(
        self,
        question: str,
        tenant_id: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        return await self._post(
            "/query",
            {
                "question": question,
                "tenant_id": tenant_id,
                "filters": filters or {},
                "top_k": top_k,
            },
        )

    async def upload_learning(
        self,
        *,
        text: str,
        tenant_id: str,
        title: str,
        metadata: dict[str, Any],
        document_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "text": text,
            "title": title,
            "metadata": {"tenant_id": tenant_id, **metadata},
            "document_id": document_id,
        }
        return await self._post("/upload-text", payload)

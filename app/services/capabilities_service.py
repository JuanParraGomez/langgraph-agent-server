from __future__ import annotations

from typing import Any

from app.adapters.celery_server_adapter import CeleryServerAdapter
from app.adapters.rag_server_adapter import RagServerAdapter
from app.adapters.terminal_tools_adapter import TerminalToolsAdapter
from app.services.provider_service import ProviderService


class CapabilitiesService:
    def __init__(
        self,
        provider_service: ProviderService,
        terminal_adapter: TerminalToolsAdapter,
        rag_adapter: RagServerAdapter,
        celery_adapter: CeleryServerAdapter,
    ) -> None:
        self.provider_service = provider_service
        self.terminal_adapter = terminal_adapter
        self.rag_adapter = rag_adapter
        self.celery_adapter = celery_adapter

    async def backend_health(self) -> dict[str, Any]:
        terminal = await self.terminal_adapter.health()
        rag = await self.rag_adapter.health()
        celery = await self.celery_adapter.health()
        return {
            "terminal_tools": terminal,
            "rag_server": rag,
            "celery_server": celery,
        }

    async def full_capabilities(self) -> dict[str, Any]:
        return {
            "providers": self.provider_service.capabilities(),
            "defaults": self.provider_service.selected_defaults(),
            "backends": await self.backend_health(),
            "agents": [
                {"name": "supervisor_agent", "role": "plan/delegate/control iterations"},
                {"name": "research_agent", "role": "document retrieval/context"},
                {"name": "terminal_agent", "role": "operational terminal subtasks"},
                {"name": "script_ops_agent", "role": "script operations via celery-server"},
                {"name": "synthesis_agent", "role": "final synthesis"},
            ],
            "graphs": [
                {
                    "name": "supervisor_v1",
                    "engine": "langgraph",
                    "description": "Supervisor -> specialized subagents -> synthesis",
                }
            ],
        }

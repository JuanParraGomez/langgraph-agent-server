from __future__ import annotations

from typing import Any

from app.adapters.celery_server_adapter import CeleryServerAdapter
from app.adapters.hapi_client import HapiClient
from app.adapters.rag_server_adapter import RagServerAdapter
from app.adapters.terminal_tools_adapter import TerminalToolsAdapter
from app.adapters.voice_pair_adapter import VoicePairAdapter
from app.services.provider_service import ProviderService


class CapabilitiesService:
    def __init__(
        self,
        provider_service: ProviderService,
        terminal_adapter: TerminalToolsAdapter,
        rag_adapter: RagServerAdapter,
        celery_adapter: CeleryServerAdapter,
        hapi_client: HapiClient,
        voice_pair_adapter: VoicePairAdapter,
    ) -> None:
        self.provider_service = provider_service
        self.terminal_adapter = terminal_adapter
        self.rag_adapter = rag_adapter
        self.celery_adapter = celery_adapter
        self.hapi_client = hapi_client
        self.voice_pair_adapter = voice_pair_adapter

    async def backend_health(self) -> dict[str, Any]:
        terminal = await self.terminal_adapter.health()
        rag = await self.rag_adapter.health()
        celery = await self.celery_adapter.health()
        hapi = await self.hapi_client.health()
        voice_pair = await self.voice_pair_adapter.health()
        return {
            "terminal_tools": terminal,
            "rag_server": rag,
            "celery_server": celery,
            "hapi": hapi,
            "voice_pair": voice_pair,
        }

    async def full_capabilities(self) -> dict[str, Any]:
        return {
            "providers": self.provider_service.capabilities(),
            "defaults": self.provider_service.selected_defaults(),
            "backends": await self.backend_health(),
            "agents": [
                {"name": "supervisor_agent", "role": "plan/delegate/control iterations"},
                {"name": "research_agent", "role": "document retrieval/context"},
                {"name": "memory_review_agent", "role": "check similar work and version hints in rag-server"},
                {"name": "prompt_engineer_agent", "role": "build strong code prompts and routing flow"},
                {"name": "ui_complexity_agent", "role": "classify UI work by complexity and route to Copilot or Codex"},
                {"name": "workspace_planner_agent", "role": "declare file and folder ownership before parallel UI work starts"},
                {"name": "ui_integrator_agent", "role": "use Codex to unify parallel UI changes before validation"},
                {"name": "failure_recovery_agent", "role": "classify strong runtime failures and suggest remediation"},
                {"name": "terminal_agent", "role": "operational terminal subtasks"},
                {"name": "script_ops_agent", "role": "script operations via celery-server"},
                {"name": "synthesis_agent", "role": "final synthesis"},
                {"name": "voice_pair_agent", "role": "synthesize text to audio via voice-pair service (port 8085)"},
            ],
            "graphs": [
                {
                    "name": "supervisor_v1",
                    "engine": "langgraph",
                    "description": "Supervisor -> specialized subagents -> synthesis",
                },
                {
                    "name": "prompt_workflow_v1",
                    "engine": "service-workflow",
                    "description": "Memory review -> prompt engineering -> optional publication to rag-server",
                },
                {
                    "name": "ui_factory_v1",
                    "engine": "service-workflow",
                    "description": "Discover/create/update UI -> build with terminal-tools -> register public state in hapi -> ingest memory in rag",
                },
            ],
        }

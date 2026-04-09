from __future__ import annotations

from functools import lru_cache

from app.adapters.celery_server_adapter import CeleryServerAdapter
from app.adapters.hapi_client import HapiClient
from app.adapters.rag_server_adapter import RagServerAdapter
from app.adapters.terminal_tools_adapter import TerminalToolsAdapter
from app.adapters.voice_pair_adapter import VoicePairAdapter
from app.agents.research_agent import ResearchAgent
from app.agents.script_ops_agent import ScriptOpsAgent
from app.agents.supervisor_agent import SupervisorAgent
from app.agents.synthesis_agent import SynthesisAgent
from app.agents.terminal_agent import TerminalAgent
from app.agents.prompt_engineer_agent import PromptEngineerAgent
from app.agents.memory_review_agent import MemoryReviewAgent
from app.agents.failure_recovery_agent import FailureRecoveryAgent
from app.agents.coordinator_agent import CoordinatorAgent
from app.core.settings import get_settings
from app.services.capabilities_service import CapabilitiesService
from app.services.deepseek_service import DeepSeekService
from app.services.blackboard_service import Blackboard
from app.services.provider_service import ProviderService
from app.services.run_service import RunService
from app.storage.run_store import RunStore


@lru_cache(maxsize=1)
def get_store() -> RunStore:
    settings = get_settings()
    return RunStore(db_path=settings.runs_db_path, logs_dir=settings.logs_dir)


@lru_cache(maxsize=1)
def get_provider_service() -> ProviderService:
    return ProviderService(get_settings())


@lru_cache(maxsize=1)
def get_deepseek_service() -> DeepSeekService:
    return DeepSeekService(get_settings())


@lru_cache(maxsize=1)
def get_terminal_adapter() -> TerminalToolsAdapter:
    s = get_settings()
    return TerminalToolsAdapter(base_url=s.terminal_tools_base_url, timeout_seconds=s.backend_timeout_seconds)


@lru_cache(maxsize=1)
def get_rag_adapter() -> RagServerAdapter:
    s = get_settings()
    return RagServerAdapter(base_url=s.rag_server_base_url, timeout_seconds=s.backend_timeout_seconds)


@lru_cache(maxsize=1)
def get_celery_adapter() -> CeleryServerAdapter:
    s = get_settings()
    return CeleryServerAdapter(base_url=s.celery_server_base_url, timeout_seconds=s.backend_timeout_seconds)


@lru_cache(maxsize=1)
def get_hapi_client() -> HapiClient:
    s = get_settings()
    return HapiClient(base_url=s.hapi_base_url, timeout_seconds=s.backend_timeout_seconds)


@lru_cache(maxsize=1)
def get_voice_pair_adapter() -> VoicePairAdapter:
    s = get_settings()
    return VoicePairAdapter(base_url=s.voice_pair_base_url, timeout_seconds=s.backend_timeout_seconds)


@lru_cache(maxsize=1)
def get_supervisor_agent() -> SupervisorAgent:
    return SupervisorAgent(deepseek_service=get_deepseek_service())


@lru_cache(maxsize=1)
def get_research_agent() -> ResearchAgent:
    settings = get_settings()
    return ResearchAgent(get_rag_adapter(), default_tenant_id=settings.rag_default_tenant_id)


@lru_cache(maxsize=1)
def get_memory_review_agent() -> MemoryReviewAgent:
    settings = get_settings()
    return MemoryReviewAgent(get_rag_adapter(), default_tenant_id=settings.rag_default_tenant_id)


@lru_cache(maxsize=1)
def get_terminal_agent() -> TerminalAgent:
    return TerminalAgent(get_terminal_adapter())


@lru_cache(maxsize=1)
def get_script_ops_agent() -> ScriptOpsAgent:
    return ScriptOpsAgent(get_celery_adapter())


@lru_cache(maxsize=1)
def get_synthesis_agent() -> SynthesisAgent:
    return SynthesisAgent()


@lru_cache(maxsize=1)
def get_prompt_engineer_agent() -> PromptEngineerAgent:
    return PromptEngineerAgent(get_deepseek_service())


@lru_cache(maxsize=1)
def get_failure_recovery_agent() -> FailureRecoveryAgent:
    return FailureRecoveryAgent()


@lru_cache(maxsize=1)
def get_blackboard() -> Blackboard:
    return Blackboard(get_settings())


@lru_cache(maxsize=1)
def get_coordinator_agent() -> CoordinatorAgent:
    return CoordinatorAgent(
        deepseek_service=get_deepseek_service(),
        blackboard=get_blackboard(),
    )


@lru_cache(maxsize=1)
def get_run_service() -> RunService:
    return RunService(
        store=get_store(),
        provider_service=get_provider_service(),
        supervisor=get_supervisor_agent(),
        research=get_research_agent(),
        memory_review=get_memory_review_agent(),
        terminal=get_terminal_agent(),
        script_ops=get_script_ops_agent(),
        synthesis=get_synthesis_agent(),
        prompt_engineer=get_prompt_engineer_agent(),
        failure_recovery=get_failure_recovery_agent(),
        rag_adapter=get_rag_adapter(),
        hapi_client=get_hapi_client(),
        settings=get_settings(),
    )


@lru_cache(maxsize=1)
def get_capabilities_service() -> CapabilitiesService:
    return CapabilitiesService(
        provider_service=get_provider_service(),
        terminal_adapter=get_terminal_adapter(),
        rag_adapter=get_rag_adapter(),
        celery_adapter=get_celery_adapter(),
        hapi_client=get_hapi_client(),
        voice_pair_adapter=get_voice_pair_adapter(),
    )

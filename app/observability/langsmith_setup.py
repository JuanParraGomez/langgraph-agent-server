from __future__ import annotations

import inspect
import os
from typing import Any, Awaitable, Callable, ParamSpec, TypeVar

from langsmith import Client
from langsmith.run_helpers import traceable, tracing_context

from app.core.settings import Settings

try:
    from openai import AsyncOpenAI, OpenAI
except Exception:  # pragma: no cover - optional dependency at runtime
    AsyncOpenAI = None
    OpenAI = None


class LangSmithConfigurationError(RuntimeError):
    """Raised when LangSmith is required but cannot be configured."""


P = ParamSpec("P")
T = TypeVar("T")


def _is_pytest_runtime() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST"))


def _is_langsmith_tracing_enabled() -> bool:
    return str(os.getenv("LANGSMITH_TRACING", "false")).strip().lower() == "true"


def configure_langsmith(settings: Settings) -> dict[str, Any]:
    project_name = settings.langsmith_project or settings.server_name
    tracing_enabled = bool(settings.langsmith_enabled and settings.langsmith_tracing)
    enforce = bool(settings.langsmith_enforce and not _is_pytest_runtime())

    if enforce and not tracing_enabled:
        raise LangSmithConfigurationError("LangSmith tracing is required but LANGSMITH_TRACING/LANGSMITH_ENABLED disabled")
    if enforce and not settings.langsmith_api_key:
        raise LangSmithConfigurationError("LangSmith tracing is required but LANGSMITH_API_KEY is missing")
    if enforce and not settings.langsmith_workspace_id:
        raise LangSmithConfigurationError("LangSmith tracing is required but LANGSMITH_WORKSPACE_ID is missing")

    if not tracing_enabled:
        return {
            "enabled": False,
            "enforced": enforce,
            "project": project_name,
            "endpoint": settings.langsmith_endpoint,
            "workspace_id": settings.langsmith_workspace_id,
            "reason": "disabled",
        }

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_ENABLED"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = project_name
    os.environ["LANGSMITH_PROJECT"] = project_name
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith_endpoint
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    if settings.langsmith_workspace_id:
        os.environ["LANGSMITH_WORKSPACE_ID"] = settings.langsmith_workspace_id
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key

    return {
        "enabled": True,
        "enforced": enforce,
        "project": project_name,
        "endpoint": settings.langsmith_endpoint,
        "workspace_id": settings.langsmith_workspace_id,
    }


async def invoke_graph_traced(
    operation_name: str,
    runnable: Callable[P, Awaitable[T]] | Callable[P, T],
    *args: P.args,
    trace_tags: list[str] | None = None,
    trace_metadata: dict[str, Any] | None = None,
    trace_run_type: str = "chain",
    **kwargs: P.kwargs,
) -> T:
    wrapped = traceable(name=operation_name, run_type=trace_run_type)(runnable)
    with tracing_context(
        project_name=os.getenv("LANGSMITH_PROJECT"),
        tags=trace_tags or [],
        metadata=trace_metadata or {},
        enabled=_is_langsmith_tracing_enabled(),
    ):
        result = wrapped(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


def get_wrapped_openai_client(
    *,
    async_client: bool = True,
    api_key: str | None = None,
    base_url: str | None = None,
    **kwargs: Any,
) -> Any:
    if async_client:
        if AsyncOpenAI is None:
            raise RuntimeError("openai package is required for async OpenAI client instrumentation")
        from langsmith.wrappers import wrap_openai

        client = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"), base_url=base_url, **kwargs)
        return wrap_openai(client)

    if OpenAI is None:
        raise RuntimeError("openai package is required for sync OpenAI client instrumentation")
    from langsmith.wrappers import wrap_openai

    client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"), base_url=base_url, **kwargs)
    return wrap_openai(client)


def get_langsmith_client() -> Client:
    return Client(
        api_url=os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
        api_key=os.getenv("LANGSMITH_API_KEY"),
        workspace_id=os.getenv("LANGSMITH_WORKSPACE_ID"),
    )

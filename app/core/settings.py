from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    global_env_path: Path = Field(default=Path("/home/juan/Documents/.env"), alias="GLOBAL_ENV_PATH")

    server_name: str = Field(default="langgraph-agent-server", alias="AGENT_SERVER_NAME")
    host: str = Field(default="127.0.0.1", alias="AGENT_SERVER_HOST")
    port: int = Field(default=8070, alias="AGENT_SERVER_PORT")
    data_dir: Path = Field(default=Path("./data"), alias="AGENT_DATA_DIR")

    default_reasoning_provider: str = Field(default="deepseek", alias="DEFAULT_REASONING_PROVIDER")
    default_planner_provider: str = Field(default="gemini", alias="DEFAULT_PLANNER_PROVIDER")
    default_special_provider: str = Field(default="openai", alias="DEFAULT_SPECIAL_PROVIDER")

    deepseek_api_key: str | None = Field(default=None, alias="DEEPSEEK_API_KEY")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    deepseek_timeout_seconds: int = Field(default=60, alias="DEEPSEEK_TIMEOUT_SECONDS")
    deepseek_text_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_TEXT_MODEL")
    gemini_supervisor_model: str = Field(default="gemini-2.5-pro", alias="GEMINI_SUPERVISOR_MODEL")
    openai_special_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_SPECIAL_MODEL")

    terminal_tools_base_url: str = Field(default="http://127.0.0.1:8090", alias="TERMINAL_TOOLS_BASE_URL")
    terminal_tools_mcp_url: str = Field(default="http://127.0.0.1:8091/mcp/", alias="TERMINAL_TOOLS_MCP_URL")
    rag_server_base_url: str = Field(default="http://127.0.0.1:8000", alias="RAG_SERVER_BASE_URL")
    rag_server_mcp_url: str = Field(default="http://127.0.0.1:8081", alias="RAG_SERVER_MCP_URL")
    rag_default_tenant_id: str = Field(default="tenant-stack-probe", alias="RAG_DEFAULT_TENANT_ID")
    celery_server_base_url: str = Field(default="http://127.0.0.1:8011", alias="CELERY_SERVER_BASE_URL")
    celery_server_mcp_url: str = Field(default="http://127.0.0.1:8082/mcp", alias="CELERY_SERVER_MCP_URL")
    hapi_base_url: str = Field(default="http://127.0.0.1:8095", alias="HAPI_BASE_URL")
    hapi_mcp_url: str = Field(default="http://127.0.0.1:8096/mcp/", alias="HAPI_MCP_URL")
    ui_factory_repo_root: Path = Field(default=Path("/home/juan/Documents/coolify-server"), alias="UI_FACTORY_REPO_ROOT")
    ui_factory_repo_url: str = Field(default="git@github.com:JuanParraGomez/coolify-server.git", alias="UI_FACTORY_REPO_URL")
    ui_factory_default_branch: str = Field(default="main", alias="UI_FACTORY_DEFAULT_BRANCH")
    ui_factory_git_user_name: str = Field(default="UI Factory Bot", alias="UI_FACTORY_GIT_USER_NAME")
    ui_factory_git_user_email: str = Field(default="bot@uniflexa.cloud", alias="UI_FACTORY_GIT_USER_EMAIL")
    ui_factory_git_ssh_key_path: str = Field(default="/opt/git-keys/id_ed25519_openclaw", alias="UI_FACTORY_GIT_SSH_KEY_PATH")
    ui_factory_copilot_plan_timeout_seconds: int = Field(default=1800, alias="UI_FACTORY_COPILOT_PLAN_TIMEOUT_SECONDS")
    ui_factory_execution_timeout_seconds: int = Field(default=5400, alias="UI_FACTORY_EXECUTION_TIMEOUT_SECONDS")
    ui_factory_small_change_timeout_seconds: int = Field(default=2700, alias="UI_FACTORY_SMALL_CHANGE_TIMEOUT_SECONDS")
    ui_factory_validation_timeout_seconds: int = Field(default=1200, alias="UI_FACTORY_VALIDATION_TIMEOUT_SECONDS")
    ui_factory_git_timeout_seconds: int = Field(default=1800, alias="UI_FACTORY_GIT_TIMEOUT_SECONDS")
    ui_factory_deploy_max_attempts: int = Field(default=3, alias="UI_FACTORY_DEPLOY_MAX_ATTEMPTS")
    ui_factory_deploy_retry_delay_seconds: int = Field(default=8, alias="UI_FACTORY_DEPLOY_RETRY_DELAY_SECONDS")

    backend_timeout_seconds: int = Field(default=20, alias="BACKEND_TIMEOUT_SECONDS")

    langsmith_enabled: bool = Field(default=True, alias="LANGSMITH_ENABLED")
    langsmith_api_key: str | None = Field(default=None, alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="langgraph-agent-server", alias="LANGSMITH_PROJECT")
    langsmith_endpoint: str = Field(default="https://api.smith.langchain.com", alias="LANGSMITH_ENDPOINT")

    @property
    def runs_db_path(self) -> Path:
        return self.data_dir / "runs" / "runs.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"


def _load_global_env() -> None:
    env_path = os.getenv("GLOBAL_ENV_PATH", "/home/juan/Documents/.env")
    load_dotenv(env_path, override=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_global_env()
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.runs_db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.ui_factory_repo_root.mkdir(parents=True, exist_ok=True)
    return settings

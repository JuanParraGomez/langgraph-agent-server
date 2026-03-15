from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class ComplexTaskRequest(BaseModel):
    goal: str = Field(min_length=3)
    context: dict[str, Any] = Field(default_factory=dict)
    max_iterations: int = Field(default=3, ge=1, le=10)


class PlanTaskRequest(BaseModel):
    goal: str = Field(min_length=3)
    context: dict[str, Any] = Field(default_factory=dict)


class PromptWorkflowRequest(BaseModel):
    goal: str = Field(min_length=3)
    context: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str | None = Field(default=None, min_length=1)
    agent_name: str | None = None
    current_version: str | None = None
    publish_learning: bool = True


class UIFactoryRequest(BaseModel):
    goal: str = Field(min_length=3)
    context: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str | None = Field(default=None, min_length=1)
    app_name: str | None = None
    slug: str | None = None
    project_type: str = "long_lived"
    deploy: bool = True
    publish_memory: bool = True
    max_iterations: int = Field(default=3, ge=1, le=10)
    resume_run_id: str | None = None


class CancelRunRequest(BaseModel):
    reason: str | None = None


class UIFactoryPlan(BaseModel):
    action: str
    slug: str
    name: str
    framework: str
    app_type: str
    template: str
    project_type: str
    rationale: str
    project_root: str | None = None


class UIFactoryResult(BaseModel):
    status: str
    app_id: str | None = None
    action_taken: str
    repo_url: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
    public_url: str | None = None
    deployment_status: str
    rag_ingested: bool
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class ResearchSubtaskRequest(BaseModel):
    question: str = Field(min_length=3)
    top_k: int = Field(default=5, ge=1, le=20)


class TerminalSubtaskRequest(BaseModel):
    task: str = Field(min_length=2)


class ScriptOpsSubtaskRequest(BaseModel):
    action: str = Field(min_length=2)
    payload: dict[str, Any] = Field(default_factory=dict)


class SummarizeFindingsRequest(BaseModel):
    run_id: str = Field(min_length=6)


class VoiceSynthesisRequest(BaseModel):
    text: str = Field(min_length=1, description="Text to synthesize into audio")
    voice_id: str = Field(default="default", description="Voice identifier")
    format: str = Field(default="wav", description="Audio format: wav or mp3")


class RunRecord(BaseModel):
    run_id: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: RunStatus
    requested_goal: str
    selected_graph: str
    selected_agents: list[str] = Field(default_factory=list)
    providers_used: list[str] = Field(default_factory=list)
    external_tools_used: list[str] = Field(default_factory=list)
    summary: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    logs_path: str | None = None


class RunResponse(BaseModel):
    run: RunRecord


class RunLogsResponse(BaseModel):
    run_id: str
    logs: list[dict[str, Any]]


class HealthResponse(BaseModel):
    status: str
    service: str
    providers: dict[str, Any]
    backends: dict[str, Any]


class CapabilitiesResponse(BaseModel):
    agents: list[dict[str, Any]]
    graphs: list[dict[str, Any]]
    providers: dict[str, Any]
    backends: dict[str, Any]


class AgentToolResponse(BaseModel):
    ok: bool = True
    tool: str
    data: dict[str, Any]

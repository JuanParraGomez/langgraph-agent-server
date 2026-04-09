"""Dynamic agent capability registry.

Agents register their capabilities at startup or runtime. The coordinator
queries the registry to find the best agent for each sub-task.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentCapability:
    agent_name: str
    capabilities: list[str]
    description: str
    registered_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentRegistry:
    """In-memory registry of agent capabilities. Queryable by the coordinator."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentCapability] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in agents."""
        defaults = [
            AgentCapability(
                agent_name="research_agent",
                capabilities=["rag", "search", "documents", "context", "knowledge"],
                description="RAG retrieval, document search, context gathering",
            ),
            AgentCapability(
                agent_name="terminal_agent",
                capabilities=["shell", "terminal", "files", "inspect", "logs", "code", "git"],
                description="Shell commands, file inspection, repo operations",
            ),
            AgentCapability(
                agent_name="script_ops_agent",
                capabilities=["scripts", "deploy", "backup", "schedule", "cron", "jobs"],
                description="Script execution, scheduled jobs, deploy ops",
            ),
            AgentCapability(
                agent_name="memory_review_agent",
                capabilities=["memory", "history", "recall", "consolidate"],
                description="Review and consolidate session memory",
            ),
            AgentCapability(
                agent_name="prompt_engineer_agent",
                capabilities=["prompts", "workflow", "design", "plan"],
                description="Generate prompt packages and code workflow plans",
            ),
            AgentCapability(
                agent_name="synthesis_agent",
                capabilities=["synthesize", "aggregate", "summarize", "report"],
                description="Aggregate outputs into coherent response",
            ),
            AgentCapability(
                agent_name="coordinator_agent",
                capabilities=["coordinate", "decompose", "orchestrate", "delegate"],
                description="Task decomposition and multi-agent coordination",
            ),
        ]
        for cap in defaults:
            self._agents[cap.agent_name] = cap

    def register(self, capability: AgentCapability) -> None:
        """Register or update an agent's capabilities."""
        self._agents[capability.agent_name] = capability
        logger.info("Agent registered: %s with capabilities: %s",
                     capability.agent_name, capability.capabilities)

    def unregister(self, agent_name: str) -> bool:
        """Remove an agent from the registry."""
        return self._agents.pop(agent_name, None) is not None

    def get(self, agent_name: str) -> AgentCapability | None:
        """Get a specific agent's capabilities."""
        return self._agents.get(agent_name)

    def list_all(self) -> list[AgentCapability]:
        """List all registered agents."""
        return list(self._agents.values())

    def find_by_capability(self, capability: str) -> list[AgentCapability]:
        """Find agents that have a specific capability."""
        capability_lower = capability.lower()
        return [
            agent for agent in self._agents.values()
            if any(capability_lower in cap.lower() for cap in agent.capabilities)
        ]

    def find_best_for_task(self, task_description: str) -> list[tuple[str, int]]:
        """Score agents by relevance to a task description. Returns sorted (agent_name, score) pairs."""
        task_lower = task_description.lower()
        scores: list[tuple[str, int]] = []
        for agent in self._agents.values():
            score = sum(1 for cap in agent.capabilities if cap in task_lower)
            if score > 0:
                scores.append((agent.agent_name, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    def to_dict(self) -> list[dict[str, Any]]:
        """Serialize for API responses."""
        return [
            {
                "agent_name": a.agent_name,
                "capabilities": a.capabilities,
                "description": a.description,
                "registered_at": a.registered_at,
                "metadata": a.metadata,
            }
            for a in self._agents.values()
        ]


# Singleton
_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry

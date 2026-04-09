"""Coordinator agent: decomposes commands → spawns sub-agents → evaluates → re-delegates.

Top-level orchestrator with feedback loop. Uses DeepSeek for decomposition and evaluation.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.services.blackboard_service import Blackboard
from app.services.deepseek_service import DeepSeekService

logger = logging.getLogger(__name__)


class EvalAction(str, Enum):
    ACCEPT = "accept"
    RETRY = "retry"
    ESCALATE = "escalate"


@dataclass
class SubTask:
    id: str
    description: str
    agent: str
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"
    result: Any = None
    attempts: int = 0
    max_attempts: int = 3


DECOMPOSE_SYSTEM = """\
You are a task decomposition engine for a multi-agent system. Break down the user's command \
into independent sub-tasks that can be delegated to specialized agents.

Available agents: research_agent, terminal_agent, script_ops_agent, memory_review_agent, prompt_engineer_agent, code_agent

Rules:
- Each sub-task has: id (short), description, agent, depends_on (list of sub-task ids)
- Minimize sub-tasks. Only split when genuinely parallel or when different agents are needed.
- Use depends_on for ordering. Empty means can run immediately.
- For CODE tasks (programming, debugging, implementing, refactoring, tests): use code_agent (GitHub Copilot/openai-codex).
- For system ops, shell, file inspection: use terminal_agent.

Return JSON: {"subtasks": [{"id": "t1", "description": "...", "agent": "...", "depends_on": []}]}
"""

EVALUATE_SYSTEM = """\
You are a quality evaluator for a multi-agent system. Given a sub-task and its result, \
decide the next action.

Return JSON: {"action": "accept"|"retry"|"escalate", "reason": "brief reason"}
- accept: result is good enough
- retry: result is wrong/incomplete, try again (will be retried up to 3x)
- escalate: task needs human intervention or a more capable model
"""


class CoordinatorAgent:
    name = "coordinator_agent"

    def __init__(
        self,
        deepseek_service: DeepSeekService | None = None,
        blackboard: Blackboard | None = None,
    ) -> None:
        self.deepseek = deepseek_service
        self.blackboard = blackboard

    async def decompose(self, command: str, context: dict[str, Any] | None = None) -> list[SubTask]:
        """Break command into sub-tasks using LLM or heuristic fallback."""
        if self.deepseek and self.deepseek.available():
            try:
                return await self._llm_decompose(command, context or {})
            except Exception as exc:
                logger.warning("LLM decomposition failed: %s", exc)

        return self._heuristic_decompose(command)

    async def evaluate(self, subtask: SubTask, result: Any) -> EvalAction:
        """Evaluate whether a sub-task result is acceptable."""
        if self.deepseek and self.deepseek.available():
            try:
                return await self._llm_evaluate(subtask, result)
            except Exception as exc:
                logger.warning("LLM evaluation failed: %s", exc)

        # Heuristic: accept if result has ok=True, retry otherwise
        if isinstance(result, dict):
            return EvalAction.ACCEPT if result.get("ok") else EvalAction.RETRY
        return EvalAction.ACCEPT if result else EvalAction.RETRY

    async def run(
        self,
        command: str,
        agent_runners: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Full coordination loop: decompose → execute → evaluate → synthesize."""
        subtasks = await self.decompose(command, context)
        results: dict[str, Any] = {}

        # Write plan to blackboard
        if self.blackboard:
            await self.blackboard.write(
                "current_plan",
                {"command": command, "subtasks": [{"id": st.id, "agent": st.agent, "desc": st.description} for st in subtasks]},
                agent_id=self.name,
            )

        # Execute in dependency order
        for subtask in self._resolve_order(subtasks):
            runner = agent_runners.get(subtask.agent)
            if not runner:
                subtask.status = "skipped"
                subtask.result = {"ok": False, "error": f"Agent '{subtask.agent}' not available"}
                results[subtask.id] = subtask.result
                continue

            while subtask.attempts < subtask.max_attempts:
                subtask.attempts += 1
                try:
                    result = await self._run_agent(runner, subtask, command, results)
                    action = await self.evaluate(subtask, result)

                    if action == EvalAction.ACCEPT:
                        subtask.status = "done"
                        subtask.result = result
                        results[subtask.id] = result
                        break
                    elif action == EvalAction.ESCALATE:
                        subtask.status = "escalated"
                        subtask.result = {"escalated": True, "last_result": result}
                        results[subtask.id] = subtask.result
                        break
                    # RETRY: loop continues
                except Exception as exc:
                    logger.error("Agent %s failed on subtask %s (attempt %d): %s",
                                 subtask.agent, subtask.id, subtask.attempts, exc)
                    if subtask.attempts >= subtask.max_attempts:
                        subtask.status = "failed"
                        subtask.result = {"ok": False, "error": str(exc)}
                        results[subtask.id] = subtask.result

        # Write results to blackboard
        if self.blackboard:
            await self.blackboard.write("last_results", results, agent_id=self.name)

        return {
            "ok": all(st.status in ("done", "skipped") for st in subtasks),
            "command": command,
            "subtasks": [
                {"id": st.id, "agent": st.agent, "status": st.status, "attempts": st.attempts}
                for st in subtasks
            ],
            "results": results,
        }

    async def _run_agent(
        self,
        runner: Any,
        subtask: SubTask,
        original_command: str,
        prior_results: dict[str, Any],
    ) -> Any:
        """Run an agent with context from prior results."""
        enriched_task = subtask.description
        if subtask.depends_on:
            deps_context = {dep: prior_results.get(dep, "no result") for dep in subtask.depends_on}
            enriched_task += f"\n\nContext from prior steps: {json.dumps(deps_context, default=str)[:500]}"

        if hasattr(runner, "run"):
            # ResearchAgent expects 'question', TerminalAgent expects 'task', etc
            if subtask.agent == "research_agent":
                return await runner.run(question=enriched_task, top_k=5)
            elif subtask.agent == "terminal_agent":
                return await runner.run(task=enriched_task)
            elif subtask.agent == "script_ops_agent":
                return await runner.run(action="execute", payload={"goal": enriched_task})
            else:
                return await runner.run(goal=enriched_task, context=prior_results)
        return {"ok": False, "error": "Runner has no run() method"}

    async def _llm_decompose(self, command: str, context: dict[str, Any]) -> list[SubTask]:
        raw = await self.deepseek.chat_completion(
            system_prompt=DECOMPOSE_SYSTEM,
            user_prompt=json.dumps({"command": command, "context_keys": list(context.keys())}),
            temperature=0.1,
        )
        parsed = self._parse_json(raw)
        subtasks = []
        for item in parsed.get("subtasks", []):
            subtasks.append(SubTask(
                id=item["id"],
                description=item["description"],
                agent=item["agent"],
                depends_on=item.get("depends_on", []),
            ))
        return subtasks or self._heuristic_decompose(command)

    async def _llm_evaluate(self, subtask: SubTask, result: Any) -> EvalAction:
        raw = await self.deepseek.chat_completion(
            system_prompt=EVALUATE_SYSTEM,
            user_prompt=json.dumps({
                "subtask": {"id": subtask.id, "description": subtask.description, "agent": subtask.agent},
                "result_summary": str(result)[:500],
                "attempt": subtask.attempts,
            }),
            temperature=0.0,
        )
        parsed = self._parse_json(raw)
        action_str = parsed.get("action", "accept").lower()
        try:
            return EvalAction(action_str)
        except ValueError:
            return EvalAction.ACCEPT

    def _heuristic_decompose(self, command: str) -> list[SubTask]:
        """Simple fallback decomposition."""
        text = command.lower()
        subtasks: list[SubTask] = []

        # CODE tasks → code_agent (Copilot/openai-codex)
        is_code = any(k in text for k in [
            "code", "implement", "debug", "refactor", "función", "function", "class",
            "test", "typescript", "python", "javascript", "build", "compile", "fix", "bug",
        ])
        if is_code:
            subtasks.append(SubTask(id="code", description=f"Code task: {command}", agent="code_agent"))

        if any(k in text for k in ["investiga", "research", "busca", "find", "document"]):
            subtasks.append(SubTask(id="research", description=f"Research: {command}", agent="research_agent"))

        if not is_code and any(k in text for k in ["file", "repo", "terminal", "inspect", "log"]):
            subtasks.append(SubTask(
                id="terminal",
                description=f"Terminal inspection: {command}",
                agent="terminal_agent",
                depends_on=["research"] if subtasks else [],
            ))

        if any(k in text for k in ["script", "deploy", "backup", "schedule"]):
            subtasks.append(SubTask(id="ops", description=f"Script ops: {command}", agent="script_ops_agent"))

        if not subtasks:
            subtasks = [
                SubTask(id="research", description=f"Gather context: {command}", agent="research_agent"),
            ]

        return subtasks

    @staticmethod
    def _resolve_order(subtasks: list[SubTask]) -> list[SubTask]:
        """Topological sort by depends_on."""
        done: set[str] = set()
        ordered: list[SubTask] = []
        remaining = list(subtasks)

        max_iters = len(remaining) * 2
        for _ in range(max_iters):
            if not remaining:
                break
            for st in list(remaining):
                if all(dep in done for dep in st.depends_on):
                    ordered.append(st)
                    done.add(st.id)
                    remaining.remove(st)

        # Append any stuck tasks (circular deps) with warning
        if remaining:
            stuck_ids = [st.id for st in remaining]
            logger.warning(f"Circular dependency detected in subtasks: {stuck_ids}. Appending in arbitrary order.")
        ordered.extend(remaining)
        return ordered

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if "```" in text:
            for part in text.split("```")[1:]:
                candidate = part.strip()
                if candidate.startswith("json"):
                    candidate = candidate[4:].strip()
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

"""Code execution workflow using Claude CLI via terminal-tools.

Receives a code task, routes to Claude CLI (local, free), returns structured result.
Supports two modes: small change (claude) and plan-then-execute (claude-plan).
"""
from __future__ import annotations

import logging
from typing import Any, Literal, TypedDict

from app.adapters.terminal_tools_adapter import TerminalToolsAdapter

try:
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except Exception:
    END = "END"
    LANGGRAPH_AVAILABLE = False
    StateGraph = None

logger = logging.getLogger(__name__)


class CodeGraphState(TypedDict, total=False):
    objective: str
    cwd: str
    complexity: int  # 1-5 scale; <=2 → small change, >=3 → plan-then-execute
    result: dict[str, Any]
    error: str | None
    mode: Literal["small", "plan"]
    iterations: int
    max_iterations: int


class CodeExecutionGraph:
    """LangGraph workflow: code request → Claude CLI → result."""

    def __init__(self, terminal: TerminalToolsAdapter) -> None:
        self.terminal = terminal
        self.graph = self._build_graph() if LANGGRAPH_AVAILABLE else None

    def _build_graph(self):
        graph = StateGraph(CodeGraphState)

        async def classify_node(state: CodeGraphState) -> CodeGraphState:
            complexity = state.get("complexity", 3)
            mode: Literal["small", "plan"] = "small" if complexity <= 2 else "plan"
            return {"mode": mode, "iterations": 0}

        async def claude_small_node(state: CodeGraphState) -> CodeGraphState:
            try:
                result = await self.terminal.run_claude(
                    objective=state["objective"],
                    cwd=state.get("cwd"),
                    timeout_seconds=900,
                )
                return {"result": result, "error": None, "iterations": state.get("iterations", 0) + 1}
            except Exception as exc:
                logger.error("claude_small failed: %s", exc)
                return {"result": {}, "error": str(exc), "iterations": state.get("iterations", 0) + 1}

        async def claude_plan_node(state: CodeGraphState) -> CodeGraphState:
            try:
                result = await self.terminal.run_claude_plan(
                    objective=state["objective"],
                    cwd=state.get("cwd"),
                    timeout_seconds=1800,
                )
                return {"result": result, "error": None, "iterations": state.get("iterations", 0) + 1}
            except Exception as exc:
                logger.error("claude_plan failed: %s", exc)
                return {"result": {}, "error": str(exc), "iterations": state.get("iterations", 0) + 1}

        def route_by_mode(state: CodeGraphState) -> Literal["claude_small", "claude_plan"]:
            return "claude_small" if state.get("mode") == "small" else "claude_plan"

        def should_retry(state: CodeGraphState) -> Literal["classify", "done"]:
            if state.get("error") and state.get("iterations", 0) < state.get("max_iterations", 2):
                return "classify"
            return "done"

        graph.add_node("classify", classify_node)
        graph.add_node("claude_small", claude_small_node)
        graph.add_node("claude_plan", claude_plan_node)
        graph.add_node("done", lambda state: state)

        graph.set_entry_point("classify")
        graph.add_conditional_edges("classify", route_by_mode)
        graph.add_conditional_edges("claude_small", should_retry)
        graph.add_conditional_edges("claude_plan", should_retry)
        graph.add_edge("done", END)

        return graph.compile()

    async def run(
        self,
        objective: str,
        cwd: str | None = None,
        complexity: int = 3,
        max_iterations: int = 2,
    ) -> dict[str, Any]:
        if LANGGRAPH_AVAILABLE and self.graph:
            initial: CodeGraphState = {
                "objective": objective,
                "cwd": cwd or "/home/juan",
                "complexity": complexity,
                "max_iterations": max_iterations,
                "iterations": 0,
            }
            try:
                result = await self.graph.ainvoke(initial)
                return {
                    "ok": not result.get("error"),
                    "mode": result.get("mode", "unknown"),
                    "result": result.get("result", {}),
                    "error": result.get("error"),
                    "iterations": result.get("iterations", 0),
                    "engine": "langgraph",
                }
            except Exception as exc:
                logger.error("CodeExecutionGraph.run langgraph error: %s", exc)

        # Fallback: direct call
        return await self._fallback_run(objective, cwd, complexity)

    async def _fallback_run(
        self,
        objective: str,
        cwd: str | None,
        complexity: int,
    ) -> dict[str, Any]:
        try:
            if complexity <= 2:
                result = await self.terminal.run_claude(objective=objective, cwd=cwd, timeout_seconds=900)
            else:
                result = await self.terminal.run_claude_plan(objective=objective, cwd=cwd, timeout_seconds=1800)
            return {
                "ok": True,
                "mode": "small" if complexity <= 2 else "plan",
                "result": result,
                "error": None,
                "iterations": 1,
                "engine": "fallback",
            }
        except Exception as exc:
            return {
                "ok": False,
                "mode": "small" if complexity <= 2 else "plan",
                "result": {},
                "error": str(exc),
                "iterations": 1,
                "engine": "fallback",
            }

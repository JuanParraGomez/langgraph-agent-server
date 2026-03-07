from __future__ import annotations

from typing import Any, Literal, TypedDict

from app.agents.research_agent import ResearchAgent
from app.agents.script_ops_agent import ScriptOpsAgent
from app.agents.supervisor_agent import SupervisorAgent
from app.agents.synthesis_agent import SynthesisAgent
from app.agents.terminal_agent import TerminalAgent

try:
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except Exception:  # pragma: no cover - optional import safety
    END = "END"
    LANGGRAPH_AVAILABLE = False
    StateGraph = None


class GraphState(TypedDict, total=False):
    goal: str
    context: dict[str, Any]
    plan: dict[str, Any]
    outputs: dict[str, Any]
    active_agents: list[str]
    next_agent_idx: int
    max_iterations: int
    iterations: int
    final: dict[str, Any]


class ComplexTaskGraph:
    def __init__(
        self,
        supervisor: SupervisorAgent,
        research: ResearchAgent,
        terminal: TerminalAgent,
        script_ops: ScriptOpsAgent,
        synthesis: SynthesisAgent,
    ) -> None:
        self.supervisor = supervisor
        self.research = research
        self.terminal = terminal
        self.script_ops = script_ops
        self.synthesis = synthesis
        self.graph = self._build_graph() if LANGGRAPH_AVAILABLE else None

    def _build_graph(self):
        graph = StateGraph(GraphState)

        async def supervisor_node(state: GraphState) -> GraphState:
            plan = await self.supervisor.create_plan(state["goal"], state.get("context", {}))
            active = [a for a in plan.get("selected_agents", []) if a != "synthesis_agent"]
            return {
                "plan": plan,
                "outputs": {},
                "active_agents": active,
                "next_agent_idx": 0,
                "iterations": 0,
            }

        async def route_node(state: GraphState) -> GraphState:
            return state

        async def research_node(state: GraphState) -> GraphState:
            out = dict(state.get("outputs", {}))
            context = state.get("context", {})
            out["research"] = await self.research.run(
                question=state["goal"],
                top_k=5,
                tenant_id=context.get("tenant_id"),
                filters=context.get("filters", {}),
            )
            return {"outputs": out, "next_agent_idx": state.get("next_agent_idx", 0) + 1, "iterations": state.get("iterations", 0) + 1}

        async def terminal_node(state: GraphState) -> GraphState:
            out = dict(state.get("outputs", {}))
            out["terminal"] = await self.terminal.run(task=state["goal"])
            return {"outputs": out, "next_agent_idx": state.get("next_agent_idx", 0) + 1, "iterations": state.get("iterations", 0) + 1}

        async def script_ops_node(state: GraphState) -> GraphState:
            out = dict(state.get("outputs", {}))
            out["script_ops"] = await self.script_ops.run(action="script_requirements", payload={"goal": state["goal"]})
            return {"outputs": out, "next_agent_idx": state.get("next_agent_idx", 0) + 1, "iterations": state.get("iterations", 0) + 1}

        async def synthesis_node(state: GraphState) -> GraphState:
            final = await self.synthesis.run(goal=state["goal"], plan=state.get("plan", {}), outputs=state.get("outputs", {}))
            return {"final": final}

        def next_step(state: GraphState) -> Literal["research", "terminal", "script_ops", "synthesis"]:
            idx = state.get("next_agent_idx", 0)
            agents = state.get("active_agents", [])
            if idx >= len(agents):
                return "synthesis"

            if state.get("iterations", 0) >= state.get("max_iterations", 3):
                return "synthesis"

            agent = agents[idx]
            if agent == "research_agent":
                return "research"
            if agent == "terminal_agent":
                return "terminal"
            if agent == "script_ops_agent":
                return "script_ops"
            return "synthesis"

        graph.add_node("supervisor", supervisor_node)
        graph.add_node("route", route_node)
        graph.add_node("research", research_node)
        graph.add_node("terminal", terminal_node)
        graph.add_node("script_ops", script_ops_node)
        graph.add_node("synthesis", synthesis_node)

        graph.set_entry_point("supervisor")
        graph.add_edge("supervisor", "route")
        graph.add_conditional_edges("route", next_step)
        graph.add_edge("research", "route")
        graph.add_edge("terminal", "route")
        graph.add_edge("script_ops", "route")
        graph.add_edge("synthesis", END)

        return graph.compile()

    async def run(self, goal: str, context: dict[str, Any], max_iterations: int = 3) -> dict[str, Any]:
        if not LANGGRAPH_AVAILABLE or self.graph is None:
            plan = await self.supervisor.create_plan(goal=goal, context=context)
            outputs: dict[str, Any] = {}
            for agent_name in plan.get("selected_agents", []):
                if agent_name == "research_agent":
                    outputs["research"] = await self.research.run(
                        question=goal,
                        top_k=5,
                        tenant_id=context.get("tenant_id"),
                        filters=context.get("filters", {}),
                    )
                elif agent_name == "terminal_agent":
                    outputs["terminal"] = await self.terminal.run(task=goal)
                elif agent_name == "script_ops_agent":
                    outputs["script_ops"] = await self.script_ops.run(action="script_requirements", payload={"goal": goal})
            final = await self.synthesis.run(goal=goal, plan=plan, outputs=outputs)
            return {"plan": plan, "outputs": outputs, "final": final, "engine": "fallback"}

        initial: GraphState = {
            "goal": goal,
            "context": context,
            "max_iterations": max_iterations,
            "iterations": 0,
        }
        result = await self.graph.ainvoke(initial)
        return {
            "plan": result.get("plan", {}),
            "outputs": result.get("outputs", {}),
            "final": result.get("final", {}),
            "engine": "langgraph",
        }

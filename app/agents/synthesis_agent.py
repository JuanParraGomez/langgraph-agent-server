from __future__ import annotations

from typing import Any


class SynthesisAgent:
    name = "synthesis_agent"

    async def run(self, goal: str, plan: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
        bullets: list[str] = []
        for key in ("research", "terminal", "script_ops"):
            data = outputs.get(key)
            if not data:
                continue
            if data.get("ok"):
                bullets.append(f"{key}: completed")
            else:
                bullets.append(f"{key}: failed ({data.get('error', 'unknown error')})")

        final_text = {
            "goal": goal,
            "plan_steps": plan.get("plan", []),
            "execution_summary": bullets,
            "recommendation": "Review outputs and iterate if unresolved blockers remain.",
        }
        return {"ok": True, "final": final_text}

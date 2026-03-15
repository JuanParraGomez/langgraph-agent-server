from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.settings import Settings


class ClaudeApiService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def available(self) -> bool:
        return bool(self.settings.anthropic_api_key)

    async def generate_prompt_package(
        self,
        *,
        goal: str,
        agent_name: str,
        current_version: str,
        context: dict[str, Any],
        similar_summary: dict[str, Any],
        fallback_workflow: str,
    ) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("claude_api_unavailable")

        system_prompt = (
            "You are a senior software staff engineer that designs prompt packages for code agents. "
            "Return strict JSON only. Choose one workflow from: "
            "claude_small_change, claude_plan_then_claude. "
            "Small code fixes should prefer claude_small_change. "
            "Complex or multi-file code tasks should prefer claude_plan_then_claude. "
            "For small/fast tasks, use claude-haiku-4-5. "
            "For planning, architecture, and complex code execution, use claude-sonnet-4-6. "
            "The output JSON must include keys: workflow, rationale, planning_prompt, execution_prompt, "
            "validation_prompt, rag_learning_text, recommended_sequence."
        )

        user_prompt = json.dumps(
            {
                "goal": goal,
                "agent_name": agent_name,
                "current_version": current_version,
                "context": context,
                "similar_summary": similar_summary,
                "fallback_workflow": fallback_workflow,
            },
            ensure_ascii=True,
        )

        model = self.settings.claude_plan_model
        payload = {
            "model": model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = data["content"][0]["text"]
        parsed = self._parse_json_content(content)
        parsed["provider_used"] = "anthropic"
        parsed["model_used"] = model
        return parsed

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        stripped = content.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            candidate = "\n".join(lines).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                stripped = candidate

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(stripped[start : end + 1])

        raise json.JSONDecodeError("No JSON object found in Claude API response", stripped, 0)

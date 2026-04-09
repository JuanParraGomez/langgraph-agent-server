from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.settings import Settings

logger = logging.getLogger(__name__)


class DeepSeekService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def available(self) -> bool:
        return bool(self.settings.deepseek_api_key)

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
            raise RuntimeError("deepseek_unavailable")

        system_prompt = (
            "You are a senior software staff engineer that designs prompt packages for code agents. "
            "Return strict JSON only. Choose one workflow from: "
            "copilot_small_change, copilot_plan_then_execute. "
            "Small code fixes should prefer copilot_small_change. "
            "Complex or multi-file code tasks should prefer copilot_plan_then_execute. "
            "For code execution, all tasks route to GitHub Copilot (openai-codex). "
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

        payload = {
            "model": self.settings.deepseek_text_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=self.settings.deepseek_timeout_seconds) as client:
            response = await client.post(
                f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        parsed = self._parse_json_content(content)
        parsed["provider_used"] = "deepseek"
        parsed["model_used"] = self.settings.deepseek_text_model
        return parsed

    async def chat_completion(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        model: str | None = None,
        return_usage: bool = False,
    ) -> str | dict[str, Any]:
        """Generic chat completion.

        Returns raw assistant content string unless return_usage=True,
        in which case returns {"content": str, "usage": {...}}.
        """
        if not self.available():
            raise RuntimeError("deepseek_unavailable")

        payload = {
            "model": model or self.settings.deepseek_text_model,
            "messages": [
                # System prompt marked for prefix caching (DeepSeek cache_control)
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }

        async with httpx.AsyncClient(timeout=self.settings.deepseek_timeout_seconds) as client:
            response = await client.post(
                f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        if usage:
            cache_read = usage.get("prompt_cache_hit_tokens", 0)
            cache_miss = usage.get("prompt_cache_miss_tokens", 0)
            if cache_read or cache_miss:
                logger.debug(
                    "DeepSeek cache: hit=%d miss=%d prompt=%d completion=%d",
                    cache_read, cache_miss,
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                )

        if return_usage:
            return {"content": content, "usage": usage}
        return content

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

        raise json.JSONDecodeError("No JSON object found in DeepSeek response", stripped, 0)

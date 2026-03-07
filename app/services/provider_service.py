from __future__ import annotations

from app.core.settings import Settings


class ProviderService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def capabilities(self) -> dict[str, dict]:
        return {
            "deepseek": {
                "available": bool(self.settings.deepseek_api_key),
                "model": self.settings.deepseek_text_model,
                "role": "reasoning",
            },
            "gemini": {
                "available": bool(self.settings.gemini_api_key),
                "model": self.settings.gemini_supervisor_model,
                "role": "planning/supervisor",
            },
            "openai": {
                "available": bool(self.settings.openai_api_key),
                "model": self.settings.openai_special_model,
                "role": "special tasks",
            },
        }

    def selected_defaults(self) -> dict[str, str]:
        return {
            "reasoning": self.settings.default_reasoning_provider,
            "planner": self.settings.default_planner_provider,
            "special": self.settings.default_special_provider,
        }

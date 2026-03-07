from __future__ import annotations

from app.core.settings import Settings
from app.services.deepseek_service import DeepSeekService


def test_parse_json_content_from_markdown_block() -> None:
    service = DeepSeekService(Settings())
    parsed = service._parse_json_content(
        "```json\n{\"workflow\":\"copilot_plan_then_codex\",\"planning_prompt\":\"ok\"}\n```"
    )
    assert parsed["workflow"] == "copilot_plan_then_codex"

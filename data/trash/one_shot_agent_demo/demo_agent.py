class OneShotDemoAgent:
    name = "one_shot_demo_agent"

    async def run(self, text: str) -> dict:
        cleaned = " ".join(text.strip().split())
        return {
            "ok": True,
            "agent": self.name,
            "input_length": len(text),
            "normalized_text": cleaned,
            "summary": cleaned[:120],
        }

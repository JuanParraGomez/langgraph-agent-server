class GeneratedNoteAgent:
    def __init__(self):
        self.name = 'generated_note_agent'

    async def run(self, topic: str, context: dict | None = None) -> dict:
        context_keys = sorted(context.keys()) if context else []
        return {'ok': True, 'agent': self.name, 'topic': topic, 'context_keys': context_keys}

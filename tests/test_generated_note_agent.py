import asyncio
from app.agents.generated_note_agent import GeneratedNoteAgent

def test_generated_note_agent_run():
    result = asyncio.run(GeneratedNoteAgent().run('backup', {'tenant_id': 'demo', 'project': 'x'}))
    assert result == {
        "ok": True,
        "agent": "generated_note_agent",
        "topic": "backup",
        "context_keys": ["project", "tenant_id"],
    }

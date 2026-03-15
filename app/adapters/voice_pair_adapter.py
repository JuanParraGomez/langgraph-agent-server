from __future__ import annotations

from typing import Any

from app.adapters.base import HttpAdapter


class VoicePairAdapter(HttpAdapter):
    """Adapter for the voice-pair FastAPI service (voice synthesis)."""

    async def synthesize(
        self,
        text: str,
        voice_id: str = "default",
        format: str = "wav",
    ) -> dict[str, Any]:
        """Synthesize text to audio; returns {audio_id, path}."""
        return await self._post(
            "/synthesize",
            {"voice_id": voice_id, "text": text, "format": format},
        )

    async def download_url(self, audio_id: str) -> str:
        """Return the download URL for an audio_id."""
        return f"{self.base_url}/download/{audio_id}"

    async def pair_voice(self, voice_id: str) -> dict[str, Any]:
        """Create/update the embedding for a voice_id."""
        return await self._post(f"/pair-voice/{voice_id}", {})

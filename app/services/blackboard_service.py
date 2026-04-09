"""Shared blackboard for inter-agent state using Redis (runtime) and CanonDock (persistent).

Redis holds ephemeral session state (agent outputs, intermediate results).
CanonDock (MongoDB) holds persistent shared memory across sessions.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx

from app.core.settings import Settings

logger = logging.getLogger(__name__)


class Blackboard:
    """Shared state store for multi-agent coordination."""

    def __init__(self, settings: Settings) -> None:
        self.redis_url = getattr(settings, "redis_url", None) or os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")
        self.canondock_url = settings.hapi_base_url.rstrip("/") if hasattr(settings, "hapi_base_url") else "http://127.0.0.1:8020"
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
            except ImportError:
                logger.warning("redis.asyncio not available, blackboard will use in-memory fallback")
                self._redis = InMemoryStore()
        return self._redis

    async def write(self, key: str, value: Any, agent_id: str, ttl: int = 3600) -> None:
        """Write a value to the blackboard. TTL in seconds (default 1h)."""
        r = await self._get_redis()
        entry = {
            "value": value,
            "agent_id": agent_id,
            "timestamp": time.time(),
        }
        await r.set(f"bb:{key}", json.dumps(entry, default=str), ex=ttl)
        logger.debug("Blackboard write: %s by %s", key, agent_id)

    async def read(self, key: str) -> dict[str, Any] | None:
        """Read a value from the blackboard. Returns None if not found."""
        r = await self._get_redis()
        raw = await r.get(f"bb:{key}")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"value": raw, "agent_id": "unknown", "timestamp": 0}

    async def read_value(self, key: str) -> Any | None:
        """Read just the value (unwrapped) from the blackboard."""
        entry = await self.read(key)
        return entry["value"] if entry else None

    async def list_keys(self, pattern: str = "bb:*") -> list[str]:
        """List all blackboard keys matching a pattern."""
        r = await self._get_redis()
        if isinstance(r, InMemoryStore):
            return [k for k in r._store if k.startswith(pattern.replace("*", ""))]
        keys = []
        async for key in r.scan_iter(match=pattern):
            keys.append(key.removeprefix("bb:"))
        return keys

    async def delete(self, key: str) -> bool:
        """Delete a key from the blackboard."""
        r = await self._get_redis()
        result = await r.delete(f"bb:{key}")
        return result > 0

    async def persist_to_canondock(self, key: str, collection: str = "blackboard") -> bool:
        """Persist a blackboard entry to CanonDock (MongoDB) for long-term storage."""
        entry = await self.read(key)
        if not entry:
            return False

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.canondock_url}/api/documents",
                    json={
                        "collection": collection,
                        "document": {
                            "key": key,
                            **entry,
                        },
                    },
                )
                return resp.status_code < 400
        except Exception as exc:
            logger.error("Failed to persist %s to CanonDock: %s", key, exc)
            return False


class InMemoryStore:
    """Fallback when Redis is not available."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._ttls: dict[str, float] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value
        if ex:
            self._ttls[key] = time.time() + ex

    async def get(self, key: str) -> str | None:
        if key in self._ttls and time.time() > self._ttls[key]:
            del self._store[key]
            del self._ttls[key]
            return None
        return self._store.get(key)

    async def delete(self, key: str) -> int:
        if key in self._store:
            del self._store[key]
            self._ttls.pop(key, None)
            return 1
        return 0

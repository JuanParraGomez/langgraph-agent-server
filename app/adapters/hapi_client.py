from __future__ import annotations

import asyncio
from typing import Any

import httpx


class HapiClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class HapiClient:
    def __init__(self, base_url: str, timeout_seconds: int = 20, retries: int = 2) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.retries = retries

    async def health(self) -> dict[str, Any]:
        try:
            data = await self._request("GET", "/health")
            return {"available": True, "base_url": self.base_url, "data": data}
        except Exception as exc:  # pragma: no cover - network variability
            return {"available": False, "base_url": self.base_url, "error": str(exc)}

    async def list_public_apps(self) -> dict[str, Any]:
        return await self._request("GET", "/public/apps")

    async def get_public_app(self, app_id: str) -> dict[str, Any] | None:
        return await self._get_optional(f"/public/apps/{app_id}")

    async def get_public_app_by_slug(self, slug: str) -> dict[str, Any] | None:
        return await self._get_optional(f"/public/apps/by-slug/{slug}")

    async def get_public_app_by_domain(self, domain: str) -> dict[str, Any] | None:
        return await self._get_optional(f"/public/apps/by-domain/{domain}")

    async def register_public_app(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/public/apps/register", payload)

    async def record_deployment(self, app_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"/public/apps/{app_id}/deployment", payload)

    async def record_sync(self, app_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"/public/apps/{app_id}/sync", payload)

    async def deployment_status(self, app_id: str) -> dict[str, Any] | None:
        return await self._get_optional(f"/public/deployments/{app_id}/status")

    async def coolify_health(self) -> dict[str, Any]:
        return await self._request("GET", "/infra/coolify/health")

    async def coolify_resources(self) -> dict[str, Any]:
        return await self._request("GET", "/infra/coolify/resources")

    async def public_summary(self) -> dict[str, Any]:
        return await self._request("GET", "/infra/public-summary")

    async def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/projects/create", payload)

    async def get_project(self, slug: str) -> dict[str, Any]:
        return await self._request("GET", f"/projects/{slug}")

    async def render_project_context(self, slug: str) -> dict[str, Any]:
        return await self._request("POST", f"/projects/{slug}/edit-context", {"include_readme": True})

    async def deploy_project(self, slug: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/projects/{slug}/deploy",
            payload,
            timeout_seconds=max(self.timeout_seconds, 180),
        )

    async def sync_project_rag(self, slug: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"/projects/{slug}/sync-rag", payload)

    async def project_rag_status(self, slug: str) -> dict[str, Any]:
        return await self._request("GET", f"/projects/{slug}/rag-status")

    async def _get_optional(self, path: str) -> dict[str, Any] | None:
        try:
            return await self._request("GET", path)
        except HapiClientError as exc:
            if exc.status_code == 404:
                return None
            raise

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout_seconds or self.timeout_seconds) as client:
                    response = await client.request(method, f"{self.base_url}{path}", json=payload)
                if response.status_code >= 500 and attempt < self.retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                if response.status_code >= 400:
                    body: dict[str, Any]
                    try:
                        body = response.json()
                    except Exception:
                        body = {"detail": response.text}
                    raise HapiClientError(
                        f"hapi_request_failed:{path}",
                        status_code=response.status_code,
                        payload=body,
                    )
                return response.json()
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                await asyncio.sleep(0.2 * (attempt + 1))
        raise HapiClientError(f"hapi_unreachable:{path}", payload={"error": str(last_error)})

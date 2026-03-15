from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router as api_router
from app.core.logging import configure_logging
from app.core.settings import get_settings
from app.mcp_server.router import router as mcp_router
from app.observability.langsmith_setup import configure_langsmith

configure_logging()
settings = get_settings()
langsmith_config = configure_langsmith(settings)

app = FastAPI(title=settings.server_name, version="0.1.0")
app.include_router(api_router)
app.include_router(mcp_router)


@app.get("/")
async def root() -> dict:
    return {"service": settings.server_name, "status": "ok", "langsmith": langsmith_config}

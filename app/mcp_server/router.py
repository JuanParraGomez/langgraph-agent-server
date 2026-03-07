from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.mcp_server.tool_registry import TOOL_HANDLERS, TOOL_SPECS
from app.models.schemas import AgentToolResponse

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/tools")
async def list_tools() -> dict:
    return {"tools": [tool.model_dump(mode="json") for tool in TOOL_SPECS]}


@router.post("/tools/{tool_name}", response_model=AgentToolResponse)
async def call_tool(tool_name: str, payload: dict) -> AgentToolResponse:
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise HTTPException(status_code=404, detail=f"unknown tool: {tool_name}")

    try:
        data = await handler(payload)
        ok = data.get("ok", True) if isinstance(data, dict) else True
        return AgentToolResponse(ok=ok, tool=tool_name, data=data if isinstance(data, dict) else {"value": data})
    except Exception as exc:
        return AgentToolResponse(ok=False, tool=tool_name, data={"error": str(exc)})

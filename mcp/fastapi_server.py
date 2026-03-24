from __future__ import annotations

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from .weather_tool import WeatherMcpServer


app = FastAPI(title="Demo MCP Server", version="0.1.0")
server = WeatherMcpServer()


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.post("/mcp")
async def mcp_endpoint(
    request: Request,
    mcp_protocol_version: str | None = Header(default=None, alias="MCP-Protocol-Version"),
) -> JSONResponse:
    # 这里仅做演示，不强制校验 header。
    payload = await request.json()
    result = server.handle_dict(payload)
    if mcp_protocol_version:
        result.setdefault("_meta", {})
        result["_meta"]["request_protocol_version"] = mcp_protocol_version
    return JSONResponse(result)

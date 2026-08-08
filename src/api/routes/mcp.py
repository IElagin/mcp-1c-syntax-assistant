"""MCP protocol endpoints."""

import json
import asyncio
import time
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from src import __version__
from src.core.logging import get_logger
from src.core.elasticsearch import ElasticsearchClient
from src.api.dependencies import get_elasticsearch_client
from src.api.mcp_tools import TOOLS
from src.models.mcp_models import (
    MCPRequest, MCPResponse, MCPToolType,
    Find1CHelpRequest, Get1CElementRequest, List1CObjectMembersRequest,
)
from src.handlers.mcp_handlers import (
    handle_find_1c_help, handle_get_1c_element, handle_list_1c_object_members,
)

router = APIRouter(prefix="/mcp", tags=["mcp"])
logger = get_logger(__name__)

# Перечень имён берётся из enum, а не переписывается рядом: разойдясь, копия
# советовала бы агенту имя, которого маршрутизатор не знает.
TOOL_NAMES = tuple(t.value for t in MCPToolType)


def call_error(request_id, message: str) -> JSONResponse:
    """JSON-RPC -32602: виноват вызов, а не сервер."""
    return JSONResponse(
        status_code=400,
        content={
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": message},
        },
    )


@router.get("/tools")
async def get_mcp_tools():
    """Возвращает список доступных MCP инструментов."""
    return {"tools": TOOLS}


@router.get("")
async def mcp_sse_endpoint():
    """MCP Server-Sent Events endpoint для потокового соединения."""
    async def event_stream():
        yield f"data: {json.dumps({'type': 'connection', 'status': 'connected'})}\n\n"

        while True:
            await asyncio.sleep(1)
            yield f"data: {json.dumps({'type': 'ping', 'timestamp': int(time.time())})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("")
async def mcp_jsonrpc_endpoint(
    request: Request,
    es_client: ElasticsearchClient = Depends(get_elasticsearch_client)
):
    """MCP JSON-RPC endpoint для обработки MCP протокола."""
    try:
        body = await request.body()
        data = json.loads(body.decode('utf-8'))

        if data.get("jsonrpc") != "2.0":
            return JSONResponse(
                status_code=400,
                content={"error": {"code": -32600, "message": "Invalid Request"}}
            )

        method = data.get("method")
        params = data.get("params", {})
        request_id = data.get("id")

        if method == "initialize":
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "1c-syntax-helper-mcp",
                        "version": __version__
                    }
                }
            })

        elif method == "tools/list":
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": TOOLS}
            })

        elif method == "notifications/initialized":
            return JSONResponse(content={"status": "ok"})

        elif method == "tools/call":
            if not isinstance(params, dict):
                return call_error(request_id, "params must be an object")

            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name not in TOOL_NAMES:
                return call_error(
                    request_id,
                    f"Unknown tool: {tool_name}. "
                    f"Available tools: {', '.join(TOOL_NAMES)}",
                )

            if not isinstance(arguments, dict):
                return call_error(
                    request_id,
                    f"arguments must be an object for tool {tool_name}",
                )

            mcp_request = MCPRequest(tool=tool_name, arguments=arguments)

            result = await mcp_endpoint_handler(mcp_request, es_client)
            error = getattr(result, "error", None)

            content = result.content if not error else [
                {"type": "text", "text": error}
            ]

            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": content, "isError": bool(error)},
            })

        else:
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }
            )

    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": -32700, "message": "Parse error"}}
        )
    except Exception as e:
        logger.error(f"Ошибка в MCP JSON-RPC endpoint: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "id": request_id if 'request_id' in locals() else None,
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
            }
        )


async def mcp_endpoint_handler(request: MCPRequest, es_client: ElasticsearchClient):
    """Внутренний обработчик MCP запросов."""
    logger.info(f"Получен MCP запрос: {request.tool}")

    try:
        if not await es_client.is_connected():
            raise HTTPException(
                status_code=503,
                detail="Elasticsearch недоступен"
            )

        if request.tool == MCPToolType.FIND_1C_HELP:
            return await handle_find_1c_help(Find1CHelpRequest(**request.arguments), es_client)
        elif request.tool == MCPToolType.GET_1C_ELEMENT:
            return await handle_get_1c_element(Get1CElementRequest(**request.arguments), es_client)
        elif request.tool == MCPToolType.LIST_1C_OBJECT_MEMBERS:
            return await handle_list_1c_object_members(List1CObjectMembersRequest(**request.arguments), es_client)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Неизвестный инструмент: {request.tool}"
            )

    except Exception as e:
        logger.error(f"Ошибка обработки MCP запроса: {e}")
        return MCPResponse(content=[], error=str(e))

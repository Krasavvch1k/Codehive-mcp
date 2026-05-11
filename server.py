"""
MCP-сервер CodeHive (Streamable HTTP).

Тонкий transport-shell: реєструє WORQEN_TOOLS + CODEHIVE_TOOLS, диспатчить
виклики у відповідні проєкти. Вся бізнес-логіка живе у projects/<name>/tools.py.
"""

import contextlib
import json

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent

from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send
import uvicorn

from projects.worqen.tools import WORQEN_TOOLS, worqen_dispatch
from projects.codehive.tools import CODEHIVE_TOOLS, dispatch as codehive_dispatch


server = Server("codehive-mcp")


def _format_response(data) -> list[TextContent]:
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return [TextContent(type="text", text=text)]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return WORQEN_TOOLS + CODEHIVE_TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    args = arguments or {}
    try:
        # Worqen tools (33) — диспатчер сам форматує відповідь через _format_response
        worqen_result = worqen_dispatch(name, args, _format_response)
        if worqen_result is not None:
            return worqen_result

        # Codehive tools (4) — диспатчер повертає dict, сервер форматує
        codehive_result = codehive_dispatch(name, args)
        if codehive_result is not None:
            return _format_response(codehive_result)

        return _format_response({"error": f"Невідомий tool: {name}"})

    except Exception as e:
        import traceback
        return _format_response({
            "error": str(e),
            "tool": name,
            "args": args,
            "traceback": traceback.format_exc(),
        })


# ====================== STREAMABLE HTTP TRANSPORT ======================


session_manager = StreamableHTTPSessionManager(
    app=server,
    event_store=None,
    json_response=False,
    stateless=True,
)


async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
    await session_manager.handle_request(scope, receive, send)


@contextlib.asynccontextmanager
async def lifespan(app):
    async with session_manager.run():
        yield


app = Starlette(
    debug=False,
    routes=[Mount("/mcp", app=handle_streamable_http)],
    lifespan=lifespan,
)


if __name__ == "__main__":
    print("=" * 60)
    print("CodeHive MCP Server v2.2: http://127.0.0.1:8765")
    print("Endpoint:                 http://127.0.0.1:8765/mcp")
    print("=" * 60)
    print(f"Tools: {len(WORQEN_TOOLS) + len(CODEHIVE_TOOLS)} "
          f"({len(WORQEN_TOOLS)} worqen_* + {len(CODEHIVE_TOOLS)} codehive_*)")
    print("Cache TTL: 30s")
    print("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")

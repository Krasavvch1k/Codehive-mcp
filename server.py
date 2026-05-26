"""
MCP-сервер CodeHive (Streamable HTTP).

Тонкий transport-shell: проходить по PROJECTS реєстру, кожен MCP-проєкт
сам відповідає за свої tools і dispatch. Вся бізнес-логіка живе у
projects/<name>/(tools.py | ws_tools.py | ...).
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

from projects import PROJECTS


server = Server("codehive-mcp")


def _format_response(data) -> list[TextContent]:
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return [TextContent(type="text", text=text)]


@server.list_tools()
async def list_tools() -> list[Tool]:
    result: list[Tool] = []
    for project in PROJECTS:
        result.extend(project.tools())
    return result


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    args = arguments or {}
    try:
        for project in PROJECTS:
            result = project.try_dispatch(name, args, _format_response)
            if result is not None:
                return result

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
    per_project = [(p.name, len(p.tools())) for p in PROJECTS]
    total = sum(n for _, n in per_project)

    print("=" * 60)
    print("CodeHive MCP Server v2.4: http://127.0.0.1:8765")
    print("Endpoint:                 http://127.0.0.1:8765/mcp")
    print("=" * 60)
    breakdown = " + ".join(f"{n} {name}_*" for name, n in per_project)
    print(f"Tools: {total} ({breakdown})")
    print("Cache TTL: 30s")
    print("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")

"""MCP Tool() декларації і dispatch для worqen_api проєкту.

Експортує:
    WORQEN_API_TOOLS — list[Tool] для server.list_tools
    dispatch(name, arguments) — handler для server.call_tool
"""

from typing import Any

from mcp.types import Tool

from projects.worqen_api.inspector import VALID_MODES, inspect
from projects.worqen_api.spec_cache import refresh_spec

WORQEN_API_TOOLS: list[Tool] = [
    Tool(
        name="worqen_api_inspect",
        description=(
            "Read-only inspection of Worqen Backend Dev OpenAPI spec (305 endpoints, 465 schemas). "
            "Use this to discover endpoints, view exact request/response schemas, and check what the "
            "backend really exposes (vs what PRD says). Six explicit modes:\n"
            "- mode='overview' — title, version, totals, security schemes. No query.\n"
            "- mode='tags' — list of all tags with endpoint counts. No query.\n"
            "- mode='by_tag' — endpoints in one tag. query='Milestones' (case-insensitive).\n"
            "- mode='endpoint' — full schema of one endpoint. query='GET /api/v1/...'.\n"
            "- mode='schema' — full component schema. query='UserRead' (case-insensitive).\n"
            "- mode='search' — fuzzy text search across path/summary/description. query='create vacancy'.\n"
            "Returns {data: ...} on success or {error: ..., candidates?: [...]} on miss. "
            "Spec is cached locally; refresh via worqen_api_refresh_spec when backend changes."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": list(VALID_MODES),
                    "description": "Inspection mode (see tool description).",
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Argument for mode. Omit/empty for overview and tags. "
                        "For by_tag: tag name. For endpoint: 'METHOD /path'. "
                        "For schema: component name. For search: free text."
                    ),
                },
            },
            "required": ["mode"],
        },
    ),
    Tool(
        name="worqen_api_refresh_spec",
        description=(
            "Force re-download of Worqen Backend openapi.json from upstream and overwrite local cache. "
            "Call when backend changed (new endpoints, schema updates). Spec is otherwise served from "
            "local cache to avoid slow upstream (sometimes 26-90s response). Returns counts of paths "
            "and schemas after refresh."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
]


def dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Виклик відповідного handler-а за іменем tool-а.

    Повертає None якщо tool не належить worqen_api — щоб server.py міг
    каскадно передати виклик іншим dispatch-ерам (worqen / codehive).
    """
    if not name.startswith("worqen_api_"):
        return None

    if name == "worqen_api_inspect":
        return inspect(
            mode=arguments.get("mode", ""),
            query=arguments.get("query", "") or "",
        )

    if name == "worqen_api_refresh_spec":
        try:
            spec = refresh_spec()
        except Exception as e:
            return {"error": f"Refresh failed: {type(e).__name__}: {e}"}
        return {
            "data": {
                "paths": len(spec.get("paths", {}) or {}),
                "schemas": len((spec.get("components") or {}).get("schemas") or {}),
                "title": (spec.get("info") or {}).get("title"),
                "version": (spec.get("info") or {}).get("version"),
            }
        }

    return {"error": f"Unknown worqen_api tool: {name}"}

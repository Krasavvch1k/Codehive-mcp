"""WorqenApiProject — обгортка над worqen_api/tools.py під інтерфейс Project."""

from typing import Callable, Optional

from mcp.types import Tool, TextContent

from projects.base import Project
from projects.worqen_api.tools import WORQEN_API_TOOLS, dispatch as _dispatch


class WorqenApiProject(Project):
    """Read-only inspector OpenAPI-специфікації Worqen Backend Dev."""

    name = "worqen_api"

    def tools(self) -> list[Tool]:
        return WORQEN_API_TOOLS

    def try_dispatch(
        self,
        tool_name: str,
        args: dict,
        format_response: Callable[[object], list[TextContent]],
    ) -> Optional[list[TextContent]]:
        result = _dispatch(tool_name, args)
        if result is None:
            return None
        return format_response(result)

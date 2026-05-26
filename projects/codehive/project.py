"""CodehiveProject — обгортка над codehive/tools.py під інтерфейс Project."""

from typing import Callable, Optional

from mcp.types import Tool, TextContent

from projects.base import Project
from projects.codehive.tools import CODEHIVE_TOOLS, dispatch as _dispatch


class CodehiveProject(Project):
    """Read+write tools для CodeHive Agency Shared Drive."""

    name = "codehive"

    def tools(self) -> list[Tool]:
        return CODEHIVE_TOOLS

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

"""WorqenProject — об'єднує worqen-tools і workspace-tools під інтерфейс Project."""

from typing import Callable, Optional

from mcp.types import Tool, TextContent

from projects.base import Project
from projects.worqen.tools import WORQEN_TOOLS, worqen_dispatch
from projects.worqen.ws_tools import WORQEN_WS_TOOLS, ws_dispatch


class WorqenProject(Project):
    """
    Worqen: US/BUG/Docs/team_discussions/ficha + workspace-tools (ws_*).

    Об'єднує два внутрішні диспатчери:
      - worqen_dispatch  — для core-tools (повертає вже відформатований list[TextContent])
      - ws_dispatch      — для ws_*-tools (повертає dict, форматує сервер)
    """

    name = "worqen"

    def tools(self) -> list[Tool]:
        return WORQEN_TOOLS + WORQEN_WS_TOOLS

    def try_dispatch(
        self,
        tool_name: str,
        args: dict,
        format_response: Callable[[object], list[TextContent]],
    ) -> Optional[list[TextContent]]:
        # Core worqen-tools: dispatch сам форматує (returns list[TextContent] | None)
        core_result = worqen_dispatch(tool_name, args, format_response)
        if core_result is not None:
            return core_result

        # Workspace tools: dispatch повертає dict | None — форматує сервер
        ws_result = ws_dispatch(tool_name, args)
        if ws_result is not None:
            return format_response(ws_result)

        return None

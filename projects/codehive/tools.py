"""MCP tool registry for the Codehive module."""

from typing import Optional

from mcp.types import Tool

from projects.codehive import gdoc_reader


CODEHIVE_TOOLS: list[Tool] = [
    Tool(
        name="codehive_list_folder",
        description=(
            "List files and subfolders one level deep in a CodeHive Agency Drive folder. "
            "If folder_id is not provided, defaults to the CodeHive Agency root. "
            "Returns all file types (gdoc, gsheet, gslides, pdf, image, other) in docs[] "
            "plus subfolders in folders[]. For recursive traversal use codehive_list_all_docs."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "folder_id": {
                    "type": "string",
                    "description": "Subfolder ID. Default: CodeHive Agency root.",
                },
            },
        },
    ),
    Tool(
        name="codehive_list_all_docs",
        description=(
            "Recursive traversal of the CodeHive Agency folder. "
            "Returns items[] with path (breadcrumbs) and depth for each entry. "
            "Folders also appear in items[] with kind='folder'. "
            "max_depth: 0 = root only, 3 (default) = root + 3 levels."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum traversal depth. Default 3.",
                },
            },
        },
    ),
    Tool(
        name="codehive_read_doc",
        description=(
            "Read a gdoc from CodeHive Agency as markdown. "
            "query: full Drive ID or partial name (case-insensitive substring). "
            "If more than one document matches, returns an error with the candidate list. "
            "Supports Google Docs only (not gsheet, not pdf)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Drive ID or partial name of a gdoc.",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="codehive_search",
        description=(
            "Search inside CodeHive Agency. "
            "scope: 'names' (fast, default), 'content' (slow, downloads all gdocs), 'both'. "
            "Default limit 20, context_chars 200."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "scope": {
                    "type": "string",
                    "enum": ["names", "content", "both"],
                    "description": "Default: names",
                },
                "limit": {"type": "integer", "description": "Default 20"},
                "context_chars": {"type": "integer", "description": "Default 200"},
            },
            "required": ["query"],
        },
    ),
]


def dispatch(name: str, args: dict) -> Optional[dict]:
    if name == "codehive_list_folder":
        return gdoc_reader.list_folder(folder_id=args.get("folder_id"))

    if name == "codehive_list_all_docs":
        max_depth = args.get("max_depth")
        if max_depth is None:
            return gdoc_reader.list_all_docs()
        return gdoc_reader.list_all_docs(max_depth=int(max_depth))

    if name == "codehive_read_doc":
        return gdoc_reader.read_doc(query=args["query"])

    if name == "codehive_search":
        return gdoc_reader.search(
            query=args["query"],
            scope=args.get("scope", "names"),
            limit=args.get("limit", 20),
            context_chars=args.get("context_chars", 200),
        )

    return None

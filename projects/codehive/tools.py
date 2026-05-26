"""MCP tool registry for the Codehive module."""

from typing import Optional

from mcp.types import Tool

from projects.codehive import gdoc_reader
from projects.codehive import sheets_reader
from projects.codehive import sheets_writer
from projects.codehive.writers import replace_text as replace_text_writer
from projects.codehive.writers import insert_text as insert_text_writer
from projects.codehive.writers import create_doc as create_doc_writer
from projects.codehive.writers import create_folder as create_folder_writer


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
        name="codehive_resolve",
        description=(
            "Resolve a file/folder in CodeHive Agency Drive by name substring or full Drive ID. "
            "Returns a single candidate with reconstructed path. If multiple files match — returns "
            "an error with the candidate list for refinement. "
            "Useful for verifying that other codehive tools will resolve your query correctly."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Name substring (case-insensitive) or full Drive ID.",
                },
            },
            "required": ["query"],
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
        name="codehive_read_file",
        description=(
            "Read a non-Office file from CodeHive Agency as text. "
            ".md / .txt -> raw content as-is (no markdown render). "
            ".pdf -> extracted text layer (no OCR; scanned PDFs error out). "
            "For Google Docs use codehive_read_doc instead. "
            "query: full Drive ID or partial name (case-insensitive substring)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Drive ID or partial name of a .md/.txt/.pdf file.",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="codehive_read_sheet",
        description=(
            "Read a gsheet or xlsx file from CodeHive Agency. "
            "query: full Drive ID or partial name (case-insensitive substring); must resolve to exactly one file. "
            "sheet_name: optional — read only that worksheet; otherwise reads all sheets. "
            "limit_rows / limit_cols: caps to avoid huge payloads (default 200 / 50, max 5000 / 200). "
            "force_refresh: bypass TTL cache. "
            "as_markdown: include a markdown table representation per sheet (default true). "
            "Returns sheets_data[] with values (2D string list) and optional markdown."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Drive ID or partial name of a gsheet or xlsx file.",
                },
                "sheet_name": {
                    "type": "string",
                    "description": "Optional worksheet title. If omitted, reads all sheets.",
                },
                "limit_rows": {
                    "type": "integer",
                    "description": "Max rows per sheet. Default 200, max 5000.",
                },
                "limit_cols": {
                    "type": "integer",
                    "description": "Max columns per sheet. Default 50, max 200.",
                },
                "force_refresh": {
                    "type": "boolean",
                    "description": "Bypass TTL cache. Default false.",
                },
                "as_markdown": {
                    "type": "boolean",
                    "description": "Include markdown table per sheet. Default true.",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="codehive_append_row",
        description=(
            "Append a single row to the end of a gsheet or xlsx in CodeHive Agency. "
            "query: full Drive ID or partial name (case-insensitive substring); must resolve to exactly one gsheet/xlsx. "
            "sheet: worksheet title (exact match). "
            "values: 1D list (not 2D!) — one row of values. "
            "copy_style_from_last: for xlsx — copy font/fill/border/alignment from the previous row. Default true. "
            "dry_run=true returns preview without writing. "
            "force_overwrite bypasses the drive-unchanged safety check (use only if the warning is a false positive). "
            "CONFIRM-FLOW: before calling without dry_run, show the user where and what will be written."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Drive ID or partial name of a gsheet or xlsx.",
                },
                "sheet": {
                    "type": "string",
                    "description": "Worksheet title (exact match).",
                },
                "values": {
                    "type": "array",
                    "description": "1D list of values for one row (not 2D).",
                },
                "copy_style_from_last": {
                    "type": "boolean",
                    "description": "For xlsx — copy style from previous row. Default true.",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Preview without writing. Default false.",
                },
                "force_overwrite": {
                    "type": "boolean",
                    "description": "Bypass drive-unchanged safety check. Default false.",
                },
            },
            "required": ["query", "sheet", "values"],
        },
    ),
    Tool(
        name="codehive_update_cell",
        description=(
            "Overwrite a SINGLE cell in a gsheet or xlsx in CodeHive Agency. "
            "query: full Drive ID or partial name (case-insensitive substring); must resolve to exactly one gsheet/xlsx. "
            "sheet: worksheet title (exact match). "
            "cell: A1 notation of one cell (e.g. 'A1', 'BC42'). "
            "value: new value (string/int/float/bool/null). "
            "dry_run=true returns preview without writing. "
            "force_overwrite bypasses the drive-unchanged safety check. "
            "CONFIRM-FLOW: before calling without dry_run, show the user where and what will be written."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Drive ID or partial name of a gsheet or xlsx.",
                },
                "sheet": {
                    "type": "string",
                    "description": "Worksheet title (exact match).",
                },
                "cell": {
                    "type": "string",
                    "description": "A1 notation of one cell (e.g. 'A1', 'BC42').",
                },
                "value": {
                    "description": "New value (string/int/float/bool/null).",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Preview without writing. Default false.",
                },
                "force_overwrite": {
                    "type": "boolean",
                    "description": "Bypass drive-unchanged safety check. Default false.",
                },
            },
            "required": ["query", "sheet", "cell", "value"],
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
    Tool(
        name="codehive_replace_text",
        description=(
            "Replace exactly one occurrence of old_text with new_text in a CodeHive Agency gdoc. "
            "Case-sensitive substring match. If 0 or >1 occurrences found — returns error with "
            "contexts (no write). Uses optimistic locking via revisionId — if document changed "
            "between read and write, returns error. "
            "CONFIRM-FLOW: before calling this tool, show the user what will be replaced and wait "
            "for explicit confirmation in chat. This tool has no preview mode — calling it writes immediately."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Drive ID or partial name of a gdoc.",
                },
                "old_text": {
                    "type": "string",
                    "description": "Exact text to find (case-sensitive). Must occur exactly once in the document.",
                },
                "new_text": {
                    "type": "string",
                    "description": "Replacement text.",
                },
            },
            "required": ["query", "old_text", "new_text"],
        },
    ),
    Tool(
        name="codehive_insert_text",
        description=(
            "Insert text into a CodeHive Agency gdoc in one of three modes: "
            "'after' (right after anchor substring), 'before' (right before anchor), "
            "or 'end_of_doc' (at the end of body, anchor must be None). "
            "Anchor is case-sensitive and must occur exactly once. "
            "as_paragraph=true wraps text with newlines so it becomes a separate paragraph. "
            "Uses optimistic locking via revisionId. "
            "CONFIRM-FLOW: before calling, show the user what will be inserted where and wait for "
            "explicit confirmation in chat. No preview mode — calling writes immediately."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Drive ID or partial name of a gdoc.",
                },
                "text": {
                    "type": "string",
                    "description": "Text to insert. Verbatim by default; use as_paragraph=true to wrap in newlines.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["after", "before", "end_of_doc"],
                    "description": "Where to insert relative to anchor (or document end).",
                },
                "anchor": {
                    "type": "string",
                    "description": "Substring to find (case-sensitive, must be unique). Required for after/before, must be omitted for end_of_doc.",
                },
                "as_paragraph": {
                    "type": "boolean",
                    "description": "Wrap text in newlines so it becomes a separate paragraph. Default false.",
                },
            },
            "required": ["query", "text", "mode"],
        },
    ),
    Tool(
        name="codehive_create_doc",
        description=(
            "Create a new Google Doc inside a CodeHive Agency folder. "
            "folder_query: full Drive ID or partial name (case-insensitive substring) of the target folder. "
            "If more than one folder matches the query, returns an error with candidate list. "
            "If a gdoc with the same name already exists in the target folder, returns an error (no creation). "
            "initial_content is optional plain text inserted at document end after creation. "
            "Returns file_id, url, and folder info. "
            "CONFIRM-FLOW: before calling, show the user where the doc will be created and what name/content. "
            "No preview mode — calling creates the doc immediately."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the new document.",
                },
                "folder_query": {
                    "type": "string",
                    "description": "Drive ID or partial name of the target folder (must resolve to exactly one).",
                },
                "initial_content": {
                    "type": "string",
                    "description": "Optional plain text to insert into the document body. Default: empty document.",
                },
            },
            "required": ["name", "folder_query"],
        },
    ),
    Tool(
        name="codehive_create_folder",
        description=(
            "Create a new folder inside a CodeHive Agency Drive folder. "
            "parent_folder is optional — defaults to CodeHive Agency root. "
            "Substring (case-insensitive) or full Drive ID for parent_folder. "
            "allow_duplicate=true permits creating a folder with the same name "
            "as an existing one. dry_run=true returns a preview without creating. "
            "CONFIRM-FLOW: confirm with the user before calling (no preview mode unless dry_run=true)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the new folder.",
                },
                "parent_folder": {
                    "type": "string",
                    "description": "Drive ID or partial name of parent folder. Default: CodeHive Agency root.",
                },
                "allow_duplicate": {
                    "type": "boolean",
                    "description": "Allow creating a folder when one with the same name already exists. Default false.",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Return preview without creating. Default false.",
                },
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="codehive_force_refresh",
        description=(
            "Invalidate the TTL cache, either targeted (one file/folder by query) or full. "
            "Without query — clears entire cache (file + folder). "
            "With query — clears cache for one file/folder (resolved via Drive search). "
            "Useful when you just edited a file manually in Drive UI and want fresh data immediately, "
            "or when new files appeared in a folder but the folder cache TTL has not expired."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Drive ID or substring of name. Omit to clear entire cache.",
                },
            },
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

    if name == "codehive_resolve":
        try:
            return gdoc_reader.resolve_doc(args["query"])
        except ValueError as e:
            return {"error": str(e)}

    if name == "codehive_read_doc":
        return gdoc_reader.read_doc(query=args["query"])

    if name == "codehive_read_file":
        return gdoc_reader.read_file(query=args["query"])

    if name == "codehive_read_sheet":
        return sheets_reader.read_sheet(
            query=args["query"],
            sheet_name=args.get("sheet_name"),
            limit_rows=args.get("limit_rows", 200),
            limit_cols=args.get("limit_cols", 50),
            force_refresh=args.get("force_refresh", False),
            as_markdown=args.get("as_markdown", True),
        )

    if name == "codehive_append_row":
        return sheets_writer.append_row(
            query=args["query"],
            sheet=args["sheet"],
            values=args["values"],
            copy_style_from_last=args.get("copy_style_from_last", True),
            dry_run=args.get("dry_run", False),
            force_overwrite=args.get("force_overwrite", False),
        )

    if name == "codehive_update_cell":
        return sheets_writer.update_cell(
            query=args["query"],
            sheet=args["sheet"],
            cell=args["cell"],
            value=args["value"],
            dry_run=args.get("dry_run", False),
            force_overwrite=args.get("force_overwrite", False),
        )

    if name == "codehive_search":
        return gdoc_reader.search(
            query=args["query"],
            scope=args.get("scope", "names"),
            limit=args.get("limit", 20),
            context_chars=args.get("context_chars", 200),
        )

    if name == "codehive_replace_text":
        return replace_text_writer.replace_text(
            query=args["query"],
            old_text=args["old_text"],
            new_text=args["new_text"],
        )

    if name == "codehive_insert_text":
        return insert_text_writer.insert_text(
            query=args["query"],
            text=args["text"],
            mode=args["mode"],
            anchor=args.get("anchor"),
            as_paragraph=args.get("as_paragraph", False),
        )

    if name == "codehive_create_doc":
        return create_doc_writer.create_doc(
            name=args["name"],
            folder_query=args["folder_query"],
            initial_content=args.get("initial_content", ""),
        )

    if name == "codehive_create_folder":
        return create_folder_writer.create_folder(
            name=args["name"],
            parent_folder=args.get("parent_folder"),
            allow_duplicate=args.get("allow_duplicate", False),
            dry_run=args.get("dry_run", False),
        )

    if name == "codehive_force_refresh":
        return gdoc_reader.force_refresh(query=args.get("query"))

    return None

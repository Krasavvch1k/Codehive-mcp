"""
Shared resolve utility for Drive file lookup.

Two projects (worqen, codehive) had identical `_resolve_via_drive_search`
implementations (~165 lines each, byte-for-byte equivalent except for error
messages). This module consolidates that logic.

Project-specific helpers (`_classify_item`, `_resolve_root`, `_get_folder_name`)
remain in each project. They are injected via `ResolveContext`.

Error messages here are English — they are diagnostic for developers, not
end-user content.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from shared.drive_client import (
    build_path_for_file,
    get_file_metadata,
    search_files_by_name,
)


GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"


# ---------------------------------------------------------------------------
# Public helpers (also usable independently)
# ---------------------------------------------------------------------------

def looks_like_drive_id(s: str) -> bool:
    """Heuristic: Drive IDs are >25 chars, no spaces or parens."""
    return len(s) > 25 and " " not in s and "(" not in s


def normalize_item(
    item: dict,
    parent_id: str,
    parent_name: Optional[str],
    *,
    classify_kind: Callable[[dict], str],
) -> dict:
    """Project-agnostic normalization of a Drive API raw item.

    `classify_kind` is project-specific because mime → kind mapping differs
    between worqen (xlsx, gsheet, docx, gdoc, folder, other) and codehive
    (gdoc, gsheet, gslides, pdf, image, other).
    """
    return {
        "id": item["id"],
        "name": item.get("name", ""),
        "mime": item.get("mimeType", ""),
        "kind": classify_kind(item),
        "modified": item.get("modifiedTime"),
        "size_bytes": int(item["size"]) if item.get("size") else None,
        "parent_folder_id": parent_id,
        "parent_folder_name": parent_name,
    }


def format_wrong_kind_error(
    query: str,
    found: list[dict],
    expected_kinds: tuple[str, ...],
) -> str:
    """Format error when query matched files but of wrong kind."""
    previews = []
    for f in found[:5]:
        previews.append(
            f"{f['name']} (kind={f['kind']}, id: {f['id'][:12]}...)"
        )
    more = f", ...{len(found) - 5} more" if len(found) > 5 else ""
    expected = "/".join(expected_kinds)
    return (
        f"Query '{query}' matched {len(found)} file(s) but none of type "
        f"{expected}. Found: {'; '.join(previews)}{more}. "
        f"Possibly wrong tool for this kind."
    )


# ---------------------------------------------------------------------------
# Context for project-specific resolve
# ---------------------------------------------------------------------------

@dataclass
class ResolveContext:
    """Project-specific dependencies injected into resolve functions.

    Fields:
        root_id: Drive ID of the project's root folder / Shared Drive.
        root_name: Human-readable name of root (e.g. "Worqen", "CodeHive Agency").
        workspace_label: Project label used in error messages
            (e.g. "Worqen Drive", "CodeHive Agency").
        list_all_hint_tool: Tool name suggested in "not found" errors
            (e.g. "worqen_ws_list_all", "codehive_list_all_docs").
        classify_kind: Function mapping a raw Drive item dict → kind string.
    """
    root_id: str
    root_name: Optional[str]
    workspace_label: str
    list_all_hint_tool: str
    classify_kind: Callable[[dict], str]


# ---------------------------------------------------------------------------
# Core: resolve via native Drive search (depth-independent)
# ---------------------------------------------------------------------------

def resolve_via_drive_search(
    query: str,
    ctx: ResolveContext,
    kind_filter: Optional[tuple[str, ...]] = None,
) -> dict:
    """Find a file via native Drive search (one API call), regardless of depth.

    kind_filter: if provided, only files with kind in this tuple are returned.
        Files of other kind raise an informative ValueError.

    Returns normalized item with reconstructed path on single match.
    Raises ValueError on 0 matches, >1 matches, or wrong-kind matches.
    """
    # Optimization: if kind_filter is only ("folder",), pre-filter at Drive API level
    mime_pre_filter: Optional[str] = None
    if kind_filter == ("folder",):
        mime_pre_filter = GOOGLE_FOLDER_MIME

    # ID-style query — try as exact file ID first
    if looks_like_drive_id(query):
        try:
            meta = get_file_metadata(query)
            if meta.get("id"):
                normalized = normalize_item(
                    meta, "", None, classify_kind=ctx.classify_kind
                )
                if kind_filter and normalized["kind"] not in kind_filter:
                    raise ValueError(
                        format_wrong_kind_error(query, [normalized], kind_filter)
                    )
                path = build_path_for_file(meta["id"], ctx.root_id, ctx.root_name)
                if path:
                    normalized["path"] = path
                normalized["depth"] = path.count(" > ") if path else 0
                return normalized
        except ValueError:
            raise
        except Exception:
            pass  # not a valid id or no access — fall through to name search

    # Substring in name — native Drive search
    raw_results = search_files_by_name(
        query, drive_id=ctx.root_id, mime_type=mime_pre_filter
    )

    # Drive API case-insensitive substring isn't strictly consistent —
    # additionally filter locally
    q_lower = query.lower()
    raw_results = [r for r in raw_results if q_lower in r.get("name", "").lower()]

    if not raw_results:
        raise ValueError(
            f"Nothing found for query='{query}' in {ctx.workspace_label}. "
            f"Try {ctx.list_all_hint_tool} to see available names."
        )

    normalized_all = [
        normalize_item(r, "", None, classify_kind=ctx.classify_kind)
        for r in raw_results
    ]

    if kind_filter:
        matched = [n for n in normalized_all if n["kind"] in kind_filter]
        if not matched:
            raise ValueError(
                format_wrong_kind_error(query, normalized_all, kind_filter)
            )
        normalized_all = matched

    if len(normalized_all) > 1:
        previews = []
        for n in normalized_all[:5]:
            path = build_path_for_file(n["id"], ctx.root_id, ctx.root_name) or "?"
            previews.append(f"{n['name']} [{path}] (id: {n['id'][:12]}...)")
        more = f", ...{len(normalized_all) - 5} more" if len(normalized_all) > 5 else ""
        raise ValueError(
            f"Query '{query}' matched {len(normalized_all)} files. "
            f"Refine the query. Candidates: {'; '.join(previews)}{more}"
        )

    found = normalized_all[0]
    path = build_path_for_file(found["id"], ctx.root_id, ctx.root_name)
    if path:
        found["path"] = path
    found["depth"] = path.count(" > ") if path else 0
    return found


# ---------------------------------------------------------------------------
# High-level: resolve with optional legacy candidates mode
# ---------------------------------------------------------------------------

def resolve(
    query: str,
    ctx: ResolveContext,
    candidates: Optional[list[dict]] = None,
    kind_filter: Optional[tuple[str, ...]] = None,
) -> dict:
    """Resolve a file/folder by query.

    query:
        - full Drive ID (heuristic: >25 chars, no spaces/parens) → exact id match
        - otherwise substring in name (case-insensitive)

    Three modes:
        1. candidates provided — search within that list only (legacy mode used
           by consumers that already have a filtered list, e.g. search()).
        2. kind_filter without candidates — native Drive search with kind filter.
        3. Neither — native Drive search without filter.

    Raises:
        ValueError on 0 / multiple matches or wrong-kind match.
    """
    q = query.strip()
    if not q:
        raise ValueError("query cannot be empty")

    # Mode 1: search within provided candidates list
    if candidates is not None:
        if looks_like_drive_id(q):
            for c in candidates:
                if c["id"] == q:
                    return c

        q_lower = q.lower()
        matches = [c for c in candidates if q_lower in c["name"].lower()]

        if not matches:
            raise ValueError(
                f"Nothing found for query='{query}' in {ctx.workspace_label}. "
                f"Try {ctx.list_all_hint_tool} to see available names."
            )

        if len(matches) > 1:
            names = [
                f"{m['name']} [{m.get('path', '?')}] (id: {m['id'][:12]}...)"
                for m in matches[:5]
            ]
            more = f", ...{len(matches) - 5} more" if len(matches) > 5 else ""
            raise ValueError(
                f"Query '{query}' matched {len(matches)} items. "
                f"Refine the query. Candidates: {'; '.join(names)}{more}"
            )

        return matches[0]

    # Modes 2 & 3: native Drive search
    return resolve_via_drive_search(q, ctx, kind_filter=kind_filter)

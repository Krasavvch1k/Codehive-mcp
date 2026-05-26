"""Read operations for the CodeHive Agency Drive folder."""

from typing import Optional

from shared.drive_client import (
    _list_folder_children,
    download_file,
    get_folder_or_drive_name,
    get_service,
)
from projects.codehive.config import (
    CODEHIVE_ROOT_FOLDER_ID,
    GOOGLE_DOC_MIME,
    GOOGLE_FOLDER_MIME,
    CODEHIVE_MAX_RECURSION_DEPTH,
)
from shared.gdoc import (
    docx_bytes_to_markdown,
    docx_bytes_to_plain_text,
    extract_snippet,
)
from shared.plaintext import decode_text_bytes
from shared.resolve import ResolveContext, resolve as shared_resolve


def _resolve_root(folder_id: Optional[str]) -> str:
    if folder_id:
        return folder_id
    if not CODEHIVE_ROOT_FOLDER_ID:
        raise RuntimeError(
            "CODEHIVE_ROOT_FOLDER_ID is not set in .env. "
            "Add CODEHIVE_ROOT_FOLDER_ID=<id> and restart the MCP server."
        )
    return CODEHIVE_ROOT_FOLDER_ID


def _get_folder_name(folder_id: str) -> Optional[str]:
    """Best-effort fetch of a folder display name (handles Shared Drive root quirk)."""
    return get_folder_or_drive_name(folder_id)


def _classify_item(item: dict) -> str:
    mime = item.get("mimeType", "")
    if mime == GOOGLE_FOLDER_MIME:
        return "folder"
    if mime == GOOGLE_DOC_MIME:
        return "gdoc"
    if mime == "application/vnd.google-apps.spreadsheet":
        return "gsheet"
    if mime == "application/vnd.google-apps.presentation":
        return "gslides"
    if mime == "application/pdf":
        return "pdf"
    if mime.startswith("image/"):
        return "image"
    if mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return "docx"
    if mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        return "xlsx"
    if mime == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
        return "pptx"
    return "other"


def _normalize_item(item: dict, parent_id: str, parent_name: Optional[str]) -> dict:
    return {
        "id": item["id"],
        "name": item.get("name", ""),
        "mime": item.get("mimeType", ""),
        "kind": _classify_item(item),
        "modified": item.get("modifiedTime"),
        "size_bytes": int(item["size"]) if item.get("size") else None,
        "parent_folder_id": parent_id,
        "parent_folder_name": parent_name,
    }


def _build_resolve_ctx() -> ResolveContext:
    """Build ResolveContext for shared.resolve.

    Re-fetches root_name on each call (handled by cached drive_client under the hood).
    """
    root_id = _resolve_root(None)
    return ResolveContext(
        root_id=root_id,
        root_name=_get_folder_name(root_id),
        workspace_label="CodeHive Agency",
        list_all_hint_tool="codehive_list_all_docs",
        classify_kind=_classify_item,
    )


def list_folder(folder_id: Optional[str] = None) -> dict:
    fid = _resolve_root(folder_id)
    folder_name = _get_folder_name(fid)

    raw_children = _list_folder_children(fid)

    folders: list[dict] = []
    docs: list[dict] = []
    for item in raw_children:
        normalized = _normalize_item(item, fid, folder_name)
        if normalized["kind"] == "folder":
            folders.append(normalized)
        else:
            docs.append(normalized)

    folders.sort(key=lambda d: d["name"].lower())
    docs.sort(key=lambda d: d["name"].lower())

    return {
        "folder_id": fid,
        "folder_name": folder_name,
        "folders_count": len(folders),
        "docs_count": len(docs),
        "folders": folders,
        "docs": docs,
    }


def list_all_docs(max_depth: int = CODEHIVE_MAX_RECURSION_DEPTH) -> dict:
    root_id = _resolve_root(None)
    root_name = _get_folder_name(root_id)

    items: list[dict] = []
    total_folders = 0
    total_docs = 0

    queue: list[tuple[str, Optional[str], str, int]] = [
        (root_id, root_name, "", 0),
    ]

    while queue:
        cur_id, cur_name, cur_path, depth = queue.pop(0)
        if depth > max_depth:
            continue

        children = _list_folder_children(cur_id)
        for item in children:
            normalized = _normalize_item(item, cur_id, cur_name)
            sub_path = (
                f"{cur_path} > {normalized['name']}"
                if cur_path
                else normalized["name"]
            )
            normalized["path"] = sub_path
            normalized["depth"] = depth + 1
            items.append(normalized)

            if normalized["kind"] == "folder":
                total_folders += 1
                if depth + 1 < max_depth:
                    queue.append((normalized["id"], normalized["name"], sub_path, depth + 1))
            else:
                total_docs += 1

    items.sort(key=lambda d: d["path"].lower())

    return {
        "root_folder_id": root_id,
        "root_folder_name": root_name,
        "max_depth": max_depth,
        "total_folders": total_folders,
        "total_docs": total_docs,
        "items": items,
    }


def resolve_doc(
    query: str,
    all_docs: Optional[list[dict]] = None,
    kind_filter: Optional[tuple[str, ...]] = None,
) -> dict:
    """
    Resolve a file by query.

    Thin wrapper over shared.resolve.resolve() with codehive-specific
    ResolveContext (CodeHive Agency root, codehive_list_all_docs hint tool).

    Two modes:
      - all_docs provided (legacy): search within the provided list. Used by
        consumers that already have a filtered list_all_docs result (e.g. search).
      - all_docs is None: native Drive search, with optional kind_filter.
        Works regardless of tree depth.
    """
    return shared_resolve(
        query,
        _build_resolve_ctx(),
        candidates=all_docs,
        kind_filter=kind_filter,
    )


def read_doc(query: str) -> dict:
    doc_meta = resolve_doc(query, kind_filter=("gdoc",))

    content = download_file(doc_meta["id"], fmt="gdoc")
    text = docx_bytes_to_markdown(content)

    return {
        "id": doc_meta["id"],
        "name": doc_meta["name"],
        "mime": doc_meta["mime"],
        "path": doc_meta.get("path"),
        "modified": doc_meta.get("modified"),
        "length": len(text),
        "text": text,
    }


def read_file(query: str) -> dict:
    """
    Read a non-Office file from CodeHive Agency as text.

    .md / .txt (kind=other) -> raw content as-is (no markdown render).
    .pdf -> extracted text layer via pypdf (no OCR; scans raise an error).

    For gdoc use read_doc instead.

    Raises:
        ValueError if not found, ambiguous, or not a text/pdf file
        (NotTextFileError subclasses ValueError).
    """
    doc_meta = resolve_doc(query, kind_filter=("other", "pdf"))

    fmt = "pdf" if doc_meta["kind"] == "pdf" else "md"
    content = download_file(doc_meta["id"], fmt=fmt)
    text = decode_text_bytes(content, doc_meta["kind"], doc_meta["name"])

    return {
        "id": doc_meta["id"],
        "name": doc_meta["name"],
        "mime": doc_meta["mime"],
        "kind": doc_meta["kind"],
        "path": doc_meta.get("path"),
        "modified": doc_meta.get("modified"),
        "length": len(text),
        "text": text,
    }


def search(
    query: str,
    scope: str = "names",
    limit: int = 20,
    context_chars: int = 200,
) -> dict:
    if scope not in ("names", "content", "both"):
        raise ValueError(f"scope must be 'names' / 'content' / 'both', not '{scope}'")

    all_data = list_all_docs(max_depth=CODEHIVE_MAX_RECURSION_DEPTH)
    items = all_data["items"]
    q_lower = query.lower()

    name_matches: list[dict] = []
    content_matches: list[dict] = []

    if scope in ("names", "both"):
        for it in items:
            if q_lower in it["name"].lower() or (
                it.get("path") and q_lower in it["path"].lower()
            ):
                name_matches.append(it)

    if scope in ("content", "both"):
        gdocs = [d for d in items if d["kind"] == "gdoc"]
        for d in gdocs:
            try:
                content = download_file(d["id"], fmt="gdoc")
                full_text = docx_bytes_to_plain_text(content)
                snippet = extract_snippet(full_text, query, context_chars)
                if snippet is not None:
                    content_matches.append({
                        "id": d["id"],
                        "name": d["name"],
                        "path": d.get("path"),
                        "snippet": snippet,
                    })
            except Exception as e:
                content_matches.append({
                    "id": d["id"],
                    "name": d["name"],
                    "path": d.get("path"),
                    "error": str(e),
                })

    return {
        "scope": scope,
        "query": query,
        "total_name_matches": len(name_matches),
        "total_content_matches": len(content_matches),
        "name_matches": name_matches[:limit],
        "content_matches": content_matches[:limit],
    }

"""
Worqen Workspace — динамічне виявлення і читання файлів у Worqen Shared Drive.

Воркспейс — Shared Drive "Worqen" (corner WORQEN_ROOT_FOLDER_ID).
Усі файли, які лежать у Worqen Drive і підпапках, доступні через ws-tools.
Pinned файли (FILE_IDS) — теж видимі тут, але для них є дублюючі worqen_* read-tools
з спеціалізованою логікою (наприклад get_doc_section з TOC). ws-tools — generic.

Це шар list/resolve/read. Sheets-логіка — у ws_sheet_reader.
"""

from typing import Optional

from shared.drive_client import (
    _list_folder_children,
    clear_cache as clear_drive_cache,
    clear_folder_cache,
    download_file,
    get_folder_or_drive_name,
    get_service,
)
from shared.gdoc import (
    docx_bytes_to_markdown,
    docx_bytes_to_plain_text,
    extract_snippet,
)
from shared.plaintext import decode_text_bytes
from shared.resolve import ResolveContext, resolve as shared_resolve
from projects.worqen.config import (
    GOOGLE_DOC_MIME,
    GOOGLE_FOLDER_MIME,
    GOOGLE_SHEET_MIME,
    GOOGLE_SLIDES_MIME,
    WORQEN_ROOT_FOLDER_ID,
    WS_MAX_RECURSION_DEPTH,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_root(folder_id: Optional[str]) -> str:
    """Якщо folder_id переданий — використовуємо його, інакше — Worqen Drive root."""
    if folder_id:
        return folder_id
    if not WORQEN_ROOT_FOLDER_ID:
        raise RuntimeError(
            "WORQEN_ROOT_FOLDER_ID is not set in .env. "
            "Add WORQEN_ROOT_FOLDER_ID=<id> and restart the MCP server."
        )
    return WORQEN_ROOT_FOLDER_ID


def _classify_item(item: dict) -> str:
    """Класифікує файл за MIME-типом."""
    mime = item.get("mimeType", "")
    if mime == GOOGLE_FOLDER_MIME:
        return "folder"
    if mime == GOOGLE_DOC_MIME:
        return "gdoc"
    if mime == GOOGLE_SHEET_MIME:
        return "gsheet"
    if mime == GOOGLE_SLIDES_MIME:
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


def _get_folder_name(folder_id: str) -> Optional[str]:
    """Назва папки/драйва (handles Shared Drive root quirk)."""
    return get_folder_or_drive_name(folder_id)


def _build_resolve_ctx() -> ResolveContext:
    """Build ResolveContext for shared.resolve.

    Re-fetches root_name on each call (handled by cached drive_client under the hood).
    """
    root_id = _resolve_root(None)
    return ResolveContext(
        root_id=root_id,
        root_name=_get_folder_name(root_id),
        workspace_label="Worqen Drive",
        list_all_hint_tool="worqen_ws_list_all",
        classify_kind=_classify_item,
    )


# ---------------------------------------------------------------------------
# Public: list_folder
# ---------------------------------------------------------------------------


def list_folder(folder_id: Optional[str] = None) -> dict:
    """
    Один рівень: повертає підпапки і файли у вказаній папці.

    Якщо folder_id не передано — корінь Worqen Drive.
    Кешується через _list_folder_children (TTL з shared.config).
    """
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


# ---------------------------------------------------------------------------
# Public: list_all
# ---------------------------------------------------------------------------


def list_all(
    max_depth: int = WS_MAX_RECURSION_DEPTH,
    folder_id: Optional[str] = None,
) -> dict:
    """
    BFS-обхід воркспейсу (або підпапки, якщо folder_id вказано).

    max_depth: глибина від root (1 = тільки прямі діти, 2 = +їх діти, тощо).
    Кожен item має поле 'path' (breadcrumb через ' > ') і 'depth'.
    """
    root_id = _resolve_root(folder_id)
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
                    queue.append(
                        (normalized["id"], normalized["name"], sub_path, depth + 1)
                    )
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


# ---------------------------------------------------------------------------
# Public: resolve
# ---------------------------------------------------------------------------


def resolve(
    query: str,
    candidates: Optional[list[dict]] = None,
    kind_filter: Optional[tuple[str, ...]] = None,
) -> dict:
    """
    Знаходить файл/папку за query.

    Тонкий wrapper над shared.resolve.resolve() з worqen-specific ResolveContext
    (Worqen Drive root, worqen_ws_list_all як hint tool).

    query:
        - повний Drive ID (детектиться: довжина > 25, без пробілів/дужок) — точне співпадіння по id
        - інакше substring у name (case-insensitive)

    Три режими:
        1. candidates передано — пошук тільки серед них (legacy). Використовується
           тими consumer-ами які вже мають готовий filtered список.
        2. kind_filter передано без candidates — нативний Drive search з фільтром
           по типу файла ("docx", "gdoc", "gsheet", "xlsx", "folder" тощо).
        3. Нічого з двох — нативний Drive search без фільтра.

    Raises:
        ValueError якщо нічого не знайдено / знайдено кілька / wrong kind.
    """
    return shared_resolve(
        query,
        _build_resolve_ctx(),
        candidates=candidates,
        kind_filter=kind_filter,
    )


# ---------------------------------------------------------------------------
# Public: read_doc (docx + gdoc)
# ---------------------------------------------------------------------------


def read_doc(query: str, force_refresh: bool = False) -> dict:
    """
    Читає docx або gdoc як markdown.

    query: name substring або повний Drive ID.
    force_refresh: якщо True — обходить TTL-кеш у drive_client (свіже з Drive).

    Raises:
        ValueError якщо файл не знайдено або це не docx/gdoc.
    """
    doc_meta = resolve(query, kind_filter=("docx", "gdoc"))

    fmt = "gdoc" if doc_meta["kind"] == "gdoc" else "docx"
    content = download_file(doc_meta["id"], fmt=fmt, force_refresh=force_refresh)
    text = docx_bytes_to_markdown(content)

    return {
        "id": doc_meta["id"],
        "name": doc_meta["name"],
        "mime": doc_meta["mime"],
        "kind": doc_meta["kind"],
        "path": doc_meta.get("path"),
        "modified": doc_meta.get("modified"),
        "length": len(text),
        "force_refresh": force_refresh,
        "text": text,
    }



# ---------------------------------------------------------------------------
# Public: read_file (md / txt / pdf — не-Office)
# ---------------------------------------------------------------------------


def read_file(query: str, force_refresh: bool = False) -> dict:
    """
    Читає НЕ-Office файл як текст: .md / .txt (kind=other) або .pdf.

    Дзеркало read_doc, але для текстових/pdf файлів:
    - .md / .txt → raw bytes декодуються як UTF-8 (як є, без markdown-рендеру)
    - .pdf       → витяг текстового шару через pypdf (без OCR)

    query: name substring або повний Drive ID.
    force_refresh: True — обійти TTL-кеш drive_client (свіже з Drive).

    Raises:
        ValueError якщо файл не знайдено, або це не текст/pdf,
        або тексту витягти не вдалось (NotTextFileError успадковує ValueError).
    """
    doc_meta = resolve(query, kind_filter=("other", "pdf"))

    fmt = "pdf" if doc_meta["kind"] == "pdf" else "md"
    content = download_file(doc_meta["id"], fmt=fmt, force_refresh=force_refresh)
    text = decode_text_bytes(content, doc_meta["kind"], doc_meta["name"])

    return {
        "id": doc_meta["id"],
        "name": doc_meta["name"],
        "mime": doc_meta["mime"],
        "kind": doc_meta["kind"],
        "path": doc_meta.get("path"),
        "modified": doc_meta.get("modified"),
        "length": len(text),
        "force_refresh": force_refresh,
        "text": text,
    }

# ---------------------------------------------------------------------------
# Public: force_refresh
# ---------------------------------------------------------------------------


def force_refresh(query: Optional[str] = None) -> dict:
    """
    Інвалідує кеш точково або повністю.

    query:
        - None або '' — скидає весь TTL-кеш (file + folder)
        - Drive ID або substring назви — скидає кеш для одного файлу/папки

    Корисно коли:
    - ти руками відредагував файл у Drive UI і хочеш одразу побачити свіже
    - щойно з'явились нові файли у папці (folder cache TTL ще не вийшов)
    """
    if not query:
        clear_drive_cache()
        clear_folder_cache()
        return {"ok": True, "cleared": "all"}

    # Точкове скидання — треба знайти id
    target = resolve(query)
    fid = target["id"]
    clear_drive_cache(fid)
    clear_folder_cache(fid)
    return {
        "ok": True,
        "cleared": "single",
        "id": fid,
        "name": target["name"],
        "kind": target["kind"],
    }

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
    get_service,
)
from shared.gdoc import (
    docx_bytes_to_markdown,
    docx_bytes_to_plain_text,
    extract_snippet,
)
from shared.plaintext import decode_text_bytes
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
    """Назва папки/драйва. Drive API для shared drive root повертає 'Drive' —
    тоді беремо реальну назву через drives().get(driveId=...).
    """
    service = get_service()
    try:
        meta = service.files().get(
            fileId=folder_id,
            fields="id, name, mimeType",
            supportsAllDrives=True,
        ).execute()
        name = meta.get("name")
    except Exception:
        name = None

    if name in (None, "Drive"):
        # Можливо це сам Shared Drive — спробуємо drives().get
        try:
            drive_meta = service.drives().get(
                driveId=folder_id,
                fields="id, name",
            ).execute()
            name = drive_meta.get("name") or name
        except Exception:
            pass
    return name


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


def _looks_like_drive_id(s: str) -> bool:
    """Heuristic: довге, без пробілів, без дужок — ймовірно Drive ID."""
    return len(s) > 25 and " " not in s and "(" not in s


def _format_wrong_kind_error(
    query: str,
    found_items: list[dict],
    kind_filter: tuple[str, ...],
) -> str:
    """Готує читабельну помилку для випадку 'знайдено, але не той тип'."""
    previews = []
    for it in found_items[:5]:
        previews.append(
            f"{it['name']} (kind={it['kind']}, id: {it['id'][:12]}...)"
        )
    more = f", ...{len(found_items) - 5} more" if len(found_items) > 5 else ""
    expected = "/".join(kind_filter)
    return (
        f"Query '{query}' матчить {len(found_items)} файл(и), "
        f"але жоден не {expected}. Знайдено: {'; '.join(previews)}{more}. "
        f"Можливо ти хотів інший tool для цього типу."
    )


def _resolve_via_drive_search(
    query: str,
    kind_filter: Optional[tuple[str, ...]] = None,
) -> dict:
    """
    Знаходить файл через нативний Drive search (один API call),
    незалежно від глибини у дереві.

    kind_filter: якщо передано — повертаємо тільки файли з kind у цьому tuple.
        Файли іншого типу повідомляються в окремій помилці.

    Якщо знайдено 1 — повертає normalized item з реконструйованим path.
    0 / >1 / wrong-kind — підіймає ValueError з деталями.
    """
    from shared.drive_client import (
        build_path_for_file,
        get_file_metadata,
        search_files_by_name,
    )

    root_id = _resolve_root(None)
    root_name = _get_folder_name(root_id)

    # Оптимізація: якщо kind_filter тільки "folder" — фільтруємо одразу у Drive query
    mime_pre_filter: Optional[str] = None
    if kind_filter == ("folder",):
        mime_pre_filter = GOOGLE_FOLDER_MIME

    # ID-стиль — спершу пробуємо як точний id
    if _looks_like_drive_id(query):
        try:
            meta = get_file_metadata(query)
            if meta.get("id"):
                normalized = _normalize_item(meta, parent_id="", parent_name=None)
                if kind_filter and normalized["kind"] not in kind_filter:
                    raise ValueError(
                        _format_wrong_kind_error(query, [normalized], kind_filter)
                    )
                path = build_path_for_file(meta["id"], root_id, root_name)
                if path:
                    normalized["path"] = path
                normalized["depth"] = path.count(" > ") if path else 0
                return normalized
        except ValueError:
            raise
        except Exception:
            pass  # не валідний id або немає доступу — падаємо у name search

    # Substring у назві — нативний Drive search
    raw_results = search_files_by_name(
        query, drive_id=root_id, mime_type=mime_pre_filter
    )

    # case-insensitive substring у Drive API не строго consistent —
    # додатково фільтруємо локально
    q_lower = query.lower()
    raw_results = [r for r in raw_results if q_lower in r.get("name", "").lower()]

    if not raw_results:
        raise ValueError(
            f"Нічого не знайдено для query='{query}' у Worqen Drive. "
            f"Спробуй worqen_ws_list_all з більшим max_depth щоб побачити дерево."
        )

    # Нормалізуємо всі результати
    normalized_all = [
        _normalize_item(r, parent_id="", parent_name=None) for r in raw_results
    ]

    # Якщо є kind_filter — фільтруємо
    if kind_filter:
        matched = [n for n in normalized_all if n["kind"] in kind_filter]
        if not matched:
            raise ValueError(
                _format_wrong_kind_error(query, normalized_all, kind_filter)
            )
        normalized_all = matched

    if len(normalized_all) > 1:
        previews = []
        for n in normalized_all[:5]:
            path = build_path_for_file(n["id"], root_id, root_name) or "?"
            previews.append(f"{n['name']} [{path}] (id: {n['id'][:12]}...)")
        more = f", ...{len(normalized_all) - 5} more" if len(normalized_all) > 5 else ""
        raise ValueError(
            f"Query '{query}' матчить {len(normalized_all)} елементів. "
            f"Уточни запит. Кандидати: {'; '.join(previews)}{more}"
        )

    # Єдиний матч — додаємо path
    found = normalized_all[0]
    path = build_path_for_file(found["id"], root_id, root_name)
    if path:
        found["path"] = path
    found["depth"] = path.count(" > ") if path else 0
    return found


def resolve(
    query: str,
    candidates: Optional[list[dict]] = None,
    kind_filter: Optional[tuple[str, ...]] = None,
) -> dict:
    """
    Знаходить файл/папку за query.

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
    q = query.strip()
    if not q:
        raise ValueError("query не може бути порожнім")

    # Шлях 1: пошук у наданому списку
    if candidates is not None:
        if _looks_like_drive_id(q):
            for c in candidates:
                if c["id"] == q:
                    return c

        q_lower = q.lower()
        matches = [c for c in candidates if q_lower in c["name"].lower()]

        if not matches:
            raise ValueError(
                f"Нічого не знайдено для query='{query}' у Worqen воркспейсі. "
                f"Спробуй worqen_ws_list_all щоб побачити доступні назви."
            )

        if len(matches) > 1:
            names = [
                f"{m['name']} [{m.get('path', '?')}] (id: {m['id'][:12]}...)"
                for m in matches[:5]
            ]
            more = f", ...{len(matches) - 5} more" if len(matches) > 5 else ""
            raise ValueError(
                f"Query '{query}' матчить {len(matches)} елементів. "
                f"Уточни запит. Кандидати: {'; '.join(names)}{more}"
            )

        return matches[0]

    # Шлях 2 і 3: нативний Drive search (з kind_filter або без).
    return _resolve_via_drive_search(q, kind_filter=kind_filter)


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

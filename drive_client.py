"""
Обгортка над Google Drive API.
- TTL-кеш (30с)
- download_file (з опційним fmt='gdoc' для Google Docs export)
- is_drive_newer — перевірка чи Drive має свіжіший файл ніж кеш
"""

import io
import time
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from shared.auth import get_credentials
from config import CACHE_TTL_SECONDS


# MIME для експорту Google Docs у docx-байти
_GDOC_EXPORT_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


# Кеш: (file_id, fmt) -> (content_bytes, timestamp, drive_modified_time)
_cache: dict[tuple[str, str], tuple[bytes, float, Optional[str]]] = {}


def _get_service():
    creds = get_credentials()
    return build("drive", "v3", credentials=creds)


def get_file_metadata(file_id: str) -> dict:
    service = _get_service()
    return (
        service.files()
        .get(
            fileId=file_id,
            fields="id, name, mimeType, modifiedTime",
            supportsAllDrives=True,
        )
        .execute()
    )


def download_file(
    file_id: str,
    fmt: str = "docx",
    force_refresh: bool = False,
) -> bytes:
    """
    Скачує файл з Drive. Кеш TTL 30с.

    fmt:
        'docx' / 'xlsx' / будь-яке інше — нативний download через get_media()
        'gdoc' — експорт Google Docs у docx-байти через export_media()
    """
    now = time.time()
    cache_key = (file_id, fmt)

    if not force_refresh and cache_key in _cache:
        content, cached_at, _ = _cache[cache_key]
        if now - cached_at < CACHE_TTL_SECONDS:
            return content

    service = _get_service()

    # Беремо метадані щоб зберегти modifiedTime у кеші
    meta = get_file_metadata(file_id)
    drive_modified = meta.get("modifiedTime")

    if fmt == "gdoc":
        # Експорт Google Docs у docx-байти
        request = service.files().export_media(
            fileId=file_id,
            mimeType=_GDOC_EXPORT_MIME,
        )
    else:
        # Нативний download (docx, xlsx, інше)
        request = service.files().get_media(
            fileId=file_id,
            supportsAllDrives=True,
        )

    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    content = buffer.getvalue()
    _cache[cache_key] = (content, now, drive_modified)
    return content


def clear_cache(file_id: Optional[str] = None):
    """
    Скидає кеш. Якщо file_id вказано — скидає всі формати для цього id.
    """
    if file_id:
        keys_to_drop = [k for k in _cache if k[0] == file_id]
        for k in keys_to_drop:
            _cache.pop(k, None)
    else:
        _cache.clear()


def is_drive_newer(file_id: str) -> dict:
    """
    Перевіряє чи Drive має свіжіший файл ніж у кеші.
    Корисно для діагностики синхронізації.
    Повертає інформацію по будь-якому формату цього file_id який є у кеші.
    """
    # Шукаємо будь-який запис у кеші для цього file_id
    matching = [(k, v) for k, v in _cache.items() if k[0] == file_id]
    if not matching:
        return {"in_cache": False, "drive_newer": True}

    # Беремо найсвіжіший з кешованих варіантів
    matching.sort(key=lambda kv: kv[1][1], reverse=True)
    cache_key, (_content, cached_at, cached_modified) = matching[0]

    try:
        meta = get_file_metadata(file_id)
        drive_modified = meta.get("modifiedTime")
        return {
            "in_cache": True,
            "fmt": cache_key[1],
            "cached_drive_modified": cached_modified,
            "current_drive_modified": drive_modified,
            "drive_newer": drive_modified != cached_modified,
            "cache_age_seconds": round(time.time() - cached_at, 1),
        }
    except Exception as e:
        return {"in_cache": True, "error": str(e)}


# ====================== FOLDER LISTING ======================
#
# Для папки "Обговорення з командою" (ітерація 2): список файлів
# з підпапками-сесіями за датами.

# Кеш списків папок: folder_id -> (children_list, timestamp)
_folder_cache: dict[str, tuple[list[dict], float]] = {}


def _list_folder_children(
    folder_id: str,
    only_mime: Optional[str] = None,
) -> list[dict]:
    """
    Повертає всіх дітей папки (файли і підпапки) одним списком.
    Кеш TTL 30с.

    only_mime: якщо вказано — фільтр по mimeType.
    """
    now = time.time()

    cache_key = f"{folder_id}::{only_mime or '*'}"
    cached = _folder_cache.get(cache_key)
    if cached and now - cached[1] < CACHE_TTL_SECONDS:
        return cached[0]

    service = _get_service()

    q_parts = [f"'{folder_id}' in parents", "trashed = false"]
    if only_mime:
        q_parts.append(f"mimeType = '{only_mime}'")
    q = " and ".join(q_parts)

    items: list[dict] = []
    page_token: Optional[str] = None
    while True:
        resp = (
            service.files()
            .list(
                q=q,
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, size, parents)",
                pageSize=200,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        items.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    _folder_cache[cache_key] = (items, now)
    return items


def list_docs_in_folder_recursive(folder_id: str) -> list[dict]:
    """
    Повертає всі Google Docs всередині folder_id, включно з тими що
    лежать у підпапках першого рівня.

    Кожен елемент:
        {
            "id": str,
            "name": str,
            "mime": str,
            "modified": str,
            "size_bytes": int | None,
            "parent_folder_id": str,
            "parent_folder_name": str | None,  # None для файлів у корені
        }

    Підпапки другого і нижчих рівнів НЕ обходимо (структура простa: корінь + дати).
    """
    GDOC_MIME = "application/vnd.google-apps.document"
    FOLDER_MIME = "application/vnd.google-apps.folder"

    # 1. Беремо все з кореневої папки
    root_children = _list_folder_children(folder_id)

    result: list[dict] = []
    subfolders: list[dict] = []

    for item in root_children:
        if item["mimeType"] == GDOC_MIME:
            result.append({
                "id": item["id"],
                "name": item["name"],
                "mime": item["mimeType"],
                "modified": item.get("modifiedTime"),
                "size_bytes": int(item["size"]) if item.get("size") else None,
                "parent_folder_id": folder_id,
                "parent_folder_name": None,
            })
        elif item["mimeType"] == FOLDER_MIME:
            subfolders.append(item)

    # 2. Йдемо по підпапках першого рівня
    for sub in subfolders:
        sub_id = sub["id"]
        sub_name = sub["name"]
        sub_children = _list_folder_children(sub_id, only_mime=GDOC_MIME)
        for item in sub_children:
            result.append({
                "id": item["id"],
                "name": item["name"],
                "mime": item["mimeType"],
                "modified": item.get("modifiedTime"),
                "size_bytes": int(item["size"]) if item.get("size") else None,
                "parent_folder_id": sub_id,
                "parent_folder_name": sub_name,
            })

    return result


def clear_folder_cache(folder_id: Optional[str] = None):
    """Скидає кеш списків папок."""
    if folder_id:
        keys_to_drop = [k for k in _folder_cache if k.startswith(f"{folder_id}::")]
        for k in keys_to_drop:
            _folder_cache.pop(k, None)
    else:
        _folder_cache.clear()


# ====================== WRITE OPERATIONS ======================


def upload_file_content(
    file_id: str,
    content_bytes: bytes,
    mime_type: str,
) -> dict:
    """
    Заливає байти назад у Drive через files().update() з media_body.
    Після успіху скидає кеш для цього file_id (всі формати).

    Повертає метадані оновленого файлу (id, name, modifiedTime).
    """
    from googleapiclient.http import MediaIoBaseUpload

    service = _get_service()

    media = MediaIoBaseUpload(
        io.BytesIO(content_bytes),
        mimetype=mime_type,
        resumable=False,
    )

    updated = (
        service.files()
        .update(
            fileId=file_id,
            media_body=media,
            fields="id, name, modifiedTime",
            supportsAllDrives=True,
        )
        .execute()
    )

    clear_cache(file_id)
    return updated


def fetch_current_drive_modified(file_id: str) -> Optional[str]:
    """
    Повертає поточний modifiedTime з Drive (без кешу).
    Використовується writer'ами для перевірки чи Drive не змінився
    між початком операції і записом.
    """
    try:
        meta = get_file_metadata(file_id)
        return meta.get("modifiedTime")
    except Exception:
        return None

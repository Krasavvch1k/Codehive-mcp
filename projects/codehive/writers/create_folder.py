"""codehive_create_folder — створення нової папки у CodeHive Agency Drive.

Робить:
1. Resolve parent_folder → folder_id, folder_name (default = root).
2. Blacklist check (через writers.safety).
3. Duplicate name check (свіжий Drive query, обходить TTL кеш).
4. files().create(mimeType=folder).
5. Log у writes_log.
"""

import logging
from typing import Any, Optional

from googleapiclient.errors import HttpError

from projects.codehive.config import (
    CODEHIVE_ROOT_FOLDER_ID,
    GOOGLE_FOLDER_MIME,
)
from projects.codehive.gdoc_reader import _get_folder_name, resolve_doc
from projects.codehive.writers.safety import SafetyError, check_write_allowed
from shared.drive_client import get_service as get_drive_service
from shared.writes_log import log_doc_write

logger = logging.getLogger(__name__)


def _check_duplicate_folder_name(parent_id: str, name: str) -> Optional[dict]:
    """Перевіряє чи у вказаному parent уже є папка з такою точною назвою.

    Звертається ПРЯМО до Drive API (без TTL-кешу).

    Returns:
        dict {id, name, modified} якщо знайдено дублікат, або None.
    """
    drive_service = get_drive_service()
    name_escaped = name.strip().replace("\\", "\\\\").replace("'", "\\'")
    query = (
        f"name = '{name_escaped}' "
        f"and '{parent_id}' in parents "
        f"and mimeType = '{GOOGLE_FOLDER_MIME}' "
        f"and trashed = false"
    )
    try:
        resp = (
            drive_service.files()
            .list(
                q=query,
                fields="files(id, name, modifiedTime)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageSize=10,
            )
            .execute()
        )
    except HttpError:
        return None

    files = resp.get("files", [])
    if not files:
        return None
    f = files[0]
    return {
        "id": f["id"],
        "name": f.get("name", name),
        "modified": f.get("modifiedTime"),
    }


def _resolve_parent(parent_folder: Optional[str]) -> tuple[str, str]:
    """Резолвить parent_folder до (folder_id, folder_name).

    None / пусто → корінь CodeHive Agency.
    Інакше → resolve_doc(kind_filter=("folder",)).
    """
    if not parent_folder:
        if not CODEHIVE_ROOT_FOLDER_ID:
            raise ValueError(
                "CODEHIVE_ROOT_FOLDER_ID is not set in .env."
            )
        root_id = CODEHIVE_ROOT_FOLDER_ID
        root_name = _get_folder_name(root_id) or "CodeHive Agency"
        return root_id, root_name

    folder_meta = resolve_doc(parent_folder, kind_filter=("folder",))
    return folder_meta["id"], folder_meta["name"]


def create_folder(
    name: str,
    parent_folder: Optional[str] = None,
    allow_duplicate: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Створює нову папку у CodeHive Agency Drive.

    Args:
        name: назва нової папки.
        parent_folder: Drive ID або substring назви parent-папки.
            Default — корінь CodeHive Agency Drive.
        allow_duplicate: дозволити створення коли вже є папка з такою назвою.
        dry_run: preview без створення.

    Returns:
        dict з ok / error / preview.
    """
    # 1. Validate
    name_clean = (name or "").strip()
    if not name_clean:
        return {"error": "name cannot be empty"}

    # 2. Resolve parent
    try:
        folder_id, folder_name = _resolve_parent(parent_folder)
    except ValueError as e:
        return {"error": f"Parent folder not found: {e}"}

    # 3. Dry run preview
    if dry_run:
        return {
            "operation": "create_folder",
            "name": name_clean,
            "parent_folder_id": folder_id,
            "parent_folder_name": folder_name,
            "allow_duplicate": allow_duplicate,
            "would_create": True,
            "dry_run": True,
        }

    # 4. Blacklist check (target = new folder у цьому parent)
    try:
        check_write_allowed(
            file_id="<new>",
            file_name=name_clean,
            parent_folder_ids=[folder_id],
        )
    except SafetyError as e:
        return {"error": f"SafetyError: {e}"}

    # 5. Duplicate name check
    if not allow_duplicate:
        dup = _check_duplicate_folder_name(folder_id, name_clean)
        if dup:
            return {
                "error": (
                    f"Folder '{name_clean}' already exists in '{folder_name}'. "
                    f"Existing: id={dup['id'][:12]}..., modified={dup.get('modified')}. "
                    f"Pass allow_duplicate=true to create anyway."
                ),
                "parent_folder_id": folder_id,
                "parent_folder_name": folder_name,
                "existing_folder_id": dup["id"],
            }

    # 6. Create
    drive_service = get_drive_service()
    try:
        new_folder = (
            drive_service.files()
            .create(
                body={
                    "name": name_clean,
                    "mimeType": GOOGLE_FOLDER_MIME,
                    "parents": [folder_id],
                },
                fields="id, name, mimeType, parents, webViewLink, modifiedTime",
                supportsAllDrives=True,
            )
            .execute()
        )
    except HttpError as e:
        return {"error": f"Drive create failed: {e}"}

    new_folder_id = new_folder["id"]
    web_view_link = new_folder.get("webViewLink") or (
        f"https://drive.google.com/drive/folders/{new_folder_id}"
    )

    # 7. Log
    try:
        log_doc_write(
            project="codehive",
            tool="create_folder",
            file_id=new_folder_id,
            file_name=name_clean,
            payload={
                "parent_folder_id": folder_id,
                "parent_folder_name": folder_name,
                "modified_after": new_folder.get("modifiedTime"),
            },
        )
    except Exception as e:
        logger.warning("writes_log failed for create_folder: %s", e)

    return {
        "ok": True,
        "folder_id": new_folder_id,
        "folder_name": name_clean,
        "parent_folder_id": folder_id,
        "parent_folder_name": folder_name,
        "url": web_view_link,
        "modified": new_folder.get("modifiedTime"),
    }

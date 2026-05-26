"""codehive_replace_text — codehive-specific обгортка над shared.doc_writers.replace_text_in_doc.

Робить:
1. Resolve query → file_id, file_name (native Drive search, gdoc only).
2. Blacklist check (codehive WRITE_BLACKLIST_*).
3. Виклик shared.doc_writers.replace_text_in_doc з готовими параметрами.

Core логіка (occurrence counting, batch_update, optimistic locking, logging)
живе у shared.doc_writers і не дублюється тут.
"""

from typing import Any

from googleapiclient.errors import HttpError

from projects.codehive.gdoc_reader import resolve_doc
from projects.codehive.writers.safety import SafetyError, check_write_allowed
from shared.doc_writers import replace_text_in_doc
from shared.drive_client import get_service as get_drive_service


def _get_parent_folders(file_id: str) -> list[str]:
    """Отримує список parent folder IDs через Drive API."""
    service = get_drive_service()
    meta = (
        service.files()
        .get(fileId=file_id, fields="parents", supportsAllDrives=True)
        .execute()
    )
    return meta.get("parents", [])


def replace_text(query: str, old_text: str, new_text: str) -> dict[str, Any]:
    """
    Замінити рівно ОДНЕ входження old_text на new_text у gdoc CodeHive Agency.

    Args:
        query: повний Drive ID або substring назви документа.
        old_text: текст для пошуку (case-sensitive).
        new_text: чим замінити.

    Returns:
        dict з ok / error.
    """
    # 1. Resolve query → file_id, file_name (native Drive search, depth-independent)
    try:
        doc_meta = resolve_doc(query, kind_filter=("gdoc",))
    except ValueError as e:
        return {"error": str(e)}

    file_id = doc_meta["id"]
    file_name = doc_meta["name"]

    # 2. Blacklist check
    try:
        parent_ids = _get_parent_folders(file_id)
        check_write_allowed(file_id, file_name, parent_ids)
    except SafetyError as e:
        return {"error": f"SafetyError: {e}"}
    except HttpError as e:
        return {"error": f"Не вдалось отримати parents: {e}"}

    # 3. Виклик shared core logic
    return replace_text_in_doc(
        file_id=file_id,
        file_name=file_name,
        old_text=old_text,
        new_text=new_text,
        project="codehive",
    )

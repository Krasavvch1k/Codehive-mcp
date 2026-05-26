"""codehive_insert_text — codehive-specific обгортка над shared.doc_writers.insert_text_in_doc.

Робить:
1. Resolve query → file_id, file_name.
2. Blacklist check.
3. Виклик shared.doc_writers.insert_text_in_doc.

Core логіка (mode handling, anchor search, Docs API index offset, batch_update,
optimistic locking, logging) живе у shared.doc_writers.
"""

from typing import Any

from googleapiclient.errors import HttpError

from projects.codehive.gdoc_reader import resolve_doc
from projects.codehive.writers.safety import SafetyError, check_write_allowed
from shared.doc_writers import insert_text_in_doc
from shared.drive_client import get_service as get_drive_service


def _get_parent_folders(file_id: str) -> list[str]:
    service = get_drive_service()
    meta = (
        service.files()
        .get(fileId=file_id, fields="parents", supportsAllDrives=True)
        .execute()
    )
    return meta.get("parents", [])


def insert_text(
    query: str,
    text: str,
    mode: str,
    anchor: str | None = None,
    as_paragraph: bool = False,
) -> dict[str, Any]:
    """
    Вставка тексту у gdoc CodeHive Agency.

    Args:
        query: повний Drive ID або substring назви документа.
        text: що вставляти.
        mode: "after" | "before" | "end_of_doc".
        anchor: для after/before — substring (case-sensitive, unique).
        as_paragraph: обгортати text у переноси рядків.

    Returns:
        dict з ok / error.
    """
    # 1. Resolve query (native Drive search, depth-independent)
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

    # 3. Виклик shared
    return insert_text_in_doc(
        file_id=file_id,
        file_name=file_name,
        text=text,
        mode=mode,
        anchor=anchor,
        as_paragraph=as_paragraph,
        project="codehive",
    )

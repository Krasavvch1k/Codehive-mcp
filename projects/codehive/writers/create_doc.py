"""codehive_create_doc — codehive-specific обгортка над shared.doc_writers.create_doc_in_folder.

Робить:
1. Resolve folder_query → folder_id, folder_name.
2. Blacklist check (через writers.safety).
3. Duplicate name check (свіжий Drive query, обходить TTL кеш).
4. Виклик shared.doc_writers.create_doc_in_folder.

Core логіка (drive.files().create + optional initial_content + logging)
живе у shared.doc_writers.
"""

from typing import Any

from googleapiclient.errors import HttpError

from projects.codehive.gdoc_reader import resolve_doc
from projects.codehive.config import GOOGLE_DOC_MIME
from projects.codehive.writers.safety import SafetyError, check_write_allowed
from shared.doc_writers import create_doc_in_folder
from shared.drive_client import get_service as get_drive_service


def _check_duplicate_name(folder_id: str, name: str) -> dict | None:
    """Перевіряє чи у вказаній папці вже є gdoc з такою точно назвою.

    Звертається ПРЯМО до Drive API (без TTL-кешу), бо щойно створені файли
    у кешованому list_all_docs не з'являтимуться до закінчення TTL.

    Returns:
        dict {id, name, modified} якщо знайдено дублікат, або None.
    """
    drive_service = get_drive_service()
    name_escaped = name.strip().replace("\\", "\\\\").replace("'", "\\'")
    query = (
        f"name = '{name_escaped}' "
        f"and '{folder_id}' in parents "
        f"and mimeType = '{GOOGLE_DOC_MIME}' "
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


def create_doc(
    name: str,
    folder_query: str,
    initial_content: str = "",
) -> dict[str, Any]:
    """
    Створює новий gdoc у вказаній папці CodeHive Agency.

    Args:
        name: назва нового документа.
        folder_query: повний Drive ID папки або substring назви.
        initial_content: опційно, plain text для тіла.

    Returns:
        dict з ok / error.
    """
    # 1. Validate
    name_clean = (name or "").strip()
    if not name_clean:
        return {"error": "name не може бути порожнім"}
    if not folder_query:
        return {"error": "folder_query не може бути порожнім"}

    # 2. Resolve folder_query (depth-independent native Drive search)
    try:
        folder_meta = resolve_doc(folder_query, kind_filter=("folder",))
    except ValueError as e:
        return {"error": f"Папка не знайдена: {e}"}

    folder_id = folder_meta["id"]
    folder_name = folder_meta["name"]

    # 3. Blacklist check (target = new doc у цій папці)
    try:
        check_write_allowed(
            file_id="<new>",
            file_name=name_clean,
            parent_folder_ids=[folder_id],
        )
    except SafetyError as e:
        return {"error": f"SafetyError: {e}"}

    # 4. Duplicate name check (свіжий Drive query)
    dup = _check_duplicate_name(folder_id, name_clean)
    if dup:
        return {
            "error": (
                f"У папці '{folder_name}' вже існує gdoc з назвою '{name_clean}'. "
                f"Існуючий: id={dup['id'][:12]}..., modified={dup.get('modified')}. "
                f"Якщо потрібно створити дублікат — змінити назву (наприклад, додати '(2)')."
            ),
            "folder_id": folder_id,
            "folder_name": folder_name,
            "existing_file_id": dup["id"],
        }

    # 5. Виклик shared
    return create_doc_in_folder(
        folder_id=folder_id,
        folder_name=folder_name,
        name=name_clean,
        initial_content=initial_content,
        project="codehive",
    )

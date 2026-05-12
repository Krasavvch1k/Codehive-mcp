"""codehive_create_doc — handler.

Створює новий Google Doc у вказаній папці CodeHive Agency.

Логіка:
1. Resolve folder_query → folder_id, folder_name (через resolve_doc з фільтром на folders).
2. Перевірка blacklist через safety.check_write_allowed (target = нова дока у цій папці).
3. Перевірка дублікатів — error якщо у тій самій папці вже є gdoc з такою точно назвою.
4. drive.files().create(mimeType=document, parents=[folder_id]).
5. Якщо initial_content передано — docs.batchUpdate з insertText у endOfSegmentLocation.
6. Лог через log_doc_write.
7. Response з file_id, url, folder info.

Confirm-flow живе у чаті (як у replace_text / insert_text).
"""

import logging
from typing import Any

from googleapiclient.errors import HttpError

from projects.codehive.gdoc_reader import list_all_docs, resolve_doc
from projects.codehive.config import CODEHIVE_MAX_RECURSION_DEPTH, GOOGLE_DOC_MIME
from projects.codehive.writers.safety import SafetyError, check_write_allowed
from shared.docs_client import batch_update
from shared.drive_client import get_service as get_drive_service
from shared.writes_log import log_doc_write

logger = logging.getLogger(__name__)


def _check_duplicate_name(folder_id: str, name: str) -> dict | None:
    """Перевіряє чи у вказаній папці вже є gdoc з такою точно назвою.

    Звертається ПРЯМО до Drive API (без TTL-кешу), бо щойно створені файли
    у кешованому list_all_docs не з'являтимуться до закінчення TTL.

    Returns:
        dict {id, name, modified} якщо знайдено дублікат, або None якщо вільно.
    """
    drive_service = get_drive_service()
    # Escape одинарних лапок у назві щоб не зламати q-вираз
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
        # Якщо запит зламався — не блокуємо створення, тільки попередимо.
        # Це trade-off: краще створити можливий дублікат ніж сфейлити happy path.
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
    Створює новий gdoc у вказаній папці.

    Args:
        name: назва нового документа.
        folder_query: повний Drive ID папки або substring назви.
        initial_content: опційно, plain text для тіла. За замовчуванням порожній док.

    Returns:
        dict з ok / error.
    """
    # --- 1. Validate inputs ---
    name_clean = (name or "").strip()
    if not name_clean:
        return {"error": "name не може бути порожнім"}

    if not folder_query:
        return {"error": "folder_query не може бути порожнім"}

    # --- 2. Resolve folder_query → папка ---
    try:
        all_data = list_all_docs(max_depth=CODEHIVE_MAX_RECURSION_DEPTH)
        folders = [d for d in all_data["items"] if d["kind"] == "folder"]
        folder_meta = resolve_doc(folder_query, folders)
    except ValueError as e:
        return {"error": f"Папка не знайдена: {e}"}

    folder_id = folder_meta["id"]
    folder_name = folder_meta["name"]

    # --- 3. Blacklist check ---
    # Target = нова дока, file_id ще не існує. Передаємо placeholder для file_id,
    # blacklist по file_id точно не спрацює (нова дока). Перевіряємо тільки по
    # name substring і parent folder.
    try:
        check_write_allowed(
            file_id="<new>",
            file_name=name_clean,
            parent_folder_ids=[folder_id],
        )
    except SafetyError as e:
        return {"error": f"SafetyError: {e}"}

    # --- 4. Перевірка дублікатів у тій самій папці ---
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

    # --- 5. drive.files().create ---
    drive_service = get_drive_service()
    try:
        new_doc = (
            drive_service.files()
            .create(
                body={
                    "name": name_clean,
                    "mimeType": GOOGLE_DOC_MIME,
                    "parents": [folder_id],
                },
                fields="id, name, mimeType, parents, webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
    except HttpError as e:
        return {"error": f"Drive create failed: {e}"}

    file_id = new_doc["id"]
    web_view_link = new_doc.get("webViewLink") or (
        f"https://docs.google.com/document/d/{file_id}/edit"
    )

    # --- 6. Якщо initial_content — batchUpdate з insertText ---
    inserted_chars = 0
    if initial_content:
        requests = [
            {
                "insertText": {
                    "endOfSegmentLocation": {},
                    "text": initial_content,
                }
            }
        ]
        try:
            # У свіжоствореного документа є revisionId, але ми його не отримували.
            # Для першого write на порожньому документі revision lock не критичний —
            # ніхто інший не міг його зачепити за мілісекунди між create і insert.
            batch_update(file_id, requests, required_revision_id=None)
            inserted_chars = len(initial_content)
        except HttpError as e:
            # Документ створений, але контент не залився. Повертаємо partial success.
            return {
                "ok": True,
                "warning": (
                    f"Документ створений, але initial_content не залився: {e}. "
                    f"Спробуй codehive_insert_text(mode='end_of_doc')."
                ),
                "file_id": file_id,
                "file_name": name_clean,
                "folder_id": folder_id,
                "folder_name": folder_name,
                "url": web_view_link,
                "inserted_chars": 0,
            }

    # --- 7. Log ---
    try:
        log_doc_write(
            project="codehive",
            tool="create_doc",
            file_id=file_id,
            file_name=name_clean,
            payload={
                "folder_id": folder_id,
                "folder_name": folder_name,
                "initial_content_length": len(initial_content),
                "inserted_chars": inserted_chars,
            },
        )
    except Exception as e:
        logger.warning("writes_log failed for codehive.create_doc: %s", e)

    # --- 8. Response ---
    return {
        "ok": True,
        "file_id": file_id,
        "file_name": name_clean,
        "folder_id": folder_id,
        "folder_name": folder_name,
        "url": web_view_link,
        "inserted_chars": inserted_chars,
    }

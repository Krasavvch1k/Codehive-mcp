"""Generic write handlers для Google Docs.

Низькорівневі функції — приймають уже resolved file_id / folder_id і виконують
саме операцію через Docs/Drive API + логування. НЕ роблять:
- resolve query → file_id (це project-specific, у проєктних обгортках)
- safety check (whitelist/blacklist policy теж project-specific)
- duplicate check для create (теж project-specific)

Проєктні обгортки повинні зробити resolve + safety ДО виклику, передати готові
file_id/file_name/folder_id/folder_name.

Logging — спільний через shared.writes_log.log_doc_write, з параметром project.
"""

import logging
from typing import Any

from googleapiclient.errors import HttpError

from shared.docs_client import batch_update, extract_plain_text, get_document
from shared.drive_client import get_service as get_drive_service
from shared.writes_log import log_doc_write

logger = logging.getLogger(__name__)


CONTEXT_RADIUS = 30  # символів зліва/справа для error-контексту
VALID_INSERT_MODES = ("after", "before", "end_of_doc")

# Google Doc MIME — локальна generic константа (можна винести у shared/config.py пізніше).
_GOOGLE_DOC_MIME = "application/vnd.google-apps.document"


# ----- helpers -----

def _find_all_occurrences(text: str, needle: str) -> list[int]:
    """Повертає список індексів усіх входжень needle у text (case-sensitive)."""
    if not needle:
        return []
    indices: list[int] = []
    start = 0
    while True:
        i = text.find(needle, start)
        if i == -1:
            break
        indices.append(i)
        start = i + 1
    return indices


def _format_contexts(text: str, indices: list[int], needle: str) -> list[str]:
    """Контекст ±CONTEXT_RADIUS символів навколо кожного occurrence."""
    contexts: list[str] = []
    n = len(needle)
    for i in indices:
        left = text[max(0, i - CONTEXT_RADIUS) : i]
        right = text[i + n : i + n + CONTEXT_RADIUS]
        left_clean = " ".join(left.split())
        right_clean = " ".join(right.split())
        contexts.append(f"...{left_clean} [{needle}] {right_clean}...")
    return contexts


def _wrap_as_paragraph(text: str, mode: str) -> str:
    """Обгортає text у переноси рядків залежно від режиму вставки.

    - after/before: \\n...\\n — окремий блок між сусідніми абзацами
    - end_of_doc: \\n... — новий рядок після останнього блоку

    Якщо text вже починається/закінчується \\n — не дублюємо.
    """
    prefix = "" if text.startswith("\n") else "\n"
    suffix = "" if text.endswith("\n") else "\n"

    if mode == "end_of_doc":
        return prefix + text
    return prefix + text + suffix


# ----- public API -----

def replace_text_in_doc(
    file_id: str,
    file_name: str,
    old_text: str,
    new_text: str,
    project: str,
) -> dict[str, Any]:
    """
    Замінити рівно ОДНЕ входження old_text на new_text у gdoc.

    Caller відповідає за resolve query → file_id і safety check ДО виклику.

    Args:
        file_id: Drive ID документа.
        file_name: назва (для логу і error messages).
        old_text: текст для пошуку (case-sensitive).
        new_text: чим замінити.
        project: "codehive" / "worqen" — для логу.

    Returns:
        dict з ok / error.
    """
    if not old_text:
        return {"error": "old_text не може бути порожнім"}

    if old_text == new_text:
        return {"error": "old_text == new_text, нічого замінювати"}

    # Read document
    try:
        doc = get_document(file_id)
    except HttpError as e:
        return {"error": f"Не вдалось прочитати документ: {e}"}

    revision_before = doc.get("revisionId")
    plain_text = extract_plain_text(doc)

    # Count occurrences
    indices = _find_all_occurrences(plain_text, old_text)
    count = len(indices)

    if count == 0:
        return {
            "error": (
                f"Текст '{old_text}' не знайдено у документі '{file_name}'. "
                f"Перевір регістр (search case-sensitive) і пробіли."
            ),
            "file_id": file_id,
            "file_name": file_name,
        }

    if count > 1:
        contexts = _format_contexts(plain_text, indices, old_text)
        return {
            "error": (
                f"Знайдено {count} входжень '{old_text}' у '{file_name}'. "
                f"replace_text заміняє тільки якщо рівно 1 входження. "
                f"Зроби old_text більш специфічним (додай контекст з боків)."
            ),
            "file_id": file_id,
            "file_name": file_name,
            "occurrences": count,
            "contexts": contexts[:10],
        }

    # Write
    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": old_text, "matchCase": True},
                "replaceText": new_text,
            }
        }
    ]

    try:
        response = batch_update(
            file_id, requests, required_revision_id=revision_before
        )
    except HttpError as e:
        return {
            "error": f"batchUpdate failed: {e}",
            "file_id": file_id,
            "file_name": file_name,
            "hint": (
                "Можливо документ змінився між читанням і записом. Спробуй ще раз."
            ),
        }

    revision_after = (
        response.get("writeControl", {}).get("requiredRevisionId") or "unknown"
    )

    replies = response.get("replies", [])
    occurrences_changed = (
        replies[0].get("replaceAllText", {}).get("occurrencesChanged", 0)
        if replies
        else 0
    )

    # Log
    try:
        log_doc_write(
            project=project,
            tool="replace_text",
            file_id=file_id,
            file_name=file_name,
            payload={
                "old_text": old_text,
                "new_text": new_text,
                "revision_before": revision_before,
                "revision_after": revision_after,
                "occurrences_changed": occurrences_changed,
            },
        )
    except Exception as e:
        logger.warning("writes_log failed for %s.replace_text: %s", project, e)

    return {
        "ok": True,
        "file_id": file_id,
        "file_name": file_name,
        "revision_before": revision_before,
        "revision_after": revision_after,
        "replaced": occurrences_changed,
    }


def insert_text_in_doc(
    file_id: str,
    file_name: str,
    text: str,
    mode: str,
    anchor: str | None,
    as_paragraph: bool,
    project: str,
) -> dict[str, Any]:
    """
    Вставка тексту у gdoc у режимі after/before/end_of_doc.

    Caller відповідає за resolve query → file_id і safety check ДО виклику.

    Args:
        file_id: Drive ID документа.
        file_name: назва (для логу і error messages).
        text: що вставляти.
        mode: "after" | "before" | "end_of_doc".
        anchor: для after/before — substring (case-sensitive, unique). Для
            end_of_doc — має бути None або порожній.
        as_paragraph: якщо True — обгортає text у переноси рядків.
        project: "codehive" / "worqen" — для логу.

    Returns:
        dict з ok / error.
    """
    # Validate
    if mode not in VALID_INSERT_MODES:
        return {
            "error": f"mode має бути одним з {VALID_INSERT_MODES}, отримано: '{mode}'"
        }

    if not text:
        return {"error": "text не може бути порожнім"}

    if mode in ("after", "before"):
        if not anchor:
            return {"error": f"для mode='{mode}' потрібен anchor"}
    else:  # end_of_doc
        if anchor:
            return {
                "error": (
                    "для mode='end_of_doc' anchor має бути None або порожнім; "
                    "якщо треба вставити після конкретного тексту — використовуй mode='after'"
                )
            }

    # Read document
    try:
        doc = get_document(file_id)
    except HttpError as e:
        return {"error": f"Не вдалось прочитати документ: {e}"}

    revision_before = doc.get("revisionId")
    plain_text = extract_plain_text(doc)

    final_text = _wrap_as_paragraph(text, mode) if as_paragraph else text
    inserted_at_index: int | None = None

    # Build request
    if mode == "end_of_doc":
        request = {
            "insertText": {
                "endOfSegmentLocation": {},
                "text": final_text,
            }
        }
    else:
        indices = _find_all_occurrences(plain_text, anchor)
        count = len(indices)

        if count == 0:
            return {
                "error": (
                    f"Anchor '{anchor}' не знайдено у '{file_name}'. "
                    f"Перевір регістр (case-sensitive) і пробіли."
                ),
                "file_id": file_id,
                "file_name": file_name,
            }

        if count > 1:
            contexts = _format_contexts(plain_text, indices, anchor)
            return {
                "error": (
                    f"Знайдено {count} входжень '{anchor}' у '{file_name}'. "
                    f"insert_text вимагає рівно 1 входження. "
                    f"Зроби anchor більш специфічним."
                ),
                "file_id": file_id,
                "file_name": file_name,
                "occurrences": count,
                "contexts": contexts[:10],
            }

        anchor_pos = indices[0]
        if mode == "after":
            insert_pos = anchor_pos + len(anchor)
        else:  # before
            insert_pos = anchor_pos

        # +1 — корекція на Docs API offset (body починається з index=1, не 0)
        docs_api_index = insert_pos + 1
        inserted_at_index = docs_api_index

        request = {
            "insertText": {
                "location": {"index": docs_api_index},
                "text": final_text,
            }
        }

    # Write
    try:
        response = batch_update(
            file_id, [request], required_revision_id=revision_before
        )
    except HttpError as e:
        return {
            "error": f"batchUpdate failed: {e}",
            "file_id": file_id,
            "file_name": file_name,
            "hint": (
                "Можливо документ змінився між читанням і записом. Спробуй ще раз."
            ),
        }

    revision_after = (
        response.get("writeControl", {}).get("requiredRevisionId") or "unknown"
    )

    # Log
    try:
        log_doc_write(
            project=project,
            tool="insert_text",
            file_id=file_id,
            file_name=file_name,
            payload={
                "mode": mode,
                "anchor": anchor,
                "text": final_text,
                "as_paragraph": as_paragraph,
                "inserted_at_index": inserted_at_index,
                "revision_before": revision_before,
                "revision_after": revision_after,
            },
        )
    except Exception as e:
        logger.warning("writes_log failed for %s.insert_text: %s", project, e)

    return {
        "ok": True,
        "file_id": file_id,
        "file_name": file_name,
        "mode": mode,
        "inserted_at_index": inserted_at_index,
        "revision_before": revision_before,
        "revision_after": revision_after,
    }


def create_doc_in_folder(
    folder_id: str,
    folder_name: str,
    name: str,
    initial_content: str,
    project: str,
) -> dict[str, Any]:
    """
    Створює новий gdoc у вказаній папці.

    Caller відповідає за resolve folder_query → folder_id, duplicate check
    і safety check ДО виклику.

    Args:
        folder_id: Drive ID папки куди створити.
        folder_name: назва папки (для логу і response).
        name: назва нового документа.
        initial_content: опційно, plain text для тіла. Порожній рядок = empty doc.
        project: "codehive" / "worqen" — для логу.

    Returns:
        dict з ok / error.
    """
    drive_service = get_drive_service()

    try:
        new_doc = (
            drive_service.files()
            .create(
                body={
                    "name": name,
                    "mimeType": _GOOGLE_DOC_MIME,
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

    # Optional initial_content
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
            batch_update(file_id, requests, required_revision_id=None)
            inserted_chars = len(initial_content)
        except HttpError as e:
            return {
                "ok": True,
                "warning": (
                    f"Документ створений, але initial_content не залився: {e}. "
                    f"Спробуй insert_text(mode='end_of_doc')."
                ),
                "file_id": file_id,
                "file_name": name,
                "folder_id": folder_id,
                "folder_name": folder_name,
                "url": web_view_link,
                "inserted_chars": 0,
            }

    # Log
    try:
        log_doc_write(
            project=project,
            tool="create_doc",
            file_id=file_id,
            file_name=name,
            payload={
                "folder_id": folder_id,
                "folder_name": folder_name,
                "initial_content_length": len(initial_content),
                "inserted_chars": inserted_chars,
            },
        )
    except Exception as e:
        logger.warning("writes_log failed for %s.create_doc: %s", project, e)

    return {
        "ok": True,
        "file_id": file_id,
        "file_name": name,
        "folder_id": folder_id,
        "folder_name": folder_name,
        "url": web_view_link,
        "inserted_chars": inserted_chars,
    }

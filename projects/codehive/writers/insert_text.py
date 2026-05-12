"""codehive_insert_text — handler.

Вставка тексту у gdoc у трьох режимах:
- after: відразу після anchor (substring, case-sensitive, unique)
- before: відразу перед anchor
- end_of_doc: у кінець body (anchor ігнорується — має бути None)

Параметр as_paragraph=True обгортає text у \\n...\\n (для after/before) або
\\n... (для end_of_doc) — щоб вставка ставала окремим абзацом.

Confirm-flow живе у чаті (як у replace_text). Цей tool НЕ має preview-режиму.
"""

import logging
from typing import Any

from googleapiclient.errors import HttpError

from projects.codehive.gdoc_reader import list_all_docs, resolve_doc
from projects.codehive.config import CODEHIVE_MAX_RECURSION_DEPTH
from projects.codehive.writers.safety import SafetyError, check_write_allowed
from shared.docs_client import batch_update, extract_plain_text, get_document
from shared.drive_client import get_service as get_drive_service
from shared.writes_log import log_doc_write

logger = logging.getLogger(__name__)


CONTEXT_RADIUS = 30  # символів зліва/справа для error-контексту при ambiguous anchor
VALID_MODES = ("after", "before", "end_of_doc")


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


def _get_parent_folders(file_id: str) -> list[str]:
    service = get_drive_service()
    meta = (
        service.files()
        .get(fileId=file_id, fields="parents", supportsAllDrives=True)
        .execute()
    )
    return meta.get("parents", [])


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


def insert_text(
    query: str,
    text: str,
    mode: str,
    anchor: str | None = None,
    as_paragraph: bool = False,
) -> dict[str, Any]:
    """
    Вставляє text у документ.

    Args:
        query: повний Drive ID або substring назви документа.
        text: що вставляти.
        mode: "after" | "before" | "end_of_doc".
        anchor: для after/before — substring який треба знайти (case-sensitive, unique).
            Для end_of_doc — має бути None або порожній.
        as_paragraph: якщо True — обгортає text у переноси рядків для окремого абзацу.

    Returns:
        dict з ok / error.
    """
    # --- 1. Validate inputs ---
    if mode not in VALID_MODES:
        return {"error": f"mode має бути одним з {VALID_MODES}, отримано: '{mode}'"}

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

    # --- 2. Resolve query ---
    try:
        all_data = list_all_docs(max_depth=CODEHIVE_MAX_RECURSION_DEPTH)
        gdocs = [d for d in all_data["items"] if d["kind"] == "gdoc"]
        doc_meta = resolve_doc(query, gdocs)
    except ValueError as e:
        return {"error": str(e)}

    file_id = doc_meta["id"]
    file_name = doc_meta["name"]

    # --- 3. Blacklist check ---
    try:
        parent_ids = _get_parent_folders(file_id)
        check_write_allowed(file_id, file_name, parent_ids)
    except SafetyError as e:
        return {"error": f"SafetyError: {e}"}
    except HttpError as e:
        return {"error": f"Не вдалось отримати parents: {e}"}

    # --- 4. Read document ---
    try:
        doc = get_document(file_id)
    except HttpError as e:
        return {"error": f"Не вдалось прочитати документ: {e}"}

    revision_before = doc.get("revisionId")
    plain_text = extract_plain_text(doc)

    # --- 5. Обгортка text за as_paragraph ---
    final_text = _wrap_as_paragraph(text, mode) if as_paragraph else text

    # --- 6. Будуємо insertText request ---
    # Docs API index: 1 = початок body (нульовий символ — невидимий section start).
    # Тобто позиція anchor у plain_text + 1 = Docs API index.
    inserted_at_index: int | None = None

    if mode == "end_of_doc":
        # endOfSegmentLocation без segmentId = body
        request = {
            "insertText": {
                "endOfSegmentLocation": {},
                "text": final_text,
            }
        }
    else:
        # after / before — шукаємо anchor у plain text
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

        # Рівно 1 occurrence
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

    # --- 7. batchUpdate ---
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

    # --- 8. Log ---
    try:
        log_doc_write(
            project="codehive",
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
        logger.warning("writes_log failed for codehive.insert_text: %s", e)

    # --- 9. Response ---
    return {
        "ok": True,
        "file_id": file_id,
        "file_name": file_name,
        "mode": mode,
        "inserted_at_index": inserted_at_index,
        "revision_before": revision_before,
        "revision_after": revision_after,
    }

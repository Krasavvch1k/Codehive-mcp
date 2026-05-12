"""codehive_replace_text — handler.

Логіка:
1. Resolve query → doc_id (через resolve_doc з gdoc_reader).
2. Перевірка blacklist через safety.check_write_allowed.
3. Читання повного документа (Docs API) → revisionId + plain text.
4. Підрахунок occurrences old_text у тексті.
5. Якщо 0 — error "not found".
6. Якщо >1 — error з контекстами (±30 символів навколо).
7. Якщо рівно 1 — batchUpdate з replaceAllText + matchCase=true + requiredRevisionId.
8. Лог у shared/writes_log.
9. Response з old/new revision + context.

Confirm-flow живе у чаті (Claude показує preview через codehive_read_doc
+ "що замінюю", потім кличе цей tool після "так" від користувача).
Tool сам по собі НЕ має preview-режиму — це за дизайном.
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


CONTEXT_RADIUS = 30  # символів зліва/справа для error-контексту при ambiguous match


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
        start = i + 1  # overlap дозволяємо: "aaa" + "aa" → [0, 1]
    return indices


def _format_contexts(text: str, indices: list[int], needle: str) -> list[str]:
    """Для кожного входження повертає рядок виду '...тут_зліва [needle] тут_справа...'"""
    contexts: list[str] = []
    n = len(needle)
    for i in indices:
        left = text[max(0, i - CONTEXT_RADIUS) : i]
        right = text[i + n : i + n + CONTEXT_RADIUS]
        # схлопуємо пробіли/перенос рядків для читаності
        left_clean = " ".join(left.split())
        right_clean = " ".join(right.split())
        contexts.append(f"...{left_clean} [{needle}] {right_clean}...")
    return contexts


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
    Замінити рівно ОДНЕ входження old_text на new_text у документі.

    Args:
        query: повний Drive ID або substring назви документа.
        old_text: текст для пошуку (case-sensitive).
        new_text: чим замінити.

    Returns:
        dict з:
        - ok: bool
        - file_id, file_name
        - revision_before, revision_after
        - replaced: int (завжди 1 при успіху)
        OR error dict з полем 'error' і деталями.
    """
    if not old_text:
        return {"error": "old_text не може бути порожнім"}

    if old_text == new_text:
        return {"error": "old_text == new_text, нічого замінювати"}

    # 1. Resolve query → doc meta
    try:
        all_data = list_all_docs(max_depth=CODEHIVE_MAX_RECURSION_DEPTH)
        gdocs = [d for d in all_data["items"] if d["kind"] == "gdoc"]
        doc_meta = resolve_doc(query, gdocs)
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

    # 3. Читаємо повний документ (revisionId + text)
    try:
        doc = get_document(file_id)
    except HttpError as e:
        return {"error": f"Не вдалось прочитати документ: {e}"}

    revision_before = doc.get("revisionId")
    plain_text = extract_plain_text(doc)

    # 4-6. Підрахунок occurrences
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
            "contexts": contexts[:10],  # обмежимо щоб не залити чат
        }

    # 7. Записуємо
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
        # Очікувані: 400 invalid revision (документ змінився), 403 permission, 404 not found
        return {
            "error": f"batchUpdate failed: {e}",
            "file_id": file_id,
            "file_name": file_name,
            "hint": (
                "Можливо документ змінився між читанням і записом. "
                "Спробуй ще раз."
            ),
        }

    # Витягаємо нову ревізію (writeControl у response містить її)
    revision_after = (
        response.get("writeControl", {}).get("requiredRevisionId") or "unknown"
    )

    # Перевіряємо що replaceAllText реально замінив 1 раз
    replies = response.get("replies", [])
    occurrences_changed = (
        replies[0].get("replaceAllText", {}).get("occurrencesChanged", 0)
        if replies
        else 0
    )

    # 8. Лог
    try:
        log_doc_write(
            project="codehive",
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
        # Логування — не критично для успіху write; продовжуємо
        logger.warning("writes_log failed for codehive.replace_text: %s", e)

    # 9. Response
    return {
        "ok": True,
        "file_id": file_id,
        "file_name": file_name,
        "revision_before": revision_before,
        "revision_after": revision_after,
        "replaced": occurrences_changed,
    }

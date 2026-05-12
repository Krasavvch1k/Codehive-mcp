"""
Обгортка над Google Docs API.
- Без кешу: завжди свіжий стан документа (revisionId критичний для write).
- get_document — повертає dict з 'documentId', 'revisionId', 'body', 'title'.
- batch_update — обгортка над documents.batchUpdate з writeControl.
"""

from googleapiclient.discovery import build

from shared.auth import get_credentials


def _get_service():
    creds = get_credentials()
    return build("docs", "v1", credentials=creds, cache_discovery=False)


def get_document(doc_id: str) -> dict:
    """
    Повертає повний документ через documents.get.

    У відповіді є:
    - 'documentId': str
    - 'title': str
    - 'revisionId': str (потрібен для optimistic locking при write)
    - 'body': {'content': [...]} — структура документа

    Raises:
        googleapiclient.errors.HttpError якщо документ не існує / нема доступу.
    """
    service = _get_service()
    return service.documents().get(documentId=doc_id).execute()


def batch_update(
    doc_id: str,
    requests: list[dict],
    required_revision_id: str | None = None,
) -> dict:
    """
    Виконує batchUpdate з опційним optimistic locking через writeControl.

    Args:
        doc_id: Drive ID документа.
        requests: список request-об'єктів Docs API (replaceAllText, insertText, etc.).
        required_revision_id: якщо передано — Docs відмовить write якщо документ
            змінився (повертає HttpError 400). Використовуй revisionId з get_document().

    Returns:
        Повний response batchUpdate з replies + (опційно) writeControl.

    Raises:
        googleapiclient.errors.HttpError при будь-якій помилці API.
    """
    service = _get_service()
    body: dict = {"requests": requests}
    if required_revision_id is not None:
        body["writeControl"] = {"requiredRevisionId": required_revision_id}
    return service.documents().batchUpdate(documentId=doc_id, body=body).execute()


def extract_plain_text(doc: dict) -> str:
    """
    Витягує plain text з body документа (без форматування).
    Потрібно для пошуку входжень — порахувати скільки разів substring зустрічається.

    Конкатенує всі text-елементи з body.content -> paragraph -> elements -> textRun.
    Не зачіпає таблиці і headers/footers — цього достатньо для замін у основному тексті.
    Якщо колись треба буде шукати в таблицях / headers — додамо обробку.
    """
    parts: list[str] = []
    body = doc.get("body", {})
    for element in body.get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for run in paragraph.get("elements", []):
            text_run = run.get("textRun")
            if text_run:
                parts.append(text_run.get("content", ""))
    return "".join(parts)

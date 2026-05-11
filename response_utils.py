"""
Утиліти для формування відповідей з мінімізацією токенів:
- видалення None / порожніх полів
- табличний формат для великих списків
- pagination
"""

from typing import Optional
from config import TABLE_FORMAT_THRESHOLD, DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT


def strip_empty(obj: dict) -> dict:
    """Видаляє None і порожні значення з словника."""
    return {
        k: v for k, v in obj.items()
        if v is not None and v != "" and v != "—"
    }


def to_table_format(items: list[dict], columns: Optional[list[str]] = None) -> dict:
    """
    Конвертує список об'єктів у табличний формат:
    {"columns": [...], "rows": [[...], ...]}

    Економить токени бо не повторюються ключі.
    """
    if not items:
        return {"columns": columns or [], "rows": []}

    if columns is None:
        # Збираємо всі унікальні ключі
        keys: list[str] = []
        seen = set()
        for item in items:
            for k in item.keys():
                if k not in seen:
                    keys.append(k)
                    seen.add(k)
        columns = keys

    rows = []
    for item in items:
        row = [item.get(col) for col in columns]
        rows.append(row)

    return {"columns": columns, "rows": rows}


def paginate(
    items: list,
    limit: Optional[int] = None,
    offset: int = 0,
) -> tuple[list, dict]:
    """
    Pagination. Повертає (зрізаний список, метадані).
    Метадані: {total, returned, offset, has_more}
    """
    if limit is None:
        limit = DEFAULT_LIST_LIMIT
    limit = min(limit, MAX_LIST_LIMIT)

    total = len(items)
    sliced = items[offset:offset + limit]
    return sliced, {
        "total": total,
        "returned": len(sliced),
        "offset": offset,
        "has_more": offset + len(sliced) < total,
    }


def format_list_response(
    items: list[dict],
    limit: Optional[int] = None,
    offset: int = 0,
    auto_table: bool = True,
    table_columns: Optional[list[str]] = None,
) -> dict:
    """
    Уніфікована відповідь для list-операцій:
    - очищає від None
    - застосовує pagination
    - >TABLE_FORMAT_THRESHOLD рядків - табличний формат
    """
    cleaned = [strip_empty(item) for item in items]
    sliced, meta = paginate(cleaned, limit, offset)

    if auto_table and len(sliced) > TABLE_FORMAT_THRESHOLD:
        table = to_table_format(sliced, table_columns)
        return {**meta, **table}
    else:
        return {**meta, "items": sliced}

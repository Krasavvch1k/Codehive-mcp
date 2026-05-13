"""
Обгортка над Google Sheets API.

Призначена для читання/майбутнього запису у Google Sheets (gsheet).
Для xlsx-файлів використовуйте shared.drive_client.download_file + openpyxl.

- TTL-кеш для read-операцій (CACHE_TTL_SECONDS з shared.config).
- get_spreadsheet_meta — список аркушів, їх розміри.
- get_sheet_values — значення діапазону як 2D-список.
"""

import time
from typing import Optional

from googleapiclient.discovery import build

from shared.auth import get_credentials
from shared.config import CACHE_TTL_SECONDS


def _get_service():
    creds = get_credentials()
    # cache_discovery=False — щоб уникнути попередження про відсутню директорію
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


# Кеш метаданих: spreadsheet_id -> (meta_dict, timestamp)
_meta_cache: dict[str, tuple[dict, float]] = {}

# Кеш значень: (spreadsheet_id, range_str, value_render_option) -> (values_2d, timestamp)
_values_cache: dict[tuple[str, str, str], tuple[list[list], float]] = {}


def get_spreadsheet_meta(
    spreadsheet_id: str,
    force_refresh: bool = False,
) -> dict:
    """
    Метадані spreadsheet: title, список аркушів з розмірами.

    Повертає:
        {
            'spreadsheet_id': str,
            'title': str,
            'sheets': [
                {'sheet_id': int, 'title': str, 'index': int,
                 'row_count': int, 'col_count': int},
                ...
            ],
        }
    """
    now = time.time()
    if not force_refresh and spreadsheet_id in _meta_cache:
        cached, cached_at = _meta_cache[spreadsheet_id]
        if now - cached_at < CACHE_TTL_SECONDS:
            return cached

    service = _get_service()
    resp = (
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="properties.title,sheets.properties",
        )
        .execute()
    )

    sheets: list[dict] = []
    for s in resp.get("sheets", []):
        p = s.get("properties", {})
        grid = p.get("gridProperties", {})
        sheets.append({
            "sheet_id": p.get("sheetId"),
            "title": p.get("title", ""),
            "index": p.get("index", 0),
            "row_count": grid.get("rowCount", 0),
            "col_count": grid.get("columnCount", 0),
        })

    result = {
        "spreadsheet_id": spreadsheet_id,
        "title": resp.get("properties", {}).get("title", ""),
        "sheets": sheets,
    }
    _meta_cache[spreadsheet_id] = (result, now)
    return result


def get_sheet_values(
    spreadsheet_id: str,
    range_str: str,
    value_render_option: str = "FORMATTED_VALUE",
    force_refresh: bool = False,
) -> list[list]:
    """
    Значення діапазону як 2D-список.

    range_str: A1-нотація. Приклади:
        'Sheet1'         — увесь аркуш Sheet1
        'Sheet1!A1:Z100' — конкретний діапазон
        "'My Sheet'!A:A" — увесь стовпець A (назва з пробілом — у лапках)

    value_render_option:
        'FORMATTED_VALUE'   — як видно у UI (форматування дат, чисел)
        'UNFORMATTED_VALUE' — сирі значення (числа як числа, дати як serial)
        'FORMULA'           — формули як текст замість їх результатів

    Повертає 2D-список рядків. Порожні комірки на кінцях рядків можуть
    бути обрізані Sheets API — це нормально.
    """
    now = time.time()
    cache_key = (spreadsheet_id, range_str, value_render_option)
    if not force_refresh and cache_key in _values_cache:
        cached, cached_at = _values_cache[cache_key]
        if now - cached_at < CACHE_TTL_SECONDS:
            return cached

    service = _get_service()
    resp = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=range_str,
            valueRenderOption=value_render_option,
        )
        .execute()
    )
    values = resp.get("values", [])
    _values_cache[cache_key] = (values, now)
    return values


def clear_cache(spreadsheet_id: Optional[str] = None):
    """Скидає кеш метаданих і значень. Якщо id вказано — точково."""
    if spreadsheet_id:
        _meta_cache.pop(spreadsheet_id, None)
        keys_to_drop = [k for k in _values_cache if k[0] == spreadsheet_id]
        for k in keys_to_drop:
            _values_cache.pop(k, None)
    else:
        _meta_cache.clear()
        _values_cache.clear()

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


# ===========================================================================
# WRITE METHODS (Phase 2 — ws_sheet_writer support)
# ===========================================================================
#
# Усі write-операції автоматично інвалідують кеш для spreadsheet_id після
# успіху. Caller (ws_sheet_writer) відповідає за snapshot, drive-sync check
# і logging — sheets_client тільки виконує API виклик.


def update_values(
    spreadsheet_id: str,
    range_str: str,
    values: list[list],
    value_input_option: str = "USER_ENTERED",
) -> dict:
    """
    Перезаписує значення у вказаному діапазоні через values.update.

    range_str: A1-нотація. Має покривати весь values (Sheets API не дозволяє
        записати масив більший за діапазон). Якщо values 1x1 — діапазон 1 cell.

    value_input_option:
        'USER_ENTERED' — Google інтерпретує (формули, дати, числа) — як ввід у UI
        'RAW'          — точно як string

    Повертає response API: updatedRange, updatedRows, updatedColumns, updatedCells.
    """
    service = _get_service()
    body = {"values": values}

    resp = (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=range_str,
            valueInputOption=value_input_option,
            body=body,
        )
        .execute()
    )

    clear_cache(spreadsheet_id)
    return resp


def append_values(
    spreadsheet_id: str,
    range_str: str,
    values: list[list],
    value_input_option: str = "USER_ENTERED",
    insert_data_option: str = "INSERT_ROWS",
) -> dict:
    """
    Додає рядки у кінець таблиці через values.append.

    range_str — діапазон де Sheets шукає кінець таблиці. Зазвичай ім'я аркуша
        ('Sheet1') або стовпець ('Sheet1!A:A').

    insert_data_option:
        'INSERT_ROWS' — вставляє нові рядки (shift existing data down if needed)
        'OVERWRITE'   — перезаписує існуючі рядки нижче діапазону

    value_input_option — як у update_values.

    Повертає response API: tableRange, updates: {updatedRange, ...}.
    """
    service = _get_service()
    body = {"values": values}

    resp = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=range_str,
            valueInputOption=value_input_option,
            insertDataOption=insert_data_option,
            body=body,
        )
        .execute()
    )

    clear_cache(spreadsheet_id)
    return resp


def batch_update(
    spreadsheet_id: str,
    requests: list[dict],
) -> dict:
    """
    Виконує structural changes через spreadsheets.batchUpdate.

    Не плутати з values.batchUpdate (для масової зміни значень) — цей метод для
    структурних операцій: addSheet, deleteSheet, updateSheetProperties,
    insertDimension, deleteDimension, mergeCells, тощо.

    requests: список request об'єктів, наприклад:
        [{"addSheet": {"properties": {"title": "NewSheet"}}}]

    Повертає response API: replies (один на кожен request).
    """
    service = _get_service()
    body = {"requests": requests}

    resp = (
        service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body,
        )
        .execute()
    )

    clear_cache(spreadsheet_id)
    return resp


def create_spreadsheet(
    name: str,
    initial_sheet_title: Optional[str] = None,
    columns: Optional[list[str]] = None,
) -> dict:
    """
    Створює новий spreadsheet через spreadsheets.create.

    Args:
        name: назва нового spreadsheet.
        initial_sheet_title: назва першого аркуша (default — Sheets API сам ставить
            'Sheet1').
        columns: якщо передано — записує як header row у першому аркуші.

    NB: цей метод НЕ кладе файл у вказану папку — Sheets API кладе у "My Drive"
        root service account-а. Якщо треба у конкретну папку — після create
        викликати Drive API files.update(addParents=folder_id, removeParents=...)
        або краще створювати через Drive API напряму з MIME-type spreadsheet.

    Повертає response API: spreadsheetId, spreadsheetUrl, sheets, properties.
    """
    service = _get_service()
    body: dict = {"properties": {"title": name}}
    if initial_sheet_title:
        body["sheets"] = [{"properties": {"title": initial_sheet_title}}]

    resp = (
        service.spreadsheets()
        .create(body=body, fields="spreadsheetId,spreadsheetUrl,properties,sheets")
        .execute()
    )

    # Опційно — записати header row
    if columns:
        spreadsheet_id = resp["spreadsheetId"]
        sheet_title = initial_sheet_title or resp["sheets"][0]["properties"]["title"]
        # range — перший рядок шириною len(columns)
        end_col_letter = _col_index_to_letter(len(columns))
        header_range = f"'{sheet_title}'!A1:{end_col_letter}1"
        update_values(spreadsheet_id, header_range, [columns])

    return resp


def _col_index_to_letter(idx: int) -> str:
    """1-based column index → A1 letter. 1=A, 26=Z, 27=AA, 52=AZ, 702=ZZ."""
    if idx < 1:
        raise ValueError(f"Column index must be >= 1, got {idx}")
    letters = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters

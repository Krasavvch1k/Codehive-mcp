"""
Журнал успішних записів через writers.

Generic — не містить worqen/codehive-specific логіки. Логує тільки те,
що writer передав: tool, record_id, file_key, fields_changed, etc.
"""

import json
import os
from datetime import datetime
from typing import Optional

from shared.config import PROJECT_DIR


LOG_DIR = os.path.join(PROJECT_DIR, "writes_log")


def _log_path_for_date(date_str: str) -> str:
    return os.path.join(LOG_DIR, f"{date_str}.json")


def _ensure_log_dir() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)


def log_write(
    tool: str,
    record_id: str,
    file_key: str,
    fields_changed: list,
    force_overwrite: bool,
    row: int,
    drive_modified_after: Optional[str],
    fields_preview: Optional[dict] = None,
) -> None:
    try:
        _ensure_log_dir()
        today = datetime.now().strftime("%Y-%m-%d")
        path = _log_path_for_date(today)

        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "tool": tool,
            "id": record_id,
            "file_key": file_key,
            "fields_changed": list(fields_changed),
            "force_overwrite": bool(force_overwrite),
            "row": row,
            "drive_modified_after": drive_modified_after,
        }
        if fields_preview is not None:
            entry["fields_preview"] = {
                k: ("" if v is None else str(v)) for k, v in fields_preview.items()
            }

        if os.path.exists(path):
            try:
                with open(path) as f:
                    log = json.load(f)
                if not isinstance(log, list):
                    log = []
            except json.JSONDecodeError:
                log = []
        else:
            log = []

        log.append(entry)
        with open(path, "w") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def read_log_by_date(date_str: str) -> list:
    path = _log_path_for_date(date_str)
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def read_today_log() -> list:
    today = datetime.now().strftime("%Y-%m-%d")
    return read_log_by_date(today)


def filter_log(
    entries: list,
    tool: Optional[str] = None,
    record_id: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> list:
    rid = record_id.strip().upper() if record_id else None
    result = []
    for e in entries:
        if tool and e.get("tool") != tool:
            continue
        if rid and (e.get("id") or "").strip().upper() != rid:
            continue
        ts = e.get("timestamp") or ""
        if since and ts < since:
            continue
        if until and ts > until:
            continue
        result.append(e)
    return result

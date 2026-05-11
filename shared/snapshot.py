"""
Snapshot — серіалізація поточного стану xlsx-файлів у JSON.
Використовується для session_changes (порівняння між знімками).
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import Optional

from shared.config import SNAPSHOT_DIR, SNAPSHOT_RETENTION_DAYS


def _ensure_dir():
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def _today_path() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(SNAPSHOT_DIR, f"{today}.json")


def save_snapshot(data: dict) -> str:
    """
    Зберігає знімок поточного дня. Якщо файл сьогоднішнього дня вже є —
    перезаписує (тримаємо останній стан дня).
    Повертає шлях до файлу.
    """
    _ensure_dir()
    path = _today_path()
    payload = {
        "saved_at": datetime.now().isoformat(),
        "timestamp": time.time(),
        "data": data,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    _cleanup_old()
    return path


def load_snapshot(date_str: Optional[str] = None) -> Optional[dict]:
    """
    Завантажує знімок за датою (YYYY-MM-DD).
    Якщо дата не вказана — найсвіжіший доступний (крім сьогоднішнього).
    Повертає None якщо немає.
    """
    _ensure_dir()
    if date_str:
        path = os.path.join(SNAPSHOT_DIR, f"{date_str}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # Шукаємо найсвіжіший крім сьогоднішнього
    today = datetime.now().strftime("%Y-%m-%d")
    files = sorted(os.listdir(SNAPSHOT_DIR), reverse=True)
    for f in files:
        if not f.endswith(".json"):
            continue
        date_part = f.replace(".json", "")
        if date_part == today:
            continue
        path = os.path.join(SNAPSHOT_DIR, f)
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return None


def list_snapshots() -> list[dict]:
    """Список усіх збережених снепшотів з датами."""
    _ensure_dir()
    result = []
    for f in sorted(os.listdir(SNAPSHOT_DIR)):
        if not f.endswith(".json"):
            continue
        path = os.path.join(SNAPSHOT_DIR, f)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            result.append({
                "date": f.replace(".json", ""),
                "saved_at": data.get("saved_at"),
                "size_kb": round(os.path.getsize(path) / 1024, 1),
            })
        except Exception:
            continue
    return result


def _cleanup_old():
    """Видаляє снепшоти старші за SNAPSHOT_RETENTION_DAYS."""
    cutoff = datetime.now() - timedelta(days=SNAPSHOT_RETENTION_DAYS)
    for f in os.listdir(SNAPSHOT_DIR):
        if not f.endswith(".json"):
            continue
        path = os.path.join(SNAPSHOT_DIR, f)
        try:
            date_str = f.replace(".json", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            if file_date < cutoff:
                os.remove(path)
        except (ValueError, OSError):
            continue

"""
Safety layer для writer'ів.

Викликається перед КОЖНИМ записом. Робить:
1. Drive sync check — порівнює modifiedTime у Drive з тим що ми
   бачили на момент початку операції. Якщо змінився — стоп.
2. Auto snapshot — викликає save_today_snapshot() якщо сьогодні
   ще не було знімка.

Якщо щось з перевірок не пройшло — піднімається SafetyError.
Writer ловить її і повертає у MCP-відповідь.
"""

import os
from datetime import datetime
from typing import Optional

from drive_client import fetch_current_drive_modified
from shared.config import SNAPSHOT_DIR


class SafetyError(Exception):
    """Помилка перевірки безпеки запису."""
    def __init__(self, message: str, kind: str = "generic"):
        super().__init__(message)
        self.kind = kind


def check_drive_unchanged(file_id: str, baseline_modified: Optional[str]) -> str:
    """
    Перевіряє що Drive не змінився між baseline_modified і поточним
    моментом.

    baseline_modified — modifiedTime який writer запам'ятав на початку
    операції (через fetch_current_drive_modified).

    Повертає актуальний modifiedTime (для логування у відповіді).
    Піднімає SafetyError якщо файл змінився.
    """
    current = fetch_current_drive_modified(file_id)
    if current is None:
        raise SafetyError(
            f"Не вдалося отримати modifiedTime з Drive для file_id={file_id}",
            kind="drive_unreachable",
        )
    if baseline_modified is None:
        # Перший виклик — просто повертаємо current.
        return current
    if current != baseline_modified:
        raise SafetyError(
            f"Файл змінений на Drive під час операції "
            f"(baseline={baseline_modified}, current={current}). "
            f"Можливо ти його редагуєш. Збережи свої зміни і скажи 'спробуй ще'.",
            kind="drive_changed",
        )
    return current


def ensure_today_snapshot() -> dict:
    """
    Якщо сьогоднішнього снепшоту ще немає — створює.
    Якщо вже є — нічого не робить.

    Повертає {"created": bool, "path": str | None}.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    today_path = os.path.join(SNAPSHOT_DIR, f"{today}.json")

    if os.path.exists(today_path):
        return {"created": False, "path": today_path}

    # Імпорт всередині функції щоб уникнути циклу
    # (analytics.py імпортує parsers, parsers поки що не імпортує writers,
    # але краще перестрахуватись).
    from parsers import analytics
    path = analytics.save_today_snapshot()
    return {"created": True, "path": path}

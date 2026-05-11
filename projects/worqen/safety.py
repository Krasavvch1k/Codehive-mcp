"""
Safety layer — worqen-extension.

Worqen-specific: auto-snapshot xlsx перед записом (бо worqen — read+write,
а snapshot робиться з worqen FILE_IDS через parsers.analytics).

Re-exportує generic safety-символи з shared.safety, щоб worqen writers
імпортували все з одного місця (`from projects.worqen.safety import ...`).
"""

import os
from datetime import datetime

# Re-export generic частини — щоб worqen writers мали єдиний safety surface.
from shared.safety import SafetyError, check_drive_unchanged  # noqa: F401

from shared.config import SNAPSHOT_DIR


def ensure_today_snapshot() -> dict:
    """
    Якщо сьогоднішнього снепшоту ще немає — створює.
    Якщо вже є — нічого не робить.

    Worqen-specific: знімає worqen FILE_IDS через parsers.analytics.
    Якщо codehive у майбутньому отримає write tools — він матиме свій
    окремий snapshot helper (або не матиме, бо документи в Google Docs
    versioning'у і так).

    Повертає {"created": bool, "path": str | None}.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    today_path = os.path.join(SNAPSHOT_DIR, f"{today}.json")

    if os.path.exists(today_path):
        return {"created": False, "path": today_path}

    # Імпорт всередині функції щоб уникнути циклу
    # (analytics імпортує парсери, парсери імпортують config; safety
    # підтягувати весь цей граф на import-time не потрібно).
    from projects.worqen.parsers import analytics
    path = analytics.save_today_snapshot()
    return {"created": True, "path": path}

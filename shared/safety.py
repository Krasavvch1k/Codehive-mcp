"""
Safety layer — generic частина (project-agnostic).

Містить лише ті перевірки, що не залежать від конкретного проєкту:
- SafetyError — типизована помилка
- check_drive_unchanged — порівняння modifiedTime з baseline

Project-specific safety (наприклад auto-snapshot для worqen) живе у
projects/<name>/safety.py і може re-exportувати символи з цього модуля.
"""

from typing import Optional

from drive_client import fetch_current_drive_modified


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

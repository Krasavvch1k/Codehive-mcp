"""Safety checks для CodeHive write tools.

Pattern як у projects/worqen/safety.py: shared/safety re-export +
codehive-specific логіка (blacklist перевірка).
"""

from shared.safety import SafetyError, check_drive_unchanged  # noqa: F401

from projects.codehive.config import (
    WRITE_BLACKLIST_FILE_IDS,
    WRITE_BLACKLIST_FOLDERS,
    WRITE_BLACKLIST_NAME_SUBSTRINGS,
)


def check_write_allowed(
    file_id: str,
    file_name: str,
    parent_folder_ids: list[str],
) -> None:
    """
    Перевіряє чи дозволено писати у документ.

    Логіка: дефолт = все можна (всі три списки порожні).
    Заборона спрацьовує якщо ХОЧ ОДНА умова виконана:
    - file_id у WRITE_BLACKLIST_FILE_IDS
    - назва (case-insensitive substring) містить будь-який pattern з WRITE_BLACKLIST_NAME_SUBSTRINGS
    - хоч один parent folder у WRITE_BLACKLIST_FOLDERS

    Raises:
        SafetyError з explanation чому саме заборонено.
    """
    if file_id in WRITE_BLACKLIST_FILE_IDS:
        raise SafetyError(
            f"Файл {file_id} у WRITE_BLACKLIST_FILE_IDS — write заборонений."
        )

    name_lower = (file_name or "").lower()
    for pattern in WRITE_BLACKLIST_NAME_SUBSTRINGS:
        if pattern.lower() in name_lower:
            raise SafetyError(
                f"Назва '{file_name}' містить заборонений pattern '{pattern}' — "
                f"write заборонений."
            )

    for parent_id in parent_folder_ids:
        if parent_id in WRITE_BLACKLIST_FOLDERS:
            raise SafetyError(
                f"Файл у папці {parent_id} яка у WRITE_BLACKLIST_FOLDERS — "
                f"write заборонений."
            )

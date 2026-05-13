"""
Worqen Workspace — write tools для docx і gdoc.

Шар обгорток над shared.doc_writers (gdoc через Docs API) і shared.docx_writers
(docx через python-docx + reupload). Робить:

1. Resolve query → file через ws_reader.resolve (повертає id + mime + kind)
2. Blacklist check (WRITE_BLACKLIST_FILE_IDS / NAME_SUBSTRINGS / FOLDERS)
3. Маршрутизація: gdoc → shared.doc_writers, docx → shared.docx_writers
4. dry_run: повертає preview без write

dry_run preview включає:
- Який файл буде зачеплений (id, name, kind, path)
- Що саме буде зроблено (mode, anchor, before/after сніппет)
- Чи проходить blacklist check
- WIthout commit

Не використовується для xlsx/gsheet — це у ws_sheet_writer.
Не використовується для create — це у ws_creator.
"""

import logging
from typing import Any, Optional

from shared.doc_writers import (
    insert_text_in_doc as _insert_text_in_gdoc,
    replace_text_in_doc as _replace_text_in_gdoc,
)
from shared.docx_writers import (
    insert_text_in_docx as _insert_text_in_docx,
    replace_text_in_docx as _replace_text_in_docx,
)
from shared.safety import SafetyError

from projects.worqen.config import (
    WRITE_BLACKLIST_FILE_IDS,
    WRITE_BLACKLIST_FOLDERS,
    WRITE_BLACKLIST_NAME_SUBSTRINGS,
)
from projects.worqen.ws_reader import list_all, resolve

logger = logging.getLogger(__name__)


# Підтримувані kinds для write через docx/gdoc tools
_WRITABLE_DOC_KINDS = ("docx", "gdoc")

PROJECT = "worqen"  # для логування


# ----- blacklist -----

def _check_blacklist(doc_meta: dict) -> None:
    """
    Перевіряє чи doc_meta не у blacklist.

    Raises SafetyError якщо:
    - file_id у WRITE_BLACKLIST_FILE_IDS (точне співпадіння)
    - parent_folder_id у WRITE_BLACKLIST_FOLDERS
    - name містить будь-який з WRITE_BLACKLIST_NAME_SUBSTRINGS (case-insensitive)
    """
    file_id = doc_meta["id"]
    name = doc_meta.get("name", "")
    parent_id = doc_meta.get("parent_folder_id", "")

    if file_id in WRITE_BLACKLIST_FILE_IDS:
        raise SafetyError(
            f"Файл '{name}' (id={file_id}) у WRITE_BLACKLIST_FILE_IDS. "
            f"Для US/BUG використовуй worqen_update_user_story / worqen_update_bug.",
            kind="blacklisted_file_id",
        )

    if parent_id and parent_id in WRITE_BLACKLIST_FOLDERS:
        raise SafetyError(
            f"Папка батьківська (id={parent_id}) у WRITE_BLACKLIST_FOLDERS. "
            f"Запис у файли цієї папки заборонений.",
            kind="blacklisted_folder",
        )

    name_lower = name.lower()
    for substr in WRITE_BLACKLIST_NAME_SUBSTRINGS:
        if substr.lower() in name_lower:
            raise SafetyError(
                f"Назва '{name}' містить '{substr}' (WRITE_BLACKLIST_NAME_SUBSTRINGS). "
                f"Запис заборонений.",
                kind="blacklisted_name",
            )


# ----- resolve helper -----

def _resolve_writable_doc(query: str) -> dict:
    """
    Резолвить query до docx/gdoc файлу і перевіряє blacklist.

    Raises:
        SafetyError якщо blacklisted.
        ValueError якщо не знайдено / ambiguous / це не doc-тип.
    """
    all_data = list_all()
    candidates = [
        d for d in all_data["items"] if d["kind"] in _WRITABLE_DOC_KINDS
    ]
    doc_meta = resolve(query, candidates)

    if doc_meta["kind"] not in _WRITABLE_DOC_KINDS:
        raise ValueError(
            f"Файл '{doc_meta['name']}' має kind='{doc_meta['kind']}', "
            f"очікую один з {_WRITABLE_DOC_KINDS}. "
            f"Для sheets використовуй worqen_ws_update_cell / update_range / append_row."
        )

    _check_blacklist(doc_meta)
    return doc_meta


# ----- preview helpers -----

def _preview_for_replace(
    doc_meta: dict, old_text: str, new_text: str
) -> dict:
    """Будує dry_run preview для replace_text."""
    return {
        "operation": "replace_text",
        "file_id": doc_meta["id"],
        "file_name": doc_meta["name"],
        "kind": doc_meta["kind"],
        "path": doc_meta.get("path"),
        "old_text": old_text,
        "new_text": new_text,
        "old_text_length": len(old_text),
        "new_text_length": len(new_text),
        "would_write": True,
        "dry_run": True,
        "note": (
            "Це preview без запису. Передай dry_run=False (default) щоб виконати. "
            "Реальний write перевірить що old_text знайдено РІВНО 1 раз і що "
            "файл не змінився на Drive між preview і write."
        ),
    }


def _preview_for_insert(
    doc_meta: dict, text: str, mode: str, anchor: Optional[str]
) -> dict:
    """Будує dry_run preview для insert_text."""
    return {
        "operation": "insert_text",
        "file_id": doc_meta["id"],
        "file_name": doc_meta["name"],
        "kind": doc_meta["kind"],
        "path": doc_meta.get("path"),
        "mode": mode,
        "anchor": anchor,
        "text": text,
        "text_length": len(text),
        "would_write": True,
        "dry_run": True,
        "note": (
            "Це preview без запису. Передай dry_run=False (default) щоб виконати. "
            "Для mode='after'/'before' реальний write перевірить що anchor "
            "знайдено РІВНО 1 раз."
        ),
    }


# ----- public API: replace_text -----

def ws_replace_text(
    query: str,
    old_text: str,
    new_text: str,
    dry_run: bool = False,
    force_overwrite: bool = False,
    as_paragraph: bool = False,  # noqa: ARG001  — accepted for symmetry, not used
) -> dict[str, Any]:
    """
    Замінює рівно ОДНЕ входження old_text на new_text у doc.

    Маршрутизація за kind:
    - gdoc → shared.doc_writers.replace_text_in_doc (через Docs API)
    - docx → shared.docx_writers.replace_text_in_docx (через python-docx)

    Args:
        query: substring у name або повний Drive ID.
        old_text: текст для пошуку (case-sensitive).
        new_text: чим замінити.
        dry_run: якщо True — повертає preview без запису.
        force_overwrite: ігнорувати drive-unchanged check (тільки для docx,
            gdoc використовує revisionId-локінг через Docs API).

    Returns:
        dict з ok / error / dry_run preview.
    """
    try:
        doc_meta = _resolve_writable_doc(query)
    except SafetyError as e:
        return {"error": str(e), "kind": e.kind}
    except ValueError as e:
        return {"error": str(e), "kind": "resolve_failed"}

    if dry_run:
        return _preview_for_replace(doc_meta, old_text, new_text)

    if doc_meta["kind"] == "gdoc":
        return _replace_text_in_gdoc(
            file_id=doc_meta["id"],
            file_name=doc_meta["name"],
            old_text=old_text,
            new_text=new_text,
            project=PROJECT,
        )
    else:  # docx
        return _replace_text_in_docx(
            file_id=doc_meta["id"],
            file_name=doc_meta["name"],
            old_text=old_text,
            new_text=new_text,
            project=PROJECT,
            force_overwrite=force_overwrite,
        )


# ----- public API: insert_text -----

def ws_insert_text(
    query: str,
    text: str,
    mode: str = "end_of_doc",
    anchor: Optional[str] = None,
    dry_run: bool = False,
    force_overwrite: bool = False,
    as_paragraph: bool = True,
) -> dict[str, Any]:
    """
    Вставка тексту у doc — режими after / before / end_of_doc.

    Args:
        query: substring у name або повний Drive ID.
        text: що вставляти.
        mode: 'after' | 'before' | 'end_of_doc' (default).
        anchor: для after/before — substring (case-sensitive, unique). Для
            end_of_doc — None.
        dry_run: якщо True — preview без запису.
        force_overwrite: тільки для docx (для gdoc використовується revisionId).
        as_paragraph: тільки для gdoc (для docx завжди trades-off на параграфах).

    Returns:
        dict з ok / error / dry_run preview.
    """
    try:
        doc_meta = _resolve_writable_doc(query)
    except SafetyError as e:
        return {"error": str(e), "kind": e.kind}
    except ValueError as e:
        return {"error": str(e), "kind": "resolve_failed"}

    if dry_run:
        return _preview_for_insert(doc_meta, text, mode, anchor)

    if doc_meta["kind"] == "gdoc":
        return _insert_text_in_gdoc(
            file_id=doc_meta["id"],
            file_name=doc_meta["name"],
            text=text,
            mode=mode,
            anchor=anchor,
            as_paragraph=as_paragraph,
            project=PROJECT,
        )
    else:  # docx
        return _insert_text_in_docx(
            file_id=doc_meta["id"],
            file_name=doc_meta["name"],
            text=text,
            mode=mode,
            anchor=anchor,
            project=PROJECT,
            force_overwrite=force_overwrite,
        )


# ----- public API: replace_section (basic — heading anchor) -----

def ws_replace_section(
    query: str,
    heading: str,
    new_content: str,
    dry_run: bool = False,
    force_overwrite: bool = False,
) -> dict[str, Any]:
    """
    Замінює "секцію" документа за heading-anchor.

    Базовий алгоритм:
    1. Знаходимо heading (точне співпадіння рядка) у документі.
    2. "Секція" — текст від рядка ПІСЛЯ heading до рядка ПЕРЕД наступним
       heading того ж рівня (визначається префіксом '#').
    3. Замінюємо цей блок на new_content.

    NB: ця імплементація працює на plain-text рівні і не зберігає рівні
    нумерації заголовків у docx (heading style). Для production-нюансів
    можна доробити Phase 2.5. Поки що — практичний MVP.

    Args:
        query: name substring або Drive ID.
        heading: повний рядок-заголовок (з '#'). Наприклад '## Use Cases'.
        new_content: чим замінити тіло секції.
        dry_run: preview без запису.
        force_overwrite: ігнорувати drive-unchanged check (для docx).

    Returns:
        dict з ok / error / dry_run preview.

    HINT: для більш простих правок використовуй ws_replace_text — він
    точкове і прозоріше.
    """
    return {
        "error": (
            "ws_replace_section ще не реалізовано (Phase 2.5). "
            "Використовуй ws_replace_text для точкових правок або "
            "ws_insert_text з mode='end_of_doc' для додавання."
        ),
        "kind": "not_implemented",
        "hint": (
            "Якщо потрібна заміна великого блоку — розбий на серію "
            "ws_replace_text викликів (1 замінник = 1 виклик), або "
            "видали блок руками і використай ws_insert_text для нового вмісту."
        ),
        "query": query,
        "heading": heading,
        "dry_run": dry_run,
        "force_overwrite": force_overwrite,
    }

"""
Парсер для папки "Обговорення з командою" (Google Docs у підпапках за датами).

Експортує три основні функції які використовуються MCP-сервером:
- list_team_discussions(...)       - список з фільтрами
- read_team_discussion(...)        - читання одного документу як markdown
- search_team_discussions(...)     - пошук за іменем/контентом

Структура папки в Drive:
    Обговорення з камандою/
    ├── 06.05.26 Обговорення функціонал (закрили)/
    │   ├── Worqs Tier Model (закрили)
    │   ├── Solana Staking (обговорили)
    │   └── ...
    └── 09.05.26 Продуктові обговорення з командою ()/
        └── Worqen Score: per-role чи unified

Документи — Google Docs (експортуємо у docx через drive_client.download_file fmt='gdoc').
"""

import re
from typing import Optional

from drive_client import (
    download_file,
    list_docs_in_folder_recursive,
)
from projects.worqen.config import TEAM_DISCUSSIONS_FOLDER_ID
from shared.gdoc import (
    docx_bytes_to_markdown,
    docx_bytes_to_plain_text,
    extract_snippet,
)


# ---------- Парсинг метаданих з назви ----------

# Ловить '(закрили)', '(обговорили)', '(закрити)', '()'.
# Беремо ОСТАННІ дужки в кінці рядка — інакше зламає на назвах типу
# '4.4.1 User (users)' (хоча в Discussions таких не повинно бути, страховка).
_STATUS_RE = re.compile(r"^(.*?)\s*\(([^)]*)\)\s*$")

# Ловить дату на початку: '06.05.26', '09.05.26', '12.05.2026'.
_DATE_PREFIX_RE = re.compile(r"^(\d{1,2}\.\d{1,2}\.\d{2,4})\s+")


# Fallback: якщо статус не у дужках, а написаний в кінці назви без дужок.
# 'Сегментація аудиторії v1 закрили' → status='закрили'
# Шукаємо тільки в кінці, щоб не зламати назви де ці слова — частина змісту.
_BARE_STATUS_RE = re.compile(
    r"^(.*?)\s+(закрили|закрити|обговорили)\s*$",
    re.IGNORECASE,
)


def _parse_doc_name(raw_name: str) -> dict:
    """
    Парсить назву файлу-обговорення:
        'Worqs Tier Model (закрили)' →
            { name: 'Worqs Tier Model', status: 'закрили' }
        'Сегментація аудиторії v1 закрили' →
            { name: 'Сегментація аудиторії v1', status: 'закрили' }
        'Worqen Score: per-role чи unified' →
            { name: 'Worqen Score: per-role чи unified', status: None }
        '4.4.1 User (users) (закрили)' →
            { name: '4.4.1 User (users)', status: 'закрили' }  # беремо тільки останні дужки

    Спочатку пробуємо знайти статус у дужках. Якщо немає — fallback:
    шукаємо bare keyword (закрили / закрити / обговорили) в кінці.
    """
    raw = raw_name.strip()

    # 1. Дужки
    m = _STATUS_RE.match(raw)
    if m:
        clean = m.group(1).strip()
        status = m.group(2).strip() or None  # '()' → None
        # Якщо у дужках статус пустий — пробуємо bare fallback на clean-частині
        if status is None:
            return _parse_doc_name(clean)
        return {"name": clean, "status": status}

    # 2. Bare-статус в кінці без дужок
    bm = _BARE_STATUS_RE.match(raw)
    if bm:
        clean = bm.group(1).strip()
        status = bm.group(2).lower()  # нормалізуємо реєстр
        return {"name": clean, "status": status}

    return {"name": raw, "status": None}


def _parse_session_folder_name(folder_name: Optional[str]) -> dict:
    """
    Парсить назву підпапки-сесії:
        '06.05.26 Обговорення функціонал (закрили)' →
            { date: '06.05.26', name: 'Обговорення функціонал', status: 'закрили' }
    """
    if not folder_name:
        return {"date": None, "name": None, "status": None}

    name = folder_name.strip()

    # Витягуємо дату з початку
    date_match = _DATE_PREFIX_RE.match(name)
    if date_match:
        date = date_match.group(1)
        rest = name[date_match.end():]
    else:
        date = None
        rest = name

    # Витягуємо статус у кінці
    parsed = _parse_doc_name(rest)
    return {
        "date": date,
        "name": parsed["name"] or None,
        "status": parsed["status"],
    }


def _enrich_doc(raw_doc: dict) -> dict:
    """
    Доповнює запис з drive_client метаданими від парсингу назви.
    Очікує сирий запис з полів: id, name, modified, size_bytes,
                                parent_folder_id, parent_folder_name.
    """
    parsed = _parse_doc_name(raw_doc["name"])
    parent_parsed = _parse_session_folder_name(raw_doc.get("parent_folder_name"))

    return {
        "id": raw_doc["id"],
        "name": parsed["name"],          # очищена назва без статусу
        "raw_name": raw_doc["name"],     # повна оригінальна назва
        "status": parsed["status"],      # 'закрили' / 'обговорили' / None
        "session_date": parent_parsed["date"],
        "session_folder_name": raw_doc.get("parent_folder_name"),
        "modified": raw_doc.get("modified"),
        "size_bytes": raw_doc.get("size_bytes"),
    }


# ---------- Резолвінг документу за name або id ----------


def _resolve_to_id(query: str, all_docs: list[dict]) -> dict:
    """
    Повертає рівно один документ за query.
    query може бути:
        - повним id (44 символи, починається на 1, без пробілів і дужок)
        - частиною name (case-insensitive substring у raw_name або name)

    Повертає dict з полями enriched-doc'у.

    Якщо знайдено 0 — піднімає ValueError з підказкою.
    Якщо знайдено >1 — піднімає ValueError зі списком кандидатів.
    """
    q = query.strip()

    # Спочатку пробуємо як точний ID (Google Drive IDs зазвичай довгі alphanumeric)
    if len(q) > 25 and " " not in q and "(" not in q:
        for d in all_docs:
            if d["id"] == q:
                return d
        # Не знайшли точний ID — продовжимо як substring у назвах

    # Тепер як substring у raw_name або clean name
    q_lower = q.lower()
    matches = [
        d for d in all_docs
        if q_lower in d["raw_name"].lower() or q_lower in d["name"].lower()
    ]

    if not matches:
        raise ValueError(
            f"Документ за запитом '{query}' не знайдено. "
            f"Спробуй list_team_discussions для перегляду всіх назв."
        )

    if len(matches) > 1:
        names = [f"{m['raw_name']} (id: {m['id'][:12]}...)" for m in matches[:5]]
        more = f", ...ще {len(matches) - 5}" if len(matches) > 5 else ""
        raise ValueError(
            f"За запитом '{query}' знайдено {len(matches)} документів. "
            f"Уточни запит. Кандидати: {'; '.join(names)}{more}"
        )

    return matches[0]


# ---------- Основні функції tools ----------


def list_team_discussions(
    status: Optional[str] = None,
    session_date: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """
    Повертає список усіх обговорень з папки.

    Фільтри:
        status:       'закрили' / 'обговорили' / 'open' (== status is None) / None (всі)
        session_date: точна дата сесії '06.05.26' (за parent_folder)
        limit:        максимум елементів (default 50)

    Повертає:
        {
            "count": N,
            "total_unfiltered": M,
            "discussions": [enriched_doc, ...],
        }
    """
    raw_docs = list_docs_in_folder_recursive(TEAM_DISCUSSIONS_FOLDER_ID)
    enriched = [_enrich_doc(d) for d in raw_docs]
    total = len(enriched)

    # Фільтри
    filtered = enriched

    if status is not None:
        if status == "open":
            filtered = [d for d in filtered if d["status"] is None]
        else:
            status_lower = status.lower()
            filtered = [
                d for d in filtered
                if d["status"] and d["status"].lower() == status_lower
            ]

    if session_date is not None:
        filtered = [d for d in filtered if d["session_date"] == session_date]

    # Сортування: спочатку за датою сесії (новіші зверху), потім за modified
    filtered.sort(
        key=lambda d: (d["session_date"] or "", d["modified"] or ""),
        reverse=True,
    )

    return {
        "count": min(limit, len(filtered)),
        "total_unfiltered": total,
        "total_after_filters": len(filtered),
        "discussions": filtered[:limit],
    }


def read_team_discussion(query: str) -> dict:
    """
    Читає вміст одного документу-обговорення.

    query: частина name або повний id.

    Повертає:
        {
            "id": str,
            "name": str,
            "raw_name": str,
            "status": str | None,
            "session_date": str | None,
            "session_folder_name": str | None,
            "length": int,
            "text": str,  # markdown
        }
    """
    raw_docs = list_docs_in_folder_recursive(TEAM_DISCUSSIONS_FOLDER_ID)
    enriched = [_enrich_doc(d) for d in raw_docs]

    doc_meta = _resolve_to_id(query, enriched)

    # Завантажуємо як gdoc (всі файли в цій папці — Google Docs)
    content = download_file(doc_meta["id"], fmt="gdoc")
    text = docx_bytes_to_markdown(content)

    return {
        "id": doc_meta["id"],
        "name": doc_meta["name"],
        "raw_name": doc_meta["raw_name"],
        "status": doc_meta["status"],
        "session_date": doc_meta["session_date"],
        "session_folder_name": doc_meta["session_folder_name"],
        "length": len(text),
        "text": text,
    }


def search_team_discussions(
    query: str,
    scope: str = "names",
    limit: int = 20,
    context_chars: int = 200,
) -> dict:
    """
    Пошук серед обговорень.

    scope:
        'names'   — пошук тільки у назвах файлів і папок-сесій (швидко, default)
        'content' — пошук у тексті документів (повільно, скачує всі)
        'both'    — names + content

    Повертає:
        {
            "scope": str,
            "query": str,
            "name_matches": [enriched_doc, ...],
            "content_matches": [{ "id", "name", "snippet" }, ...],
            "total_name_matches": N,
            "total_content_matches": M,
        }
    """
    if scope not in ("names", "content", "both"):
        raise ValueError(f"scope має бути 'names' / 'content' / 'both', не '{scope}'")

    raw_docs = list_docs_in_folder_recursive(TEAM_DISCUSSIONS_FOLDER_ID)
    enriched = [_enrich_doc(d) for d in raw_docs]
    q_lower = query.lower()

    name_matches: list[dict] = []
    content_matches: list[dict] = []

    if scope in ("names", "both"):
        for d in enriched:
            if (
                q_lower in d["raw_name"].lower()
                or q_lower in d["name"].lower()
                or (d["session_folder_name"] and q_lower in d["session_folder_name"].lower())
            ):
                name_matches.append(d)

    if scope in ("content", "both"):
        for d in enriched:
            try:
                content = download_file(d["id"], fmt="gdoc")
                full_text = docx_bytes_to_plain_text(content)
                snippet = extract_snippet(full_text, query, context_chars)
                if snippet is not None:
                    content_matches.append({
                        "id": d["id"],
                        "name": d["name"],
                        "raw_name": d["raw_name"],
                        "snippet": snippet,
                    })
            except Exception as e:
                # Не падаємо на одному файлі — продовжуємо пошук
                content_matches.append({
                    "id": d["id"],
                    "name": d["name"],
                    "error": str(e),
                })

    return {
        "scope": scope,
        "query": query,
        "total_name_matches": len(name_matches),
        "total_content_matches": len(content_matches),
        "name_matches": name_matches[:limit],
        "content_matches": content_matches[:limit],
    }

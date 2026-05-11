"""
Аналітичні функції — detect_conflicts, validate_id_format,
list_open_questions, session_changes.
"""

import re
from typing import Optional
from datetime import datetime

from parsers import user_stories as us_parser
from parsers import bug_report as bug_parser
from projects.worqen.config import (
    FORBIDDEN_TERMS,
    OBSOLETE_NUMBERS,
    OPEN_QUESTION_MARKERS,
)
import snapshot as snap


# ====================== detect_conflicts ======================


def _check_story_for_conflicts(s: dict) -> list[dict]:
    """Сканує одну сторі і повертає знайдені проблеми."""
    issues = []
    sid = s.get("ID") or "(no id)"

    text_fields = {
        "Title": s.get("Title") or "",
        "User Story": s.get("User Story") or "",
        "Acceptance Criteria": s.get("Acceptance Criteria") or "",
        "Edge Cases": s.get("Edge Cases") or "",
        "Dependencies": s.get("Dependencies") or "",
        "Notes": s.get("Notes") or "",
        "Related Decisions": s.get("Related Decisions") or "",
    }

    # 1. Заборонені терміни
    for field, text in text_fields.items():
        for term in FORBIDDEN_TERMS:
            if term in text:
                issues.append({
                    "story_id": sid,
                    "severity": "critical",
                    "type": "forbidden_term",
                    "field": field,
                    "issue": f"Знайдено '{term}'",
                    "snippet": _snippet_around(text, term),
                })

    # 2. Старі цифри
    for field, text in text_fields.items():
        text_low = text.lower()
        for old, hint in OBSOLETE_NUMBERS:
            if old.lower() in text_low:
                issues.append({
                    "story_id": sid,
                    "severity": "critical",
                    "type": "obsolete_number",
                    "field": field,
                    "issue": f"Стара цифра '{old}' — {hint}",
                    "snippet": _snippet_around(text, old),
                })

    # 3. AC без Given/When/Then
    ac = text_fields["Acceptance Criteria"]
    if ac and len(ac) > 30:
        has_gwt = any(
            marker in ac.lower()
            for marker in ["given", "якщо", "коли", "тоді", "when", "then"]
        )
        if not has_gwt:
            issues.append({
                "story_id": sid,
                "severity": "warning",
                "type": "ac_without_gwt",
                "field": "Acceptance Criteria",
                "issue": "AC не містить Given/When/Then маркерів",
                "snippet": ac[:120],
            })

    # 4. Реалізовано + Won't (логічна неузгодженість)
    if (s.get("Status") or "").lower() == "реалізовано" and \
       (s.get("Priority") or "").lower() == "won't":
        issues.append({
            "story_id": sid,
            "severity": "critical",
            "type": "status_priority_mismatch",
            "field": "Status/Priority",
            "issue": "Status='Реалізовано' + Priority='Won't' — логічна суперечність",
            "snippet": "",
        })

    # 5. Дублі у Dependencies
    deps = text_fields["Dependencies"]
    if deps:
        ids_in_deps = re.findall(r"US-\d{3,}", deps.upper())
        seen = set()
        dups = []
        for did in ids_in_deps:
            if did in seen:
                dups.append(did)
            seen.add(did)
        if dups:
            issues.append({
                "story_id": sid,
                "severity": "warning",
                "type": "duplicate_dependencies",
                "field": "Dependencies",
                "issue": f"Дублі ID: {', '.join(set(dups))}",
                "snippet": deps[:120],
            })

    return issues


def _snippet_around(text: str, term: str, context: int = 40) -> str:
    """Повертає фрагмент тексту навколо терміну."""
    pos = text.lower().find(term.lower())
    if pos == -1:
        return text[:80]
    start = max(0, pos - context)
    end = min(len(text), pos + len(term) + context)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def detect_conflicts(
    epic: Optional[str] = None,
    severity_min: str = "warning",
    limit: int = 20,
) -> dict:
    """
    Сканує всі сторі і повертає список проблем.

    severity_min: критичність порогу (critical / warning / info)
    limit: топ N знахідок з повним описом, решта — тільки ID
    """
    severity_levels = {"critical": 3, "warning": 2, "info": 1}
    min_level = severity_levels.get(severity_min, 2)

    all_issues = []
    for s in us_parser.get_raw_stories():
        all_issues.extend(_check_story_for_conflicts(s))

    # Фільтруємо за severity
    filtered = [
        i for i in all_issues
        if severity_levels.get(i["severity"], 0) >= min_level
    ]

    # Сортуємо: critical → warning → info, потім по story_id
    filtered.sort(key=lambda i: (
        -severity_levels.get(i["severity"], 0),
        i.get("story_id", ""),
    ))

    counts = {
        "critical": sum(1 for i in all_issues if i["severity"] == "critical"),
        "warning": sum(1 for i in all_issues if i["severity"] == "warning"),
        "info": sum(1 for i in all_issues if i["severity"] == "info"),
    }

    top = filtered[:limit]
    rest_ids = sorted({i["story_id"] for i in filtered[limit:]})

    return {
        "summary": counts,
        "shown_count": len(top),
        "total_filtered": len(filtered),
        "issues": top,
        "more_affected_stories": rest_ids,
    }


# ====================== validate_id_format ======================


def validate_id_format(entity: str = "us") -> dict:
    """
    Перевірка послідовності ID. entity: 'us' або 'bug'.
    Повертає пропуски, дублі, неправильний формат.
    """
    if entity == "us":
        items = us_parser.get_raw_stories()
        prefix = "US"
        get_id = lambda x: x.get("ID")
    elif entity == "bug":
        items = bug_parser.get_raw_bugs()
        prefix = "BUG"
        get_id = lambda x: x.get("ID")
    elif entity == "ficha":
        items = bug_parser.get_raw_ficha()
        prefix = "Ficha"
        get_id = lambda x: x.get("#")
    else:
        return {"error": f"Unknown entity '{entity}', expected 'us'/'bug'/'ficha'"}

    pattern = re.compile(rf"^{prefix}-(\d+)$", re.IGNORECASE)

    nums = []
    invalid = []
    raw_ids = []

    for item in items:
        rid = (get_id(item) or "").strip()
        raw_ids.append(rid)
        m = pattern.match(rid)
        if m:
            nums.append((int(m.group(1)), rid))
        else:
            if rid:
                invalid.append(rid)

    if not nums:
        return {
            "entity": entity,
            "total": len(items),
            "error": "No valid IDs found",
        }

    nums_only = [n for n, _ in nums]
    min_num = min(nums_only)
    max_num = max(nums_only)
    expected_range = set(range(min_num, max_num + 1))
    actual = set(nums_only)

    missing = sorted(expected_range - actual)

    seen = {}
    duplicates = []
    for n, rid in nums:
        if n in seen:
            duplicates.append(rid)
        seen[n] = rid

    return {
        "entity": entity,
        "total": len(items),
        "expected_range": f"{prefix}-{min_num:03d} to {prefix}-{max_num:03d}",
        "missing_ids": [f"{prefix}-{n:03d}" for n in missing],
        "duplicate_ids": duplicates,
        "invalid_format": invalid,
        "next_available": f"{prefix}-{max_num + 1:03d}",
    }


# ====================== list_open_questions ======================


def list_open_questions(epic: Optional[str] = None) -> dict:
    """
    Повертає сторі що чекають рішень PO.
    Групує по Epic + по типу маркера.
    """
    stories = us_parser.get_raw_stories()
    result = {
        "by_status_obgovorennya": [],
        "by_status_doopratsyuvannya_po": [],
        "by_marker_in_notes": [],
    }

    for s in stories:
        if epic and epic.upper() not in (s.get("Epic") or "").upper():
            continue

        status = (s.get("Status") or "").lower()
        notes = (s.get("Notes") or "")
        edge = (s.get("Edge Cases") or "")

        short = {
            "ID": s.get("ID"),
            "Epic": s.get("Epic"),
            "Title": s.get("Title"),
            "Priority": s.get("Priority"),
        }

        if "потрібно обговорення" in status:
            result["by_status_obgovorennya"].append(short)
            continue

        if "потрібно доопрацювати po" in status:
            result["by_status_doopratsyuvannya_po"].append(short)
            continue

        # Маркери у Notes / Edge Cases
        for marker in OPEN_QUESTION_MARKERS:
            if marker.lower() in notes.lower() or marker.lower() in edge.lower():
                short_with_marker = {**short, "marker": marker}
                result["by_marker_in_notes"].append(short_with_marker)
                break

    return {
        "summary": {
            "обговорення": len(result["by_status_obgovorennya"]),
            "доопрацювати_PO": len(result["by_status_doopratsyuvannya_po"]),
            "маркери_у_Notes": len(result["by_marker_in_notes"]),
        },
        "groups": result,
    }


# ====================== session_changes ======================


def make_current_snapshot() -> dict:
    """Створює знімок поточного стану xlsx-файлів."""
    return {
        "user_stories": us_parser.get_raw_stories(),
        "bugs": bug_parser.get_raw_bugs(),
        "ficha": bug_parser.get_raw_ficha(),
    }


def save_today_snapshot() -> str:
    """Зберігає поточний знімок як сьогоднішній."""
    data = make_current_snapshot()
    return snap.save_snapshot(data)


def session_changes(since_date: Optional[str] = None) -> dict:
    """
    Порівнює поточний стан зі знімком за since_date (або найсвіжішим попереднім).
    Повертає що змінилось.
    """
    prev = snap.load_snapshot(since_date)

    current = make_current_snapshot()

    if prev is None:
        # Немає попереднього снепшоту — зберігаємо поточний як baseline
        snap.save_snapshot(current)
        return {
            "info": "Не знайдено попереднього снепшоту. Поточний стан збережено як baseline.",
            "saved_today": True,
            "current_counts": {
                "user_stories": len(current["user_stories"]),
                "bugs": len(current["bugs"]),
                "ficha": len(current["ficha"]),
            },
        }

    prev_data = prev.get("data", {})

    diff = {
        "compared_to": prev.get("saved_at"),
        "user_stories": _diff_items(
            prev_data.get("user_stories", []), current["user_stories"], "ID"
        ),
        "bugs": _diff_items(
            prev_data.get("bugs", []), current["bugs"], "ID"
        ),
        "ficha": _diff_items(
            prev_data.get("ficha", []), current["ficha"], "#"
        ),
    }

    return diff


def _diff_items(prev: list[dict], current: list[dict], id_field: str) -> dict:
    """Порівнює два списки об'єктів за id_field."""
    prev_map = {(item.get(id_field) or ""): item for item in prev}
    curr_map = {(item.get(id_field) or ""): item for item in current}

    prev_ids = set(prev_map.keys())
    curr_ids = set(curr_map.keys())

    created = sorted(curr_ids - prev_ids)
    deleted = sorted(prev_ids - curr_ids)

    modified = []
    for cid in sorted(curr_ids & prev_ids):
        if not cid:
            continue
        if prev_map[cid] != curr_map[cid]:
            changed_fields = []
            for k in set(list(prev_map[cid].keys()) + list(curr_map[cid].keys())):
                if prev_map[cid].get(k) != curr_map[cid].get(k):
                    changed_fields.append(k)
            modified.append({
                "id": cid,
                "changed_fields": changed_fields,
            })

    return {
        "created": [
            {"id": cid, "title": curr_map[cid].get("Title") or curr_map[cid].get("Опис") or curr_map[cid].get("Назва")}
            for cid in created if cid
        ],
        "deleted": deleted,
        "modified": modified,
        "counts": {
            "created": len(created),
            "deleted": len(deleted),
            "modified": len(modified),
        },
    }


def list_snapshots() -> list[dict]:
    return snap.list_snapshots()

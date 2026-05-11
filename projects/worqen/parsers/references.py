"""
Сканування посилань на ID між US і BUG.

validate_references() повертає:
- missing_refs: [{from_id, from_file, field, ref_id, ref_type}]
- cycles: [[US-A, US-B, ..., US-A]]
- stats: загальні цифри

Регекс: US-\\d{3,4} і BUG-\\d{3,4} (case-insensitive).
"""

import re
from typing import Optional

from projects.worqen.parsers.user_stories import get_raw_stories
from projects.worqen.parsers.bug_report import get_raw_bugs


US_FIELDS_TO_SCAN = [
    "Dependencies",
    "Related Decisions",
    "Notes",
    "Acceptance Criteria",
    "Edge Cases",
]

BUG_FIELDS_TO_SCAN = [
    "Опис",
    "Очікувана поведінка",
    "Рекомендація для Романа",
    "Зафіксоване рішення",
    "Примітки",
]

# US/BUG NNN або NNNN
_US_REF = re.compile(r"US-(\d{3,4})", re.IGNORECASE)
_BUG_REF = re.compile(r"BUG-(\d{3,4})", re.IGNORECASE)


def _extract_refs(text: Optional[str]) -> list[tuple[str, str]]:
    """
    Витягує усі згадки US-NNN і BUG-NNN з тексту.
    Повертає список (ref_type, ref_id_normalized) — наприклад [("US","US-001"), ("BUG","BUG-024")].
    Дублі в межах одного тексту прибираються (нас цікавить факт згадки).
    """
    if not text:
        return []
    found: set[tuple[str, str]] = set()
    for m in _US_REF.finditer(text):
        num = int(m.group(1))
        found.add(("US", f"US-{num:03d}"))
    for m in _BUG_REF.finditer(text):
        num = int(m.group(1))
        found.add(("BUG", f"BUG-{num:03d}"))
    return sorted(found)


def _build_id_sets() -> tuple[set[str], set[str]]:
    """Повертає (existing_us_ids, existing_bug_ids) у нормалізованому форматі."""
    us_ids: set[str] = set()
    for s in get_raw_stories():
        sid = (s.get("ID") or "").strip()
        m = re.match(r"^US-(\d+)$", sid, re.IGNORECASE)
        if m:
            us_ids.add(f"US-{int(m.group(1)):03d}")

    bug_ids: set[str] = set()
    for b in get_raw_bugs():
        bid = (b.get("ID") or "").strip()
        m = re.match(r"^BUG-(\d+)$", bid, re.IGNORECASE)
        if m:
            bug_ids.add(f"BUG-{int(m.group(1)):03d}")

    return us_ids, bug_ids


def _normalize_own_id(raw_id: Optional[str], prefix: str) -> Optional[str]:
    if not raw_id:
        return None
    m = re.match(rf"^{prefix}-(\d+)$", raw_id.strip(), re.IGNORECASE)
    if not m:
        return None
    return f"{prefix}-{int(m.group(1)):03d}"


def _scan_records(
    records: list[dict],
    fields: list[str],
    own_prefix: str,
    existing_us: set[str],
    existing_bug: set[str],
) -> tuple[list[dict], int]:
    """
    Сканує список записів (US або BUG) по вказаних полях.
    Повертає (missing_refs_list, total_refs_found).
    """
    missing: list[dict] = []
    total_refs = 0
    own_file = "user_stories" if own_prefix == "US" else "qa_report"

    for rec in records:
        own_id = _normalize_own_id(rec.get("ID"), own_prefix)
        if not own_id:
            continue
        for field in fields:
            refs = _extract_refs(rec.get(field))
            for ref_type, ref_id in refs:
                total_refs += 1
                # Пропускаємо self-reference (запис сам себе згадує — це не broken)
                if ref_id == own_id:
                    continue
                pool = existing_us if ref_type == "US" else existing_bug
                if ref_id not in pool:
                    missing.append({
                        "from_id": own_id,
                        "from_file": own_file,
                        "field": field,
                        "ref_id": ref_id,
                        "ref_type": ref_type,
                    })
    return missing, total_refs


def _find_cycles_in_us_dependencies(records: list[dict]) -> list[list[str]]:
    """
    Знаходить циклічні залежності у Dependencies US.

    Алгоритм:
    1. Будуємо граф залежностей: id -> set of referenced US-IDs у Dependencies.
       Self-references виключаються (US-001 → US-001 не цикл).
    2. Через Tarjan SCC знаходимо strongly connected components.
    3. Для кожного SCC розміру ≥2 беремо ОДИН представницький цикл
       (BFS-шлях від однієї вершини до неї ж усередині SCC).
    4. Якщо SCC розміру 1 — це означає що self-loop, але ми його виключили
       на етапі побудови графа, тому таких циклів не буде.

    Це дає по одному циклу на кожен реальний кластер, без надлишку
    від комбінаторного перебору всіх можливих обходів.

    Повертає список циклів. Кожен цикл — список ID де перший == останній.
    """
    # CYCLES_FIX_V2 — переписано на Tarjan SCC + один цикл на SCC
    graph: dict[str, set[str]] = {}
    for rec in records:
        own = _normalize_own_id(rec.get("ID"), "US")
        if not own:
            continue
        deps = _extract_refs(rec.get("Dependencies"))
        # Беремо лише US-посилання, без self, без посилань на неіснуючі вузли
        graph[own] = {rid for (rtype, rid) in deps if rtype == "US" and rid != own}

    # Прибираємо з графа посилання на вузли яких немає у graph
    # (це broken refs — вони не утворюють цикл бо ведуть у нікуди)
    all_nodes = set(graph.keys())
    for node in list(graph.keys()):
        graph[node] = {n for n in graph[node] if n in all_nodes}

    # --- Tarjan SCC (ітеративний, щоб не впертись у recursion limit) ---
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    sccs: list[list[str]] = []

    def strongconnect(start: str) -> None:
        # Ітеративний DFS зі станом per-вузол
        work_stack: list[tuple[str, iter]] = []
        indices[start] = index_counter[0]
        lowlinks[start] = index_counter[0]
        index_counter[0] += 1
        stack.append(start)
        on_stack.add(start)
        work_stack.append((start, iter(graph.get(start, ()))))

        while work_stack:
            v, it = work_stack[-1]
            try:
                w = next(it)
            except StopIteration:
                # Завершили обхід сусідів v — закриваємо вузол
                # і оновлюємо lowlink батька
                work_stack.pop()
                if lowlinks[v] == indices[v]:
                    # Корінь SCC — витягуємо всі вершини стека до v включно
                    component: list[str] = []
                    while True:
                        w2 = stack.pop()
                        on_stack.discard(w2)
                        component.append(w2)
                        if w2 == v:
                            break
                    sccs.append(component)
                if work_stack:
                    parent = work_stack[-1][0]
                    if lowlinks[v] < lowlinks[parent]:
                        lowlinks[parent] = lowlinks[v]
                continue

            if w not in indices:
                indices[w] = index_counter[0]
                lowlinks[w] = index_counter[0]
                index_counter[0] += 1
                stack.append(w)
                on_stack.add(w)
                work_stack.append((w, iter(graph.get(w, ()))))
            elif w in on_stack:
                if indices[w] < lowlinks[v]:
                    lowlinks[v] = indices[w]

    for node in graph:
        if node not in indices:
            strongconnect(node)

    # --- Для кожного SCC розміру ≥2 знаходимо представницький цикл ---
    cycles: list[list[str]] = []
    for component in sccs:
        if len(component) < 2:
            continue
        scc_set = set(component)
        start_node = sorted(component)[0]  # детермінований вибір — лексикографічно найменший

        # BFS у підграфі обмеженому SCC, шукаємо найкоротший шлях start → start
        parent: dict[str, str] = {}
        from collections import deque
        queue = deque()
        # Стартові кроки — кожен сусід start у межах SCC
        for nxt in graph.get(start_node, ()):
            if nxt in scc_set:
                parent[nxt] = start_node
                queue.append(nxt)

        target = start_node
        found = None
        while queue:
            cur = queue.popleft()
            if cur == target:
                found = cur
                break
            for nxt in graph.get(cur, ()):
                if nxt not in scc_set:
                    continue
                if nxt == target:
                    parent[nxt] = cur
                    found = nxt
                    queue.clear()
                    break
                if nxt not in parent:
                    parent[nxt] = cur
                    queue.append(nxt)

        if found is None:
            # SCC розміру ≥2 але старт не повертається до себе?
            # Така ситуація неможлива в коректному SCC, але про всяк випадок.
            continue

        # Відновлюємо цикл.
        # target == start_node. parent[target] — це остання вершина шляху перед замиканням.
        # Йдемо назад: parent[target] → parent[parent[target]] → ... → start_node.
        # Тоді reverse, додаємо target (=start_node) у кінець для замикання.
        cycle: list[str] = []
        cur = parent[target]
        cycle.append(cur)
        while cur != start_node:
            cur = parent[cur]
            cycle.append(cur)
        # cycle: [last_before_target, ..., start_node]
        cycle.reverse()
        # cycle: [start_node, ..., last_before_target]
        cycle.append(start_node)  # замикання
        cycles.append(cycle)

    return cycles


def validate_references(
    check_us: bool = True,
    check_bug: bool = True,
    include_cycles: bool = True,
) -> dict:
    """
    Повний скан посилань.
    Повертає dict з missing_refs, cycles, stats.
    """
    existing_us, existing_bug = _build_id_sets()

    us_records = get_raw_stories() if check_us else []
    bug_records = get_raw_bugs() if check_bug else []

    missing_refs: list[dict] = []
    total_refs = 0

    if check_us:
        us_missing, us_total = _scan_records(
            us_records, US_FIELDS_TO_SCAN, "US", existing_us, existing_bug,
        )
        missing_refs.extend(us_missing)
        total_refs += us_total

    if check_bug:
        bug_missing, bug_total = _scan_records(
            bug_records, BUG_FIELDS_TO_SCAN, "BUG", existing_us, existing_bug,
        )
        missing_refs.extend(bug_missing)
        total_refs += bug_total

    cycles: list[list[str]] = []
    if include_cycles and check_us:
        cycles = _find_cycles_in_us_dependencies(us_records)

    return {
        "missing_refs": missing_refs,
        "cycles": cycles,
        "stats": {
            "total_us_scanned": len(us_records),
            "total_bug_scanned": len(bug_records),
            "total_refs_found": total_refs,
            "broken_count": len(missing_refs),
            "cycle_count": len(cycles),
            "us_fields_scanned": US_FIELDS_TO_SCAN if check_us else [],
            "bug_fields_scanned": BUG_FIELDS_TO_SCAN if check_bug else [],
        },
    }

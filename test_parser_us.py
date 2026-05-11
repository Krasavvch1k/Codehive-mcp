"""Швидкий smoke-тест парсера User Stories."""

from parsers.user_stories import (
    list_stories,
    get_story,
    get_next_us_id,
    list_epics_summary,
    find_dependents,
)


def main():
    print("=" * 60)
    print("ТЕСТ 1: Загальна кількість сторі")
    print("=" * 60)
    all_stories = list_stories()
    print(f"Всього сторі: {len(all_stories)}\n")

    print("=" * 60)
    print("ТЕСТ 2: Summary по епіках")
    print("=" * 60)
    summary = list_epics_summary()
    for epic, data in summary.items():
        print(f"  {epic}: {data['total']}")
    print()

    print("=" * 60)
    print("ТЕСТ 3: Сторі з статусом 'Не реалізовано' і пріоритетом 'Must'")
    print("=" * 60)
    must_todo = list_stories(status="Не реалізовано", priority="Must")
    print(f"Знайдено: {len(must_todo)}")
    for s in must_todo[:5]:
        print(f"  {s['ID']} [{s['Epic']}] {s['Title']}")
    if len(must_todo) > 5:
        print(f"  ... ще {len(must_todo) - 5}")
    print()

    print("=" * 60)
    print("ТЕСТ 4: Пошук однієї сторі (US-062)")
    print("=" * 60)
    s = get_story("US-062")
    if s:
        for k, v in s.items():
            v_short = (v[:80] + "...") if v and len(v) > 80 else v
            print(f"  {k}: {v_short}")
    else:
        print("  Не знайдено")
    print()

    print("=" * 60)
    print("ТЕСТ 5: Наступний вільний US-XXX")
    print("=" * 60)
    print(f"  {get_next_us_id()}")
    print()

    print("=" * 60)
    print("ТЕСТ 6: Хто залежить від US-061")
    print("=" * 60)
    deps = find_dependents("US-061")
    print(f"Знайдено: {len(deps)}")
    for s in deps:
        print(f"  {s['ID']} [{s['Epic']}] {s['Title']}")
    print()

    print("=" * 60)
    print("ТЕСТ 7: Пошук по слову 'Escrow'")
    print("=" * 60)
    found = list_stories(search="Escrow")
    print(f"Знайдено: {len(found)}")
    for s in found[:5]:
        print(f"  {s['ID']} [{s['Epic']}] {s['Title']}")
    if len(found) > 5:
        print(f"  ... ще {len(found) - 5}")


if __name__ == "__main__":
    main()

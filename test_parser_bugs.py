"""Smoke-тест парсера QA Report."""

from parsers.bug_report import (
    list_bugs,
    get_bug,
    get_next_bug_id,
    bugs_summary,
    list_ficha,
    get_ficha,
    get_next_ficha_id,
)


def main():
    print("=" * 60)
    print("ТЕСТ 1: Загальна кількість багів")
    print("=" * 60)
    all_bugs = list_bugs()
    print(f"Всього багів: {len(all_bugs)}\n")

    print("=" * 60)
    print("ТЕСТ 2: Зведена статистика")
    print("=" * 60)
    s = bugs_summary()
    print(f"Всього: {s['total']}")
    print("За пріоритетом:")
    for k, v in s["by_priority"].items():
        print(f"  {k}: {v}")
    print("За статусом:")
    for k, v in s["by_status"].items():
        print(f"  {k}: {v}")
    print("За типом:")
    for k, v in s["by_type"].items():
        print(f"  {k}: {v}")
    print("Перетин Пріоритет x Статус:")
    for pr, by_st in s["by_priority_status"].items():
        print(f"  {pr}:")
        for st, cnt in by_st.items():
            print(f"    {st}: {cnt}")
    print()

    print("=" * 60)
    print("ТЕСТ 3: P1 баги які треба зробити")
    print("=" * 60)
    p1_todo = list_bugs(priority="P1", status="Потрібно зробити")
    print(f"Знайдено: {len(p1_todo)}")
    for b in p1_todo[:5]:
        print(f"  {b['ID']} [{b['Тип']}] {b['Опис']}")
    if len(p1_todo) > 5:
        print(f"  ... ще {len(p1_todo) - 5}")
    print()

    print("=" * 60)
    print("ТЕСТ 4: Конкретний баг (BUG-001)")
    print("=" * 60)
    b = get_bug("BUG-001")
    if b:
        for k, v in b.items():
            v_short = (v[:80] + "...") if v and len(v) > 80 else v
            print(f"  {k}: {v_short}")
    else:
        print("  Не знайдено")
    print()

    print("=" * 60)
    print("ТЕСТ 5: Наступний BUG-XXX")
    print("=" * 60)
    print(f"  {get_next_bug_id()}")
    print()

    print("=" * 60)
    print("ТЕСТ 6: Пошук багів по слову 'KYC'")
    print("=" * 60)
    found = list_bugs(search="KYC")
    print(f"Знайдено: {len(found)}")
    for b in found[:5]:
        print(f"  {b['ID']} [{b['Пріоритет']}/{b['Статус']}] {b['Опис']}")
    if len(found) > 5:
        print(f"  ... ще {len(found) - 5}")
    print()

    print("=" * 60)
    print("ТЕСТ 7: Ficha — кількість і не перенесені")
    print("=" * 60)
    all_ficha = list_ficha()
    not_transferred = list_ficha(transferred=False)
    print(f"Всього Ficha: {len(all_ficha)}")
    print(f"Не перенесені в US: {len(not_transferred)}")
    for f in not_transferred[:5]:
        print(f"  {f['#']} [{f['Пріоритет']}] {f['Назва']}")
    if len(not_transferred) > 5:
        print(f"  ... ще {len(not_transferred) - 5}")
    print()

    print("=" * 60)
    print("ТЕСТ 8: Наступний Ficha-XXX")
    print("=" * 60)
    print(f"  {get_next_ficha_id()}")


if __name__ == "__main__":
    main()

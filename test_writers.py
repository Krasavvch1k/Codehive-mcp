"""
Smoke-тести для writers і нових parser-функцій.
Запуск: python test_writers.py [--missing-ids | --use-id-dryrun | ...]
"""

import sys
import argparse

from parsers.user_stories import (
    find_missing_us_ids,
    is_us_id_free,
    is_valid_us_id_format,
    get_next_us_id,
)
from parsers.bug_report import (
    find_missing_bug_ids,
    is_bug_id_free,
    is_valid_bug_id_format,
    get_next_bug_id,
)


def test_missing_ids():
    print("=== US missing IDs ===")
    missing_us = find_missing_us_ids()
    print(f"Знайдено {len(missing_us)} пропусків у US")
    if missing_us:
        print(f"Перші 20: {missing_us[:20]}")
    next_us = get_next_us_id()
    print(f"next_us_id (max+1): {next_us}")

    print()
    print("=== BUG missing IDs ===")
    missing_bug = find_missing_bug_ids()
    print(f"Знайдено {len(missing_bug)} пропусків у BUG")
    if missing_bug:
        print(f"Перші 20: {missing_bug[:20]}")
    next_bug = get_next_bug_id()
    print(f"next_bug_id (max+1): {next_bug}")


def test_id_format():
    print("=== Перевірка формату US ===")
    cases = [
        ("US-001", True),
        ("US-172", True),
        ("US-1000", True),
        ("us-001", True),
        ("US-1", False),
        ("US-A01", False),
        ("US001", False),
        ("BUG-001", False),
        ("", False),
        ("US-00001", False),
    ]
    for s, expected in cases:
        got = is_valid_us_id_format(s)
        mark = "OK" if got == expected else "FAIL"
        print(f"  {mark} '{s}' -> {got} (expected {expected})")

    print("=== Перевірка формату BUG ===")
    cases = [
        ("BUG-001", True),
        ("BUG-100", True),
        ("bug-001", True),
        ("BUG-1", False),
        ("US-001", False),
        ("", False),
    ]
    for s, expected in cases:
        got = is_valid_bug_id_format(s)
        mark = "OK" if got == expected else "FAIL"
        print(f"  {mark} '{s}' -> {got} (expected {expected})")


def test_id_free_check():
    print("=== is_us_id_free ===")
    missing = find_missing_us_ids()
    if missing:
        target = missing[0]
        is_free, title = is_us_id_free(target)
        print(f"  {target} is_free={is_free} title={title} (очікуємо is_free=True)")
    else:
        print("  Пропусків немає — нема чого тестувати на вільності")

    next_id = get_next_us_id()
    is_free, title = is_us_id_free(next_id)
    print(f"  {next_id} (next) is_free={is_free} (очікуємо True)")

    # Зайнятий ID — беремо US-001
    is_free, title = is_us_id_free("US-001")
    print(f"  US-001 is_free={is_free} title='{title}' (очікуємо False якщо існує)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--missing-ids", action="store_true")
    parser.add_argument("--id-format", action="store_true")
    parser.add_argument("--id-free", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.all or args.missing_ids:
        test_missing_ids()
        print()
    if args.all or args.id_format:
        test_id_format()
        print()
    if args.all or args.id_free:
        test_id_free_check()
        print()

    if not (args.missing_ids or args.id_format or args.id_free or args.all):
        parser.print_help()


if __name__ == "__main__":
    main()

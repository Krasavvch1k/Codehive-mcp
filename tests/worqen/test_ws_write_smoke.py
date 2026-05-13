"""
Smoke-тест для worqen_ws_* WRITE tools (Phase 2).

Майже всі тести використовують dry_run=True щоб НЕ писати у production
Worqen Drive. Перевіряється:
- Tools оголошені (всі 9 нових)
- Blacklist спрацьовує для US/BUG xlsx (помилка blacklisted_file_id)
- dry_run повертає preview без write
- A1-валідація відсіює невалідні комірки/діапазони
- Resolve спрацьовує (помилка resolve_failed для невідомих файлів)
- Невалідні параметри (format/values shape) спрацьовують

Запуск:
    cd ~/Documents/Codehive-mcp && python3 -m tests.worqen.test_ws_write_smoke

NB: тест НЕ виконує реальних writes — тільки dry_run і error-paths.
Для реальних writes — викликай tools руками через Claude Desktop і
перевіряй у Drive UI / writes_log.
"""

import sys

from projects.worqen.config import FILE_IDS
from projects.worqen.ws_tools import WORQEN_WS_TOOLS, ws_dispatch


def banner(text: str):
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def assert_dict(result, label: str) -> bool:
    if not isinstance(result, dict):
        print(f"  ❌ {label}: очікувався dict, отримано {type(result).__name__}")
        return False
    return True


def assert_no_error(result, label: str) -> bool:
    if not assert_dict(result, label):
        return False
    if "error" in result:
        print(f"  ❌ {label}: ERROR: {result['error']}")
        return False
    print(f"  ✅ {label}")
    return True


def assert_error_kind(result, expected_kind: str, label: str) -> bool:
    """Перевірка що повернулась помилка з конкретним kind."""
    if not assert_dict(result, label):
        return False
    if "error" not in result:
        print(f"  ❌ {label}: очікувалась помилка, отримано: {result}")
        return False
    actual_kind = result.get("kind", "")
    if actual_kind != expected_kind:
        print(
            f"  ❌ {label}: очікувався kind='{expected_kind}', "
            f"отримано kind='{actual_kind}', error='{result['error']}'"
        )
        return False
    print(f"  ✅ {label} (kind={actual_kind})")
    return True


def assert_dry_run(result, label: str) -> bool:
    """Перевірка що повернувся dry_run preview."""
    if not assert_dict(result, label):
        return False
    if result.get("dry_run") is not True:
        print(f"  ❌ {label}: очікувався dry_run=True у result, отримано: {result}")
        return False
    if not result.get("would_write") and not result.get("would_create"):
        print(
            f"  ⚠️  {label}: dry_run без would_write/would_create — "
            f"можливо помилка у preview structure"
        )
    print(f"  ✅ {label} (dry_run preview OK)")
    return True


def main():
    failures = 0

    # ----- 1. Tool definitions -----
    banner("1. Усі 15 ws-tools зареєстровані (6 read + 9 write)")
    print(f"  Total: {len(WORQEN_WS_TOOLS)}")
    expected_write_tools = {
        "worqen_ws_replace_text",
        "worqen_ws_insert_text",
        "worqen_ws_replace_section",
        "worqen_ws_update_cell",
        "worqen_ws_update_range",
        "worqen_ws_append_row",
        "worqen_ws_create_doc",
        "worqen_ws_create_sheet",
        "worqen_ws_create_folder",
    }
    actual = {t.name for t in WORQEN_WS_TOOLS}
    missing = expected_write_tools - actual
    if missing:
        print(f"  ❌ Не зареєстровано: {missing}")
        failures += 1
    else:
        print(f"  ✅ Усі 9 нових write tools є")
    if len(WORQEN_WS_TOOLS) != 15:
        print(f"  ❌ Очікувалось 15 tools, є {len(WORQEN_WS_TOOLS)}")
        failures += 1

    # ----- 2. Blacklist: спроба write у US xlsx -----
    banner("2. Blacklist: ws_update_cell на User_Stories — має бути заборонено")
    result = ws_dispatch(
        "worqen_ws_update_cell",
        {
            "query": "User_Stories",
            "sheet": "User_Stories",
            "cell": "A1",
            "value": "BLOCKED_BY_BLACKLIST",
        },
    )
    if not assert_error_kind(result, "blacklisted_file_id", "blacklist US"):
        failures += 1

    # ----- 3. Blacklist: спроба write у BUG xlsx -----
    banner("3. Blacklist: ws_append_row на QA_Report — має бути заборонено")
    result = ws_dispatch(
        "worqen_ws_append_row",
        {
            "query": "QA_Full_Report",
            "sheet": "Bugs",
            "values": ["BLOCKED", "BY", "BLACKLIST"],
        },
    )
    if not assert_error_kind(result, "blacklisted_file_id", "blacklist BUG"):
        failures += 1

    # ----- 4. dry_run: replace_text у PRD v2 -----
    banner("4. dry_run: ws_replace_text у PRD v2 (точна назва щоб уникнути ambiguous)")
    result = ws_dispatch(
        "worqen_ws_replace_text",
        {
            "query": "Worqen_PRD_v2.docx",
            "old_text": "fake_text_will_not_be_found_anyway_dry_run",
            "new_text": "replacement",
            "dry_run": True,
        },
    )
    if not assert_dry_run(result, "dry_run replace_text PRD v2"):
        failures += 1
    else:
        print(f"  file: {result.get('file_name')} kind={result.get('kind')}")

    # ----- 5. dry_run: insert_text end_of_doc -----
    banner("5. dry_run: ws_insert_text(mode=end_of_doc) у PRD v2")
    result = ws_dispatch(
        "worqen_ws_insert_text",
        {
            "query": "Worqen_PRD_v2.docx",
            "text": "Test paragraph",
            "mode": "end_of_doc",
            "dry_run": True,
        },
    )
    if not assert_dry_run(result, "dry_run insert_text end_of_doc"):
        failures += 1

    # ----- 6. dry_run: update_cell на gsheet (People board) -----
    banner("6. dry_run: ws_update_cell на People board")
    result = ws_dispatch(
        "worqen_ws_update_cell",
        {
            "query": "People board",
            "sheet": "Sheet1",
            "cell": "A1",
            "value": "TEST_VALUE",
            "dry_run": True,
        },
    )
    if not assert_dry_run(result, "dry_run update_cell gsheet"):
        failures += 1

    # ----- 7. A1 validation: невалідна комірка -----
    banner("7. A1 validation: cell='not-an-a1' має бути invalid_a1")
    result = ws_dispatch(
        "worqen_ws_update_cell",
        {
            "query": "People board",
            "sheet": "Sheet1",
            "cell": "not-an-a1",
            "value": "X",
            "dry_run": True,
        },
    )
    if not assert_error_kind(result, "invalid_a1", "invalid A1 cell"):
        failures += 1

    # ----- 8. A1 validation: невалідний діапазон -----
    banner("8. A1 validation: range='A1' (без двокрапки) — invalid_a1")
    result = ws_dispatch(
        "worqen_ws_update_range",
        {
            "query": "People board",
            "sheet": "Sheet1",
            "range": "A1",  # повинен бути A1:B2
            "values": [["x"]],
            "dry_run": True,
        },
    )
    if not assert_error_kind(result, "invalid_a1", "invalid A1 range"):
        failures += 1

    # ----- 9. Resolve failure для неіснуючого файлу -----
    banner("9. Resolve: query='non_existent_file_xyz_abc' — resolve_failed")
    result = ws_dispatch(
        "worqen_ws_replace_text",
        {
            "query": "non_existent_file_xyz_abc",
            "old_text": "x",
            "new_text": "y",
            "dry_run": True,
        },
    )
    if not assert_error_kind(result, "resolve_failed", "resolve non-existent"):
        failures += 1

    # ----- 10. append_row: 2D values замість 1D — invalid_values -----
    banner("10. append_row з 2D values — має бути invalid_values")
    result = ws_dispatch(
        "worqen_ws_append_row",
        {
            "query": "People board",
            "sheet": "Sheet1",
            "values": [["nested", "list"]],  # 2D — заборонено для append_row
            "dry_run": True,
        },
    )
    if not assert_error_kind(result, "invalid_values", "append_row 2D rejection"):
        failures += 1

    # ----- 11. create_doc invalid format -----
    banner("11. create_doc з format='pdf' — invalid_format")
    result = ws_dispatch(
        "worqen_ws_create_doc",
        {"name": "test_doc", "format": "pdf", "dry_run": True},
    )
    if not assert_error_kind(result, "invalid_format", "create_doc bad format"):
        failures += 1

    # ----- 12. dry_run: create_doc -----
    banner("12. dry_run: ws_create_doc у root Worqen")
    result = ws_dispatch(
        "worqen_ws_create_doc",
        {
            "name": "test_doc_dry_run_only",
            "format": "gdoc",
            "initial_content": "Hello",
            "dry_run": True,
        },
    )
    if not assert_dry_run(result, "dry_run create_doc"):
        failures += 1
    else:
        print(f"  parent: {result.get('parent_folder_name')}")

    # ----- 13. dry_run: create_folder -----
    banner("13. dry_run: ws_create_folder")
    result = ws_dispatch(
        "worqen_ws_create_folder",
        {"name": "test_folder_dry_run_only", "dry_run": True},
    )
    if not assert_dry_run(result, "dry_run create_folder"):
        failures += 1

    # ----- 14. replace_section stub -----
    banner("14. ws_replace_section — заглушка not_implemented")
    result = ws_dispatch(
        "worqen_ws_replace_section",
        {
            "query": "Worqen_PRD_v2.docx",
            "heading": "## Test",
            "new_content": "x",
            "dry_run": True,
        },
    )
    if not assert_error_kind(result, "not_implemented", "replace_section stub"):
        failures += 1

    # ----- 15. Sanity: blacklist size = 2 -----
    banner("15. WRITE_BLACKLIST_FILE_IDS sanity")
    from projects.worqen.config import WRITE_BLACKLIST_FILE_IDS

    if len(WRITE_BLACKLIST_FILE_IDS) != 2:
        print(f"  ❌ blacklist size = {len(WRITE_BLACKLIST_FILE_IDS)}, очікувалось 2")
        failures += 1
    elif FILE_IDS["user_stories"] not in WRITE_BLACKLIST_FILE_IDS:
        print(f"  ❌ user_stories не у blacklist")
        failures += 1
    elif FILE_IDS["qa_report"] not in WRITE_BLACKLIST_FILE_IDS:
        print(f"  ❌ qa_report не у blacklist")
        failures += 1
    else:
        print(f"  ✅ blacklist містить user_stories і qa_report")

    # ----- Підсумок -----
    banner(f"DONE — failures: {failures}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()

"""
Smoke-тест для worqen_ws_* tools.

Не використовує MCP transport — викликає функції напряму. Призначений
для запуску локально перед commit-ом щоб переконатись що нічого не зламано.

Запуск:
    cd ~/Documents/Codehive-mcp && python3 -m tests.worqen.test_ws_smoke
"""

import json
import sys

from projects.worqen.ws_tools import WORQEN_WS_TOOLS, ws_dispatch


def banner(text: str):
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def assert_no_error(result, label: str):
    if isinstance(result, dict) and "error" in result:
        print(f"  ❌ {label}: ERROR: {result['error']}")
        return False
    print(f"  ✅ {label}")
    return True


def main():
    failures = 0

    # 1. Tools оголошені
    banner("1. Tool definitions")
    print(f"  Total ws-tools: {len(WORQEN_WS_TOOLS)}")
    for t in WORQEN_WS_TOOLS:
        print(f"  - {t.name}")
    if len(WORQEN_WS_TOOLS) != 6:
        print(f"  ❌ Очікувалось 6 tools, є {len(WORQEN_WS_TOOLS)}")
        failures += 1

    # 2. list_folder (root)
    banner("2. worqen_ws_list_folder (root)")
    result = ws_dispatch("worqen_ws_list_folder", {})
    if not assert_no_error(result, "list_folder"):
        failures += 1
    else:
        print(f"  folder_name: {result.get('folder_name')}")
        print(f"  folders: {result.get('folders_count')}, docs: {result.get('docs_count')}")
        if result.get("folder_name") != "Worqen":
            print(f"  ⚠️  Очікувалось folder_name='Worqen', отримано '{result.get('folder_name')}'")

    # 3. list_all (depth=2)
    banner("3. worqen_ws_list_all (depth=2)")
    result = ws_dispatch("worqen_ws_list_all", {"max_depth": 2})
    if not assert_no_error(result, "list_all"):
        failures += 1
    else:
        print(f"  root_folder_name: {result.get('root_folder_name')}")
        print(f"  total_folders: {result.get('total_folders')}")
        print(f"  total_docs: {result.get('total_docs')}")
        print("  Sample items (first 5):")
        for item in result.get("items", [])[:5]:
            print(f"    [{item['kind']:>8}] {item['path']}")

    # 4. resolve — за відомою назвою
    banner("4. worqen_ws_resolve('User_Stories')")
    result = ws_dispatch("worqen_ws_resolve", {"query": "User_Stories"})
    if not assert_no_error(result, "resolve"):
        failures += 1
    else:
        print(f"  name: {result.get('name')}")
        print(f"  kind: {result.get('kind')}")
        print(f"  path: {result.get('path')}")

    # 5. read_doc — pinned gdoc (PRD v2 з кореня — точна назва щоб не матчити стару версію)
    banner("5. worqen_ws_read_doc('Worqen_PRD_v2.docx')")
    result = ws_dispatch("worqen_ws_read_doc", {"query": "Worqen_PRD_v2.docx"})
    if not assert_no_error(result, "read_doc PRD v2"):
        failures += 1
    else:
        print(f"  name: {result.get('name')}")
        print(f"  length: {result.get('length')} chars")
        text = result.get("text", "")
        print(f"  first 200 chars: {text[:200]!r}")

    # 5b. Перевіряємо що ambiguous query повертає error з підказкою
    banner("5b. worqen_ws_read_doc('PRD_v2') — очікувано ambiguous")
    result = ws_dispatch("worqen_ws_read_doc", {"query": "PRD_v2"})
    if isinstance(result, dict) and "error" in result and "матчить" in result["error"]:
        print(f"  ✅ Правильно повертає error з підказкою про дублі")
    else:
        print(f"  ❌ Очікувався ambiguous-error, отримано: {result}")
        failures += 1

    # 6. read_sheet — pinned xlsx (User Stories)
    banner("6. worqen_ws_read_sheet('User_Stories', limit_rows=3)")
    result = ws_dispatch(
        "worqen_ws_read_sheet",
        {"query": "User_Stories", "limit_rows": 3, "limit_cols": 8},
    )
    if not assert_no_error(result, "read_sheet xlsx"):
        failures += 1
    else:
        print(f"  name: {result.get('name')}")
        print(f"  kind: {result.get('kind')}")
        print(f"  sheets total: {len(result.get('sheets_meta', []))}")
        for s in result.get("sheets_data", [])[:3]:
            print(
                f"  sheet '{s.get('title')}': rows_returned={s.get('rows_returned')}, "
                f"cols_returned={s.get('cols_returned')}"
            )

    # 7. read_sheet — gsheet (People board)
    banner("7. worqen_ws_read_sheet('People board', limit_rows=5)")
    result = ws_dispatch(
        "worqen_ws_read_sheet",
        {"query": "People board", "limit_rows": 5, "limit_cols": 6},
    )
    if not assert_no_error(result, "read_sheet gsheet"):
        failures += 1
    else:
        print(f"  kind: {result.get('kind')}")
        print(f"  sheets meta: {[s.get('title') for s in result.get('sheets_meta', [])]}")
        for s in result.get("sheets_data", [])[:1]:
            md = s.get("markdown", "")
            print(f"  markdown sample:\n{md[:400]}")

    # 8. force_refresh — повне скидання
    banner("8. worqen_ws_force_refresh (all)")
    result = ws_dispatch("worqen_ws_force_refresh", {})
    if not assert_no_error(result, "force_refresh all"):
        failures += 1
    else:
        print(f"  cleared: {result.get('cleared')}")

    # Підсумок
    banner(f"DONE — failures: {failures}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()

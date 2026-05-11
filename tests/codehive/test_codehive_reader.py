"""Smoke test for the Codehive reader. Requires CODEHIVE_ROOT_FOLDER_ID in .env."""

import sys
from projects.codehive import gdoc_reader
from projects.codehive.config import CODEHIVE_ROOT_FOLDER_ID


def fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def ok(msg):
    print(f"[OK] {msg}")


def main():
    if not CODEHIVE_ROOT_FOLDER_ID:
        fail("CODEHIVE_ROOT_FOLDER_ID is empty in .env")
    ok(f"CODEHIVE_ROOT_FOLDER_ID = {CODEHIVE_ROOT_FOLDER_ID[:12]}...")

    print("\n--- 2. list_folder (root) ---")
    root = gdoc_reader.list_folder()
    print(f"   folder_name: {root['folder_name']}")
    print(f"   folders: {root['folders_count']}, docs: {root['docs_count']}")
    for f in root["folders"]:
        print(f"     [folder] {f['name']}")
    for d in root["docs"][:5]:
        print(f"     [{d['kind']}] {d['name']}")

    if root["folders_count"] == 0 and root["docs_count"] == 0:
        fail("CodeHive Agency root is empty")
    ok("Root has content")

    print("\n--- 3. list_all_docs (max_depth=3) ---")
    all_data = gdoc_reader.list_all_docs(max_depth=3)
    print(f"   root_folder_name: {all_data['root_folder_name']}")
    print(f"   total_folders: {all_data['total_folders']}")
    print(f"   total_docs: {all_data['total_docs']}")
    if all_data["total_folders"] == 0:
        fail("Recursive traversal found no subfolders")
    ok(f"Found {all_data['total_folders']} folders, {all_data['total_docs']} docs")

    print("   First 15 items:")
    for it in all_data["items"][:15]:
        print(f"     [{it['kind']}] {it['path']}")

    print("\n--- 4. search names 'site' ---")
    sr = gdoc_reader.search("site", scope="names", limit=5)
    print(f"   total_name_matches: {sr['total_name_matches']}")
    for m in sr["name_matches"]:
        print(f"     [{m['kind']}] {m['path']}")

    print("\n--- 5. read_doc test (10.05.2026) ---")
    try:
        doc = gdoc_reader.read_doc("10.05.2026")
        print(f"   name: {doc['name']}")
        print(f"   path: {doc['path']}")
        print(f"   length: {doc['length']} chars")
        preview = (doc["text"][:300] or "(empty)").replace("\n", "\n      ")
        print(f"   preview:\n      {preview}")
        ok(f"read_doc returned {doc['length']} chars")
    except ValueError as e:
        print(f"   [warn] {e}")
        print("   Try codehive_list_all_docs for exact names.")

    print("\n[DONE] basic checks complete")


if __name__ == "__main__":
    main()

"""
Знаходить ID робочих файлів Worqen у Drive (включно з Shared drives)
і виводить їх у форматі готовому до копіювання у config.py.
"""

from googleapiclient.discovery import build
from test_drive import get_credentials

FILES_TO_FIND = {
    "tech_doc": "Worqen_Technical_Documentation",
    "user_stories": "Worqen_User_Stories",
    "roadmap": "Worqen_Roadmap_2026",
    "qa_report": "Worqen_QA_Full_Report",
    "prd_bootstrap": "WorQen_PRD_Bootstrap_Edition",
    "prd_v1_1": "Worqen_PRD_v1_1",
}


def main():
    creds = get_credentials()
    service = build("drive", "v3", credentials=creds)

    print("Шукаю файли Worqen на Drive...\n")
    found = {}

    for key, name_part in FILES_TO_FIND.items():
        query = f"name contains '{name_part}' and trashed = false"

        results = (
            service.files()
            .list(
                q=query,
                pageSize=10,
                fields="files(id, name, mimeType, modifiedTime, parents, driveId)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="allDrives",
            )
            .execute()
        )

        files = results.get("files", [])

        if not files:
            print(f"NOT FOUND: {key} ({name_part})")
            continue

        if len(files) > 1:
            print(f"MULTIPLE: {key} ({name_part}): {len(files)} files:")
            for f in files:
                print(f"     - {f['name']} (id: {f['id']}, modified: {f['modifiedTime']})")
            files.sort(key=lambda x: x["modifiedTime"], reverse=True)
            print(f"   Taking newest: {files[0]['name']}")

        f = files[0]
        found[key] = {
            "id": f["id"],
            "name": f["name"],
            "mimeType": f["mimeType"],
        }
        print(f"OK: {key}: {f['name']}")
        print(f"   ID: {f['id']}")
        print(f"   Type: {f['mimeType']}")
        print()

    print("=" * 60)
    print("RESULT for config.py:")
    print("=" * 60)
    print()
    print("FILE_IDS = {")
    for key, info in found.items():
        print(f'    "{key}": "{info["id"]}",  # {info["name"]}')
    print("}")
    print()

    missing = set(FILES_TO_FIND.keys()) - set(found.keys())
    if missing:
        print(f"Missing: {', '.join(missing)}")
    else:
        print("All files found.")


if __name__ == "__main__":
    main()

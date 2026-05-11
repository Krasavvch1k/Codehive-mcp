"""
Smoke-скрипт OAuth: перевіряє credentials і виводить список перших 10 файлів до яких є доступ.

Production-код (drive_client) тепер імпортує get_credentials з shared.auth.
Цей файл — лише живий smoke-тест.
"""

from googleapiclient.discovery import build

from shared.auth import get_credentials


def main():
    print("Авторизуюсь з Google Drive...")
    creds = get_credentials()
    print("Авторизація успішна!\n")

    service = build("drive", "v3", credentials=creds)

    print("Перші 10 файлів до яких є доступ:")
    print("-" * 60)

    results = (
        service.files()
        .list(
            pageSize=10,
            fields="files(id, name, mimeType, modifiedTime)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )

    files = results.get("files", [])
    if not files:
        print("Файлів не знайдено.")
        return

    for f in files:
        print(f"  {f['name']}")
        print(f"    ID: {f['id']}")
        print(f"    Тип: {f['mimeType']}")
        print(f"    Змінено: {f['modifiedTime']}")
        print()


if __name__ == "__main__":
    main()

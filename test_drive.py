"""
Тестовий скрипт: перевіряє OAuth до Google Drive
і виводить список перших 10 файлів до яких є доступ.
"""

import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes — що ми хочемо могти робити
# readonly = тільки читання, без права запису
SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_credentials():
    """Отримує OAuth credentials. Перший запуск відкриває браузер."""
    creds = None

    # Якщо токен вже зберігали — завантажуємо
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # Якщо немає або неактуальні — оновлюємо або просимо заново
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Зберігаємо токен на майбутнє
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return creds


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
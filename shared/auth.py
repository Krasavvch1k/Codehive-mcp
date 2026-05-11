"""OAuth credentials for Google Drive API.

Provides get_credentials() used by drive_client and bootstrap scripts.
Reads/writes token.json and credentials.json in the current working directory.
"""

import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


# Scopes — що ми хочемо могти робити
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

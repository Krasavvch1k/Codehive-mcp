"""
Спільна конфігурація MCP-сервера CodeHive.

Імпортується першим у графі — тут живе load_dotenv, тому ENV vars стають
доступні для shared.auth і всіх projects.* модулів.
"""

import os

from dotenv import load_dotenv

# Завантажуємо .env з кореня проєкту
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_DIR, '.env'))

# ----- Кеш -----

CACHE_TTL_SECONDS = 30

# ----- Pagination -----

DEFAULT_LIST_LIMIT = 100
MAX_LIST_LIMIT = 500
TABLE_FORMAT_THRESHOLD = 20

# ----- Snapshot -----

SNAPSHOT_DIR = os.path.join(PROJECT_DIR, "snapshots")
SNAPSHOT_RETENTION_DAYS = 30

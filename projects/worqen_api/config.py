"""Конфігурація для worqen_api проєкту.

Read-only інспекція OpenAPI спеки Worqen Backend Dev (https://dev.api.worqen.com).
Зараз — БЕЗ авторизації і HTTP-викликів. Тільки читання openapi.json.
"""

import os
from pathlib import Path

# URL базового API і де лежить openapi.json
API_BASE_URL = "https://dev.api.worqen.com"
SPEC_URL = f"{API_BASE_URL}/openapi.json"

# Кеш — поряд з іншим runtime-state codebase, але у gitignored теці
CACHE_DIR = Path(__file__).resolve().parents[2] / "cache"
SPEC_CACHE_PATH = CACHE_DIR / "worqen_openapi.json"

# Таймаут на refresh — бачили що бекенд інколи висить до 90s
SPEC_FETCH_TIMEOUT_SECONDS = 120

# Скільки символів максимум повертати у inspect-відповіді для одного endpoint-а
# (щоб не залити Claude мегабайтом JSON-у при попаданні на пухкий response schema)
MAX_RESPONSE_CHARS = 20_000

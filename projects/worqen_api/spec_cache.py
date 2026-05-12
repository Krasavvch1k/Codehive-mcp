"""Кешований доступ до openapi.json Worqen Backend Dev.

Логіка:
- На старті — читаємо локальний кеш якщо є.
- Якщо нема — fetch і зберігаємо.
- Refresh — лише через явний виклик worqen_api_refresh_spec.

Чому не auto-refresh: бекенд інколи віддає 26-90s response або partial file.
Не хочемо щоб MCP сервер на старті висів через повільний upstream.
"""

import json
import urllib.request
from typing import Any

from projects.worqen_api.config import (
    CACHE_DIR,
    SPEC_CACHE_PATH,
    SPEC_FETCH_TIMEOUT_SECONDS,
    SPEC_URL,
)


def _fetch_from_network() -> dict[str, Any]:
    """Завантажує openapi.json з upstream і повертає parsed JSON."""
    req = urllib.request.Request(
        SPEC_URL,
        headers={"User-Agent": "codehive-mcp/worqen_api_inspector"},
    )
    with urllib.request.urlopen(req, timeout=SPEC_FETCH_TIMEOUT_SECONDS) as resp:
        raw = resp.read()
    return json.loads(raw)


def _save_to_cache(spec: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SPEC_CACHE_PATH.write_text(json.dumps(spec), encoding="utf-8")


def _load_from_cache() -> dict[str, Any] | None:
    if not SPEC_CACHE_PATH.exists():
        return None
    try:
        return json.loads(SPEC_CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def get_spec() -> dict[str, Any]:
    """Повертає openapi spec. Спочатку — кеш, fallback — мережа.

    Якщо мережа недоступна і кешу нема — raises RuntimeError.
    """
    cached = _load_from_cache()
    if cached is not None:
        return cached

    spec = _fetch_from_network()
    _save_to_cache(spec)
    return spec


def refresh_spec() -> dict[str, Any]:
    """Примусово завантажує свіжу спеку з upstream, зберігає у кеш, повертає.

    Викликається з MCP tool worqen_api_refresh_spec.
    """
    spec = _fetch_from_network()
    _save_to_cache(spec)
    return spec

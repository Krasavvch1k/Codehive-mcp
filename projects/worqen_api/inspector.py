"""Інспектор openapi.json для Worqen Backend Dev.

Read-only логіка — нічого не пишемо у upstream API, тільки читаємо
закешований openapi.json і повертаємо структуровану відповідь.

Public API:
    inspect(mode, query) -> dict

Контракт повернення (єдиний для всіх mode):
    success → {"data": {...}}
    failure → {"error": "...", "candidates"?: [...]}

Modes:
    "overview" — title/version/totals (skips query)
    "tags"     — список tags з кількістю endpoint-ів і GET у кожному
    "by_tag"   — endpoint-и одного тагу (query = tag name, case-insensitive)
    "endpoint" — повна схема ОДНОГО endpoint-а (query = "METHOD /path")
    "schema"   — повна схема одного component schema (query = ім'я)
    "search"   — fuzzy пошук у summary/description/path/operationId
"""

import json
from typing import Any

from projects.worqen_api.config import MAX_RESPONSE_CHARS
from projects.worqen_api.spec_cache import get_spec

VALID_MODES = ("overview", "tags", "by_tag", "endpoint", "schema", "search")
_HTTP_METHODS = ("get", "post", "put", "patch", "delete")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def inspect(mode: str, query: str = "") -> dict[str, Any]:
    """Dispatcher. Усі гілки повертають єдиний формат {data:...} | {error:...}."""
    if mode not in VALID_MODES:
        return {
            "error": (
                f"Невідомий mode='{mode}'. Допустимі: {', '.join(VALID_MODES)}."
            )
        }

    spec = get_spec()

    if mode == "overview":
        return _overview(spec)
    if mode == "tags":
        return _tags(spec)
    if mode == "by_tag":
        if not query:
            return {"error": "mode='by_tag' вимагає query (назва тагу)."}
        return _by_tag(spec, query)
    if mode == "endpoint":
        if not query:
            return {
                "error": (
                    "mode='endpoint' вимагає query у форматі 'METHOD /path', "
                    "наприклад 'GET /api/v1/milestones'."
                )
            }
        return _endpoint(spec, query)
    if mode == "schema":
        if not query:
            return {"error": "mode='schema' вимагає query (назва schema component)."}
        return _schema(spec, query)
    if mode == "search":
        if not query:
            return {"error": "mode='search' вимагає query (вільний текст)."}
        return _search(spec, query)

    # Технічно недосяжно через VALID_MODES guard
    return {"error": "unreachable"}


# ---------------------------------------------------------------------------
# Mode handlers — кожен повертає {"data": ...} або {"error": ...}
# ---------------------------------------------------------------------------


def _overview(spec: dict[str, Any]) -> dict[str, Any]:
    info = spec.get("info", {}) or {}
    paths = spec.get("paths", {}) or {}
    schemas = (spec.get("components") or {}).get("schemas") or {}
    security_schemes = (spec.get("components") or {}).get("securitySchemes") or {}

    methods_count: dict[str, int] = {}
    tags_set: set[str] = set()
    total_ops = 0

    for path, ops in paths.items():
        for method, op in ops.items():
            if method not in _HTTP_METHODS:
                continue
            total_ops += 1
            methods_count[method] = methods_count.get(method, 0) + 1
            for tag in op.get("tags") or ["(no tag)"]:
                tags_set.add(tag)

    return {
        "data": {
            "title": info.get("title"),
            "version": info.get("version"),
            "openapi": spec.get("openapi"),
            "totals": {
                "paths": len(paths),
                "operations": total_ops,
                "schemas": len(schemas),
                "tags": len(tags_set),
            },
            "methods": methods_count,
            "security_schemes": list(security_schemes.keys()),
        }
    }


def _tags(spec: dict[str, Any]) -> dict[str, Any]:
    paths = spec.get("paths", {}) or {}
    stats: dict[str, dict[str, int]] = {}

    for path, ops in paths.items():
        for method, op in ops.items():
            if method not in _HTTP_METHODS:
                continue
            for tag in op.get("tags") or ["(no tag)"]:
                entry = stats.setdefault(tag, {"total": 0, "get": 0})
                entry["total"] += 1
                if method == "get":
                    entry["get"] += 1

    items = [
        {"tag": t, "total": s["total"], "get": s["get"]}
        for t, s in sorted(stats.items(), key=lambda kv: -kv[1]["total"])
    ]
    return {"data": {"tags": items, "count": len(items)}}


def _by_tag(spec: dict[str, Any], query: str) -> dict[str, Any]:
    paths = spec.get("paths", {}) or {}
    query_lower = query.strip().lower()

    all_tags: set[str] = set()
    for ops in paths.values():
        for method, op in ops.items():
            if method in _HTTP_METHODS:
                for tag in op.get("tags") or []:
                    all_tags.add(tag)

    exact = [t for t in all_tags if t.lower() == query_lower]
    if exact:
        matched_tags = exact
    else:
        matched_tags = [t for t in all_tags if query_lower in t.lower()]
        if not matched_tags:
            return {
                "error": (
                    f"Не знайдено тагу за query='{query}'. "
                    "Спробуй mode='tags' щоб побачити список."
                )
            }

    if len(matched_tags) > 1:
        return {
            "error": (
                f"query='{query}' матчить кілька тагів: "
                f"{', '.join(sorted(matched_tags))}. Уточни."
            ),
            "candidates": sorted(matched_tags),
        }

    tag = matched_tags[0]
    endpoints = []
    for path, ops in paths.items():
        for method, op in ops.items():
            if method not in _HTTP_METHODS:
                continue
            if tag in (op.get("tags") or []):
                endpoints.append(
                    {
                        "method": method.upper(),
                        "path": path,
                        "summary": op.get("summary") or "",
                        "operationId": op.get("operationId"),
                        "deprecated": op.get("deprecated", False),
                    }
                )

    endpoints.sort(key=lambda e: (e["path"], e["method"]))
    return {"data": {"tag": tag, "count": len(endpoints), "endpoints": endpoints}}


def _endpoint(spec: dict[str, Any], query: str) -> dict[str, Any]:
    parsed = _parse_method_path(query)
    if parsed is None:
        return {
            "error": (
                f"query='{query}' не схожий на 'METHOD /path'. "
                "Приклад: 'GET /api/v1/milestones'."
            )
        }
    method, path = parsed

    paths = spec.get("paths", {}) or {}
    ops = paths.get(path)
    if ops is None:
        candidates = _find_path_candidates(paths.keys(), path)
        return {
            "error": f"Path '{path}' не знайдено у openapi.",
            "candidates": candidates[:10],
        }

    op = ops.get(method)
    if op is None:
        available = sorted(m.upper() for m in ops.keys() if m in _HTTP_METHODS)
        return {
            "error": (
                f"Method '{method.upper()}' відсутній для '{path}'. "
                f"Доступні: {', '.join(available)}."
            )
        }

    return _wrap_data(_format_endpoint(method, path, op))


def _schema(spec: dict[str, Any], query: str) -> dict[str, Any]:
    schemas = (spec.get("components") or {}).get("schemas") or {}
    query_stripped = query.strip()

    if query_stripped.lower().startswith("schema "):
        query_stripped = query_stripped[7:].strip()

    # Точний матч case-sensitive (як у спеці)
    if query_stripped in schemas:
        return _wrap_data({"name": query_stripped, "schema": schemas[query_stripped]})

    # Case-insensitive точний
    lower_map = {name.lower(): name for name in schemas}
    if query_stripped.lower() in lower_map:
        real = lower_map[query_stripped.lower()]
        return _wrap_data({"name": real, "schema": schemas[real]})

    # Substring
    candidates = sorted(n for n in schemas if query_stripped.lower() in n.lower())
    if not candidates:
        return {"error": f"Schema '{query_stripped}' не знайдено."}
    if len(candidates) == 1:
        name = candidates[0]
        return _wrap_data({"name": name, "schema": schemas[name]})
    return {
        "error": f"query='{query_stripped}' матчить кілька schemas. Уточни.",
        "candidates": candidates[:20],
    }


def _search(spec: dict[str, Any], query: str) -> dict[str, Any]:
    paths = spec.get("paths", {}) or {}
    q = query.strip().lower()
    if not q:
        return {"error": "Порожній search query."}

    hits: list[dict[str, Any]] = []
    for path, ops in paths.items():
        for method, op in ops.items():
            if method not in _HTTP_METHODS:
                continue
            haystack_parts = [
                path.lower(),
                (op.get("summary") or "").lower(),
                (op.get("description") or "").lower(),
                (op.get("operationId") or "").lower(),
            ]
            haystack = "\n".join(haystack_parts)
            if q in haystack:
                hits.append(
                    {
                        "method": method.upper(),
                        "path": path,
                        "summary": op.get("summary") or "",
                        "tags": op.get("tags") or [],
                    }
                )

    hits.sort(key=lambda h: (h["path"], h["method"]))
    return {"data": {"query": query, "count": len(hits), "endpoints": hits[:50]}}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_method_path(query: str) -> tuple[str, str] | None:
    parts = query.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    method, path = parts[0].lower(), parts[1].strip()
    if method not in _HTTP_METHODS:
        return None
    if not path.startswith("/"):
        path = "/" + path
    return method, path


def _find_path_candidates(all_paths, target: str) -> list[str]:
    target_lower = target.lower().strip("/")
    return sorted(
        p for p in all_paths
        if target_lower and target_lower in p.lower()
    )


def _format_endpoint(method: str, path: str, op: dict[str, Any]) -> dict[str, Any]:
    """Витискаємо корисні поля endpoint-а у плоску структуру."""
    result: dict[str, Any] = {
        "method": method.upper(),
        "path": path,
        "summary": op.get("summary") or "",
        "description": op.get("description") or "",
        "operationId": op.get("operationId"),
        "tags": op.get("tags") or [],
        "deprecated": op.get("deprecated", False),
        "security": op.get("security"),
    }

    params = op.get("parameters") or []
    if params:
        result["parameters"] = [
            {
                "name": p.get("name"),
                "in": p.get("in"),
                "required": p.get("required", False),
                "schema": p.get("schema"),
                "description": p.get("description"),
            }
            for p in params
        ]

    request_body = op.get("requestBody")
    if request_body:
        result["requestBody"] = request_body

    responses = op.get("responses") or {}
    if responses:
        result["responses"] = responses

    return result


def _wrap_data(payload: dict[str, Any]) -> dict[str, Any]:
    """Огортає payload у {"data": ...} і додає _warning якщо великий."""
    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized) <= MAX_RESPONSE_CHARS:
        return {"data": payload}
    return {
        "data": {
            **payload,
            "_warning": (
                f"Response ~{len(serialized)} chars (limit {MAX_RESPONSE_CHARS}). "
                "Структура повна, але якщо response_schema/requestBody занадто пухкі — "
                "переглянь конкретну component schema через mode='schema'."
            ),
        }
    }

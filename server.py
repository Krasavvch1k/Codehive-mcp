"""
MCP-сервер Worqen (Streamable HTTP) — повна версія з tier-системою,
оптимізацією токенів і analytics-tools.
"""

import contextlib
import json

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent

from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send
import uvicorn

from parsers import user_stories as us_parser
from parsers import bug_report as bug_parser
from parsers import docs as docs_parser
from parsers import analytics
from parsers import team_discussions as team_parser
from drive_client import (
    clear_cache as clear_drive_cache,
    get_file_metadata,
    is_drive_newer,
)
from config import FILE_IDS
from response_utils import strip_empty, format_list_response
from writers.us_writer import update_story, create_story
from writers.bug_writer import update_bug, create_bug
from writers.safety import SafetyError
from writers.writes_log import read_today_log, read_log_by_date, filter_log
from parsers.references import validate_references


server = Server("worqen-mcp")


# Список ключів doc-документів для enum-полів у tools.
DOC_ENUM = [
    "tech_doc",
    "prd_bootstrap",
    "prd_v1_1",
    "prd_v2",
    "aml_policy",
    "tos",
    "privacy",
    "cookie",
]


# ====================== TOOL DEFINITIONS ======================


def _tools() -> list[Tool]:
    return [
        # ---------- User Stories ----------
        Tool(
            name="list_user_stories",
            description=(
                "Список user stories з фільтрами. "
                "tier: 'scan' (default - короткі поля), 'audit' (+ AC, Edge Cases, Dependencies, Notes, Related Decisions), 'full'. "
                "При >20 рядках автоматично табличний формат."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "epic": {"type": "string"},
                    "status": {"type": "string"},
                    "priority": {"type": "string", "description": "Must / Should / Could / Won't"},
                    "version": {"type": "string", "description": "MVP / v1 / v2 / v3"},
                    "search": {"type": "string", "description": "Пошук по всіх текстових полях"},
                    "tier": {"type": "string", "enum": ["scan", "audit", "full"], "description": "Default: scan"},
                    "limit": {"type": "integer", "description": "Default 100, max 500"},
                    "offset": {"type": "integer", "description": "Default 0"},
                },
            },
        ),
        Tool(
            name="get_user_story",
            description="Повна user story за ID (всі поля).",
            inputSchema={
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        ),
        Tool(
            name="next_us_id",
            description="Наступний вільний US-XXX.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="epics_summary",
            description=(
                "Статистика по епіках. "
                "level: 'minimal' (default, тільки {epic: total}), 'status' (+ by_status), 'full'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["minimal", "status", "full"]},
                },
            },
        ),
        Tool(
            name="find_us_dependents",
            description="User stories які залежать від указаної (де вона у Dependencies).",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "tier": {"type": "string", "enum": ["scan", "audit", "full"]},
                },
                "required": ["id"],
            },
        ),
        # ---------- Bug Report ----------
        Tool(
            name="list_bugs",
            description="Список багів з фільтрами. tier: scan (default) / audit / full.",
            inputSchema={
                "type": "object",
                "properties": {
                    "priority": {"type": "string", "description": "P1 / P2 / P3"},
                    "status": {"type": "string", "description": "Потрібно зробити / Виправлено / Не актуально / Перевірити"},
                    "bug_type": {"type": "string", "description": "Логіка / Функціональний / UI / UX / I18n / Валідація"},
                    "search": {"type": "string"},
                    "tier": {"type": "string", "enum": ["scan", "audit", "full"]},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
            },
        ),
        Tool(
            name="get_bug",
            description="Повний баг за ID.",
            inputSchema={
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        ),
        Tool(
            name="next_bug_id",
            description="Наступний вільний BUG-XXX.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="bugs_summary",
            description="Зведена статистика багів. level: minimal / full (default).",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["minimal", "full"]},
                },
            },
        ),
        Tool(
            name="list_ficha",
            description="Список Ficha. tier: scan (default) / audit / full.",
            inputSchema={
                "type": "object",
                "properties": {
                    "priority": {"type": "string"},
                    "transferred": {"type": "boolean"},
                    "search": {"type": "string"},
                    "tier": {"type": "string", "enum": ["scan", "audit", "full"]},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
            },
        ),
        # ---------- Documents ----------
        Tool(
            name="list_doc_sections",
            description=(
                "TOC документа з breadcrumbs. Кожна секція повертається з полями "
                "{index, level, title, path}, де path — повний шлях типу "
                "'1. Overview > 1.2 Architecture > 1.2.1 Backend'. "
                "Доступні: tech_doc, prd_bootstrap, prd_v1_1, prd_v2, aml_policy, tos, privacy, cookie."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "doc": {"type": "string", "enum": DOC_ENUM},
                },
                "required": ["doc"],
            },
        ),
        Tool(
            name="get_doc_section",
            description=(
                "Текст секції документа з таблицями (markdown). "
                "Секція — від heading до наступного heading того ж або вищого рівня."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "doc": {"type": "string", "enum": DOC_ENUM},
                    "heading": {"type": "string"},
                    "include_subsections": {"type": "boolean"},
                },
                "required": ["doc", "heading"],
            },
        ),
        Tool(
            name="get_doc_block",
            description=(
                "Блок документа від heading_from до heading_to (інклюзивно з обох боків). "
                "Якщо heading_to не вказано — від heading_from до кінця документа. "
                "На відміну від get_doc_section, не зважає на рівні — бере всі заголовки і параграфи між якорями. "
                "Корисно для виборки кастомних діапазонів через TOC."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "doc": {"type": "string", "enum": DOC_ENUM},
                    "heading_from": {"type": "string", "description": "Заголовок-початок (case-insensitive substring)"},
                    "heading_to": {"type": "string", "description": "Заголовок-кінець (case-insensitive substring). Опційно."},
                },
                "required": ["doc", "heading_from"],
            },
        ),
        Tool(
            name="get_doc_full_text",
            description=(
                "Повний текст документа як markdown. Заголовки → #/##/###, таблиці → markdown-таблиці. "
                "Уважно з контекстом — для довгих доків (tech_doc) краще list_doc_sections + get_doc_section/get_doc_block."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "doc": {"type": "string", "enum": DOC_ENUM},
                },
                "required": ["doc"],
            },
        ),
        Tool(
            name="search_in_doc",
            description="Пошук у документі. limit (default 10), context_chars (default 100).",
            inputSchema={
                "type": "object",
                "properties": {
                    "doc": {"type": "string", "enum": DOC_ENUM},
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                    "context_chars": {"type": "integer"},
                },
                "required": ["doc", "query"],
            },
        ),
        # ---------- Analytics ----------
        Tool(
            name="detect_conflicts",
            description=(
                "Сканує всі сторі і повертає знайдені проблеми: "
                "заборонені терміни (USDT, Worker, Client), старі цифри ($0.50, 100 welcome bonus), "
                "AC без Given/When/Then, дублі у Dependencies, статус-пріоритет неузгодженості. "
                "За замовчуванням повертає top 20 знахідок + summary."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "epic": {"type": "string", "description": "Обмежити сканом одного епіку"},
                    "severity_min": {"type": "string", "enum": ["critical", "warning", "info"], "description": "Default: warning"},
                    "limit": {"type": "integer", "description": "Default 20"},
                },
            },
        ),
        Tool(
            name="validate_id_format",
            description="Перевірка послідовності ID. entity: us / bug / ficha. Знаходить пропуски, дублі, неправильний формат.",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "enum": ["us", "bug", "ficha"], "description": "Default: us"},
                },
            },
        ),
        Tool(
            name="list_open_questions",
            description=(
                "Сторі що чекають рішень PO: "
                "Status='Потрібно обговорення', Status='Потрібно доопрацювати PO', "
                "маркери TBD/потребує обговорення/питання у Notes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "epic": {"type": "string"},
                },
            },
        ),
        Tool(
            name="session_changes",
            description=(
                "Порівнює поточний стан xlsx-файлів зі знімком (за датою або останнім). "
                "Повертає створені/видалені/змінені записи. "
                "Якщо немає попереднього снепшоту — зберігає поточний як baseline."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "since_date": {"type": "string", "description": "YYYY-MM-DD. Default: найсвіжіший попередній снепшот."},
                },
            },
        ),
        Tool(
            name="save_snapshot",
            description="Зберігає поточний стан xlsx-файлів як знімок дня. Викликай вкінці сесії.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_snapshots",
            description="Список збережених снепшотів.",
            inputSchema={"type": "object", "properties": {}},
        ),
        # ---------- Team Discussions ----------
        Tool(
            name="list_team_discussions",
            description=(
                "Список обговорень з командою з папки Drive (Google Docs у підпапках за датами сесій). "
                "Фільтри: status ('закрили' / 'обговорили' / 'закрити' / 'open' для активних), "
                "session_date ('06.05.26'). Default limit 50, max 200. "
                "Кожен елемент: {id, name, raw_name, status, session_date, modified, size_bytes}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "'закрили' / 'закрити' / 'обговорили' / 'open' (активні без статусу)",
                    },
                    "session_date": {
                        "type": "string",
                        "description": "Точна дата сесії у форматі '06.05.26' як у назві підпапки",
                    },
                    "limit": {"type": "integer", "description": "Default 50, max 200"},
                },
            },
        ),
        Tool(
            name="read_team_discussion",
            description=(
                "Читає повний вміст одного обговорення (Google Doc експортується у markdown). "
                "query - повний Drive ID або частина назви (case-insensitive). "
                "Якщо за запитом знайдено >1 документ - повертається помилка зі списком кандидатів."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Drive ID або частина назви документу-обговорення",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="search_team_discussions",
            description=(
                "Пошук серед обговорень. scope: 'names' (default, швидко - тільки назви файлів і папок-сесій), "
                "'content' (повільно - скачує всі Google Docs і шукає у тексті), 'both'. "
                "Default limit 20, context_chars 200."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "scope": {
                        "type": "string",
                        "enum": ["names", "content", "both"],
                        "description": "Default: names",
                    },
                    "limit": {"type": "integer", "description": "Default 20"},
                    "context_chars": {"type": "integer", "description": "Default 200 (тільки для content)"},
                },
                "required": ["query"],
            },
        ),
        # ---------- Writers ----------
        Tool(
            name="update_user_story",
            description=(
                "Оновлює whitelist-поля існуючої US у Drive xlsx. "
                "Дозволені поля: Title, User Story, Acceptance Criteria, Edge Cases, "
                "Dependencies, Notes, Related Decisions. "
                "Status / Priority / Version / Est. day / Epic — Микита редагує руками. "
                "Перед записом: drive sync check + auto snapshot."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "US-XXX"},
                    "fields": {
                        "type": "object",
                        "description": "Поля для оновлення (whitelist)",
                    },
                    "force_overwrite": {
                        "type": "boolean",
                        "description": "Якщо true — пропустити Drive sync check і записати попри що. "
                                       "Використовується ТІЛЬКИ якщо Микита явно сказав 'перетри'. "
                                       "Default: false.",
                    },
                },
                "required": ["id", "fields"],
            },
        ),
        Tool(
            name="create_user_story",
            description=(
                "Створює нову US у Drive xlsx. "
                "Якщо переданий use_id — використовує цей конкретний ID (після перевірки вільності), "
                "інакше — присвоює через next_us_id. Запис завжди у кінець файлу. "
                "Обов'язкові поля: Epic, Title, User Story, Status, Priority, Version. "
                "Опційні: Acceptance Criteria, Edge Cases, Dependencies, Notes, Related Decisions, Est. day. "
                "Стиль нового рядка копіюється з останнього рядка з даними."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "fields": {
                        "type": "object",
                        "description": "Усі поля нової US (без ID — ID окремо у use_id)",
                    },
                    "use_id": {
                        "type": "string",
                        "description": "Опціонально: конкретний ID типу 'US-172' (заповнення пропуску). "
                                       "Якщо не передано — авто через next_us_id.",
                    },
                    "force_overwrite": {
                        "type": "boolean",
                        "description": "Якщо true — пропустити Drive sync check. "
                                       "Тільки за явною командою Микити. Default: false.",
                    },
                },
                "required": ["fields"],
            },
        ),
        Tool(
            name="update_bug",
            description=(
                "Оновлює whitelist-поля існуючого BUG у Drive xlsx. "
                "Дозволені поля: Опис, Де, Очікувана поведінка, Рекомендація для Романа, "
                "Посилання на скрін, Зафіксоване рішення, Примітки. "
                "Тип / Пріоритет / Статус / Джерело — Микита редагує руками."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "BUG-XXX"},
                    "fields": {
                        "type": "object",
                        "description": "Поля для оновлення (whitelist)",
                    },
                    "force_overwrite": {
                        "type": "boolean",
                        "description": "Якщо true — пропустити Drive sync check. "
                                       "Тільки за явною командою Микити. Default: false.",
                    },
                },
                "required": ["id", "fields"],
            },
        ),
        Tool(
            name="create_bug",
            description=(
                "Створює новий BUG у Drive xlsx. "
                "Якщо переданий use_id — використовує цей конкретний ID, "
                "інакше — через next_bug_id. Запис завжди у кінець файлу. "
                "Обов'язкові: Тип, Пріоритет, Статус, Опис. "
                "Опційні: Джерело, Де, Очікувана поведінка, Рекомендація для Романа, "
                "Посилання на скрін, Зафіксоване рішення, Примітки."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "fields": {
                        "type": "object",
                        "description": "Усі поля нового BUG (без ID — ID окремо у use_id)",
                    },
                    "use_id": {
                        "type": "string",
                        "description": "Опціонально: конкретний ID типу 'BUG-024' (заповнення пропуску). "
                                       "Якщо не передано — авто через next_bug_id.",
                    },
                    "force_overwrite": {
                        "type": "boolean",
                        "description": "Якщо true — пропустити Drive sync check. "
                                       "Тільки за явною командою Микити. Default: false.",
                    },
                },
                "required": ["fields"],
            },
        ),
        # ---------- Utils ----------
        Tool(
            name="get_session_writes",
            description=(
                "Журнал успішних записів через writers (update/create US/BUG) за вказану дату. "
                "Без параметрів — повертає записи за сьогодні. "
                "Допомога для формування дампа сесії. "
                "Кожен запис: timestamp, tool, id, file_key, fields_changed, "
                "force_overwrite, row, drive_modified_after, fields_preview (тільки для create)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "YYYY-MM-DD. Default — сьогодні.",
                    },
                    "tool": {
                        "type": "string",
                        "enum": [
                            "update_user_story",
                            "create_user_story",
                            "update_bug",
                            "create_bug",
                        ],
                        "description": "Фільтр по типу запису.",
                    },
                    "id": {
                        "type": "string",
                        "description": "Фільтр по конкретному ID (US-XXX / BUG-XXX).",
                    },
                    "since": {
                        "type": "string",
                        "description": "ISO timestamp без таймзони. Записи з timestamp >= since.",
                    },
                    "until": {
                        "type": "string",
                        "description": "ISO timestamp без таймзони. Записи з timestamp <= until.",
                    },
                },
            },
        ),
        Tool(
            name="bulk_validate_references",
            description=(
                "Сканує всі US і BUG, повертає: "
                "broken refs (посилання на неіснуючі ID у Dependencies, Related Decisions, Notes, AC, Edge Cases для US; "
                "Опис, Очікувана поведінка, Рекомендація для Романа, Зафіксоване рішення, Примітки для BUG) "
                "та цикли у Dependencies US. Read-only. "
                "Регекс шукає US-NNN / US-NNNN і BUG-NNN / BUG-NNNN (case-insensitive). "
                "Self-references пропускаються."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "check_us": {
                        "type": "boolean",
                        "description": "Сканувати US файл. Default: true.",
                    },
                    "check_bug": {
                        "type": "boolean",
                        "description": "Сканувати BUG файл. Default: true.",
                    },
                    "include_cycles": {
                        "type": "boolean",
                        "description": "Перевіряти циклічні Dependencies у US. Default: true.",
                    },
                },
            },
        ),
        Tool(
            name="list_files",
            description="Список усіх файлів які знає сервер.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="clear_cache",
            description="Скидає кеш скачаних файлів.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="check_drive_sync",
            description="Перевіряє чи Drive має свіжіший файл ніж у кеші. Діагностика синхронізації.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_key": {
                        "type": "string",
                        "description": (
                            "Ключ файлу: tech_doc / user_stories / roadmap / qa_report / "
                            "prd_bootstrap / prd_v1_1 / prd_v2 / aml_policy / tos / privacy / cookie"
                        ),
                    },
                },
                "required": ["file_key"],
            },
        ),
    ]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return _tools()


def _format_response(data) -> list[TextContent]:
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return [TextContent(type="text", text=text)]


# Колонки для табличного формату list-операцій
US_SCAN_COLUMNS = ["Epic", "ID", "Title", "Status", "Priority", "Version"]
BUG_SCAN_COLUMNS = ["ID", "Тип", "Пріоритет", "Статус", "Опис"]
FICHA_SCAN_COLUMNS = ["#", "Назва", "Пріоритет", "Перенесено в US"]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    args = arguments or {}
    try:
        # ---------- User Stories ----------
        if name == "list_user_stories":
            tier = args.get("tier", "scan")
            result = us_parser.list_stories(
                epic=args.get("epic"),
                status=args.get("status"),
                priority=args.get("priority"),
                version=args.get("version"),
                search=args.get("search"),
                tier=tier,
            )
            cols = US_SCAN_COLUMNS if tier == "scan" else None
            return _format_response(format_list_response(
                result,
                limit=args.get("limit"),
                offset=args.get("offset", 0),
                table_columns=cols,
            ))

        if name == "get_user_story":
            result = us_parser.get_story(args["id"])
            if result is None:
                return _format_response({"error": f"US '{args['id']}' не знайдено"})
            return _format_response(strip_empty(result))

        if name == "next_us_id":
            return _format_response({"next_id": us_parser.get_next_us_id()})

        if name == "epics_summary":
            return _format_response(us_parser.list_epics_summary(level=args.get("level", "minimal")))

        if name == "find_us_dependents":
            tier = args.get("tier", "scan")
            result = us_parser.find_dependents(args["id"], tier=tier)
            cols = US_SCAN_COLUMNS if tier == "scan" else None
            return _format_response(format_list_response(result, table_columns=cols))

        # ---------- Bug Report ----------
        if name == "list_bugs":
            tier = args.get("tier", "scan")
            result = bug_parser.list_bugs(
                priority=args.get("priority"),
                status=args.get("status"),
                bug_type=args.get("bug_type"),
                search=args.get("search"),
                tier=tier,
            )
            cols = BUG_SCAN_COLUMNS if tier == "scan" else None
            return _format_response(format_list_response(
                result,
                limit=args.get("limit"),
                offset=args.get("offset", 0),
                table_columns=cols,
            ))

        if name == "get_bug":
            result = bug_parser.get_bug(args["id"])
            if result is None:
                return _format_response({"error": f"BUG '{args['id']}' не знайдено"})
            return _format_response(strip_empty(result))

        if name == "next_bug_id":
            return _format_response({"next_id": bug_parser.get_next_bug_id()})

        if name == "bugs_summary":
            return _format_response(bug_parser.bugs_summary(level=args.get("level", "full")))

        if name == "list_ficha":
            tier = args.get("tier", "scan")
            result = bug_parser.list_ficha(
                priority=args.get("priority"),
                transferred=args.get("transferred"),
                search=args.get("search"),
                tier=tier,
            )
            cols = FICHA_SCAN_COLUMNS if tier == "scan" else None
            return _format_response(format_list_response(
                result,
                limit=args.get("limit"),
                offset=args.get("offset", 0),
                table_columns=cols,
            ))

        # ---------- Documents ----------
        if name == "list_doc_sections":
            result = docs_parser.get_toc(args["doc"])
            return _format_response({"count": len(result), "sections": result})

        if name == "get_doc_section":
            result = docs_parser.get_section(
                args["doc"],
                args["heading"],
                include_subsections=args.get("include_subsections", True),
            )
            if result is None:
                return _format_response(
                    {"error": f"Секцію '{args['heading']}' не знайдено у {args['doc']}"}
                )
            return _format_response(result)

        if name == "get_doc_block":
            result = docs_parser.get_doc_block(
                args["doc"],
                args["heading_from"],
                heading_to=args.get("heading_to"),
            )
            if result is None:
                return _format_response(
                    {"error": f"Заголовок '{args['heading_from']}' не знайдено у {args['doc']}"}
                )
            return _format_response(result)

        if name == "get_doc_full_text":
            text = docs_parser.get_full_text(args["doc"])
            return _format_response({
                "doc": args["doc"],
                "length": len(text),
                "text": text,
            })

        if name == "search_in_doc":
            limit = args.get("limit", 10)
            ctx = args.get("context_chars", 100)
            result = docs_parser.search_in_doc(args["doc"], args["query"], context_chars=ctx)
            return _format_response({
                "total": len(result),
                "shown": min(limit, len(result)),
                "matches": result[:limit],
            })

        # ---------- Analytics ----------
        if name == "detect_conflicts":
            return _format_response(analytics.detect_conflicts(
                epic=args.get("epic"),
                severity_min=args.get("severity_min", "warning"),
                limit=args.get("limit", 20),
            ))

        if name == "validate_id_format":
            return _format_response(analytics.validate_id_format(
                entity=args.get("entity", "us"),
            ))

        if name == "list_open_questions":
            return _format_response(analytics.list_open_questions(
                epic=args.get("epic"),
            ))

        if name == "session_changes":
            return _format_response(analytics.session_changes(
                since_date=args.get("since_date"),
            ))

        if name == "save_snapshot":
            path = analytics.save_today_snapshot()
            return _format_response({"saved_to": path})

        if name == "list_snapshots":
            return _format_response({"snapshots": analytics.list_snapshots()})

        # ---------- Team Discussions ----------
        if name == "list_team_discussions":
            return _format_response(team_parser.list_team_discussions(
                status=args.get("status"),
                session_date=args.get("session_date"),
                limit=args.get("limit", 50),
            ))

        if name == "read_team_discussion":
            try:
                return _format_response(team_parser.read_team_discussion(args["query"]))
            except ValueError as ve:
                return _format_response({"error": str(ve)})

        if name == "search_team_discussions":
            try:
                return _format_response(team_parser.search_team_discussions(
                    query=args["query"],
                    scope=args.get("scope", "names"),
                    limit=args.get("limit", 20),
                    context_chars=args.get("context_chars", 200),
                ))
            except ValueError as ve:
                return _format_response({"error": str(ve)})

        # ---------- Writers ----------
        if name == "update_user_story":
            try:
                return _format_response(update_story(
                    args["id"],
                    args.get("fields") or {},
                    force_overwrite=bool(args.get("force_overwrite", False)),
                ))
            except SafetyError as se:
                return _format_response({
                    "error": str(se),
                    "kind": se.kind,
                    "tool": name,
                })

        if name == "create_user_story":
            try:
                return _format_response(create_story(
                    args.get("fields") or {},
                    use_id=args.get("use_id"),
                    force_overwrite=bool(args.get("force_overwrite", False)),
                ))
            except SafetyError as se:
                return _format_response({
                    "error": str(se),
                    "kind": se.kind,
                    "tool": name,
                })

        if name == "update_bug":
            try:
                return _format_response(update_bug(
                    args["id"],
                    args.get("fields") or {},
                    force_overwrite=bool(args.get("force_overwrite", False)),
                ))
            except SafetyError as se:
                return _format_response({
                    "error": str(se),
                    "kind": se.kind,
                    "tool": name,
                })

        if name == "create_bug":
            try:
                return _format_response(create_bug(
                    args.get("fields") or {},
                    use_id=args.get("use_id"),
                    force_overwrite=bool(args.get("force_overwrite", False)),
                ))
            except SafetyError as se:
                return _format_response({
                    "error": str(se),
                    "kind": se.kind,
                    "tool": name,
                })

        # ---------- Utils ----------
        if name == "get_session_writes":
            date = args.get("date")
            if date:
                entries = read_log_by_date(date)
            else:
                entries = read_today_log()
            filtered = filter_log(
                entries,
                tool=args.get("tool"),
                record_id=args.get("id"),
                since=args.get("since"),
                until=args.get("until"),
            )
            return _format_response({
                "date": date or "today",
                "total": len(filtered),
                "entries": filtered,
            })

        if name == "bulk_validate_references":
            return _format_response(validate_references(
                check_us=bool(args.get("check_us", True)),
                check_bug=bool(args.get("check_bug", True)),
                include_cycles=bool(args.get("include_cycles", True)),
            ))

        if name == "list_files":
            files_info = []
            for key, file_id in FILE_IDS.items():
                try:
                    meta = get_file_metadata(file_id)
                    files_info.append({
                        "key": key,
                        "id": file_id,
                        "name": meta.get("name"),
                        "modified": meta.get("modifiedTime"),
                    })
                except Exception as e:
                    files_info.append({"key": key, "id": file_id, "error": str(e)})
            return _format_response(files_info)

        if name == "clear_cache":
            clear_drive_cache()
            return _format_response({"status": "cache cleared"})

        if name == "check_drive_sync":
            file_key = args["file_key"]
            if file_key not in FILE_IDS:
                return _format_response({"error": f"Unknown file_key '{file_key}'"})
            return _format_response(is_drive_newer(FILE_IDS[file_key]))

        return _format_response({"error": f"Невідомий tool: {name}"})

    except Exception as e:
        import traceback
        return _format_response({
            "error": str(e),
            "tool": name,
            "args": args,
            "traceback": traceback.format_exc(),
        })


# ====================== STREAMABLE HTTP TRANSPORT ======================


session_manager = StreamableHTTPSessionManager(
    app=server,
    event_store=None,
    json_response=False,
    stateless=True,
)


async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
    await session_manager.handle_request(scope, receive, send)


@contextlib.asynccontextmanager
async def lifespan(app):
    async with session_manager.run():
        yield


app = Starlette(
    debug=False,
    routes=[Mount("/mcp", app=handle_streamable_http)],
    lifespan=lifespan,
)


if __name__ == "__main__":
    print("=" * 60)
    print("Worqen MCP Server v2.1: http://127.0.0.1:8765")
    print("Endpoint:               http://127.0.0.1:8765/mcp")
    print("=" * 60)
    print("Tools: 27 (24 + 3 team_discussions: list / read / search)")
    print("Doc files: 8 (tech_doc, prd_bootstrap, prd_v1_1, prd_v2, aml_policy, tos, privacy, cookie)")
    print("Tier system: scan / audit / full")
    print("Cache TTL: 30s")
    print("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")

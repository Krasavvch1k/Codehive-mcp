"""
Worqen Workspace MCP tools.

Експортує WORQEN_WS_TOOLS і ws_dispatch — для динамічного виявлення і читання
файлів у Worqen Shared Drive (на додачу до зафіксованих FILE_IDS).

Tools:
- worqen_ws_list_folder     — один рівень
- worqen_ws_list_all        — BFS-обхід з max_depth
- worqen_ws_resolve         — id за substring/ID
- worqen_ws_read_doc        — docx/gdoc → markdown
- worqen_ws_read_sheet      — gsheet/xlsx → markdown-таблиці
- worqen_ws_force_refresh   — інвалідація кешу (точкова або повна)
"""

from mcp.types import Tool

from projects.worqen import ws_reader
from projects.worqen import ws_sheet_reader


WORQEN_WS_TOOLS: list[Tool] = [
    Tool(
        name="worqen_ws_list_folder",
        description=(
            "Worqen workspace: вміст однієї папки Shared Drive 'Worqen' (один рівень). "
            "Без folder_id — корінь Worqen Drive. Повертає всі типи файлів "
            "(gdoc, gsheet, docx, xlsx, gslides, pdf, image, other) і підпапки. "
            "Для рекурсивного обходу — worqen_ws_list_all."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "folder_id": {
                    "type": "string",
                    "description": "Drive ID підпапки. Default: корінь Worqen Drive.",
                },
            },
        },
    ),
    Tool(
        name="worqen_ws_list_all",
        description=(
            "Worqen workspace: рекурсивний обхід (BFS) усього Drive до max_depth. "
            "Кожен елемент має path (breadcrumb) і depth. Default depth=3. "
            "Використовуй коли треба знайти файл і не знаєш у якій підпапці він лежить."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "max_depth": {
                    "type": "integer",
                    "description": "Глибина обходу. Default: 3. Більші значення — повільніше.",
                },
                "folder_id": {
                    "type": "string",
                    "description": "Стартова папка. Default: корінь Worqen Drive.",
                },
            },
        },
    ),
    Tool(
        name="worqen_ws_resolve",
        description=(
            "Worqen workspace: знаходить файл/папку за substring у назві або за повним Drive ID. "
            "Повертає одного кандидата. Якщо матчить кілька — підкаже їх назви для уточнення. "
            "Використовуй щоб переконатись що ws-tools правильно резолвлять твою назву."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Substring назви (case-insensitive) або повний Drive ID.",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="worqen_ws_read_doc",
        description=(
            "Worqen workspace: читає docx або gdoc як markdown. "
            "query: substring назви або повний Drive ID. "
            "force_refresh: обходить TTL-кеш (30с) — корисно якщо ти щойно "
            "відредагував файл у Drive UI і хочеш свіже."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Substring назви або повний Drive ID.",
                },
                "force_refresh": {
                    "type": "boolean",
                    "description": "True щоб обійти кеш. Default: false.",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="worqen_ws_read_sheet",
        description=(
            "Worqen workspace: читає gsheet або xlsx. Повертає всі аркуші (або один, "
            "якщо вказано sheet_name) як markdown-таблиці і 2D-значення. "
            "Limit rows/cols за замовчуванням 200/50 щоб не вантажити мегабайти; "
            "підвищ для повних таблиць. force_refresh — обійти 30с TTL."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Substring назви або повний Drive ID.",
                },
                "sheet_name": {
                    "type": "string",
                    "description": "Назва конкретного аркуша. Default: усі аркуші.",
                },
                "limit_rows": {
                    "type": "integer",
                    "description": "Макс. кількість рядків на аркуш. Default: 200, max: 5000.",
                },
                "limit_cols": {
                    "type": "integer",
                    "description": "Макс. кількість колонок на аркуш. Default: 50, max: 200.",
                },
                "force_refresh": {
                    "type": "boolean",
                    "description": "True щоб обійти кеш. Default: false.",
                },
                "as_markdown": {
                    "type": "boolean",
                    "description": "Включити markdown-таблицю у відповідь. Default: true.",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="worqen_ws_force_refresh",
        description=(
            "Worqen workspace: примусово скидає TTL-кеш. "
            "Без query — скидає весь кеш (файли + структура папок). "
            "З query — скидає кеш для одного файлу/папки. "
            "Корисно коли ти щойно відредагував файл руками у Drive UI."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Substring назви або Drive ID. Без значення — скидає весь кеш.",
                },
            },
        },
    ),
]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def ws_dispatch(name: str, args: dict):
    """
    Повертає dict результату якщо tool обробився, або None — щоб обгортка
    спробувала наступного диспатчера у server.py.
    """
    if name == "worqen_ws_list_folder":
        return ws_reader.list_folder(folder_id=args.get("folder_id"))

    if name == "worqen_ws_list_all":
        return ws_reader.list_all(
            max_depth=args.get("max_depth", 3),
            folder_id=args.get("folder_id"),
        )

    if name == "worqen_ws_resolve":
        try:
            return ws_reader.resolve(args["query"])
        except ValueError as e:
            return {"error": str(e)}

    if name == "worqen_ws_read_doc":
        try:
            return ws_reader.read_doc(
                query=args["query"],
                force_refresh=args.get("force_refresh", False),
            )
        except ValueError as e:
            return {"error": str(e)}

    if name == "worqen_ws_read_sheet":
        try:
            return ws_sheet_reader.read_sheet(
                query=args["query"],
                sheet_name=args.get("sheet_name"),
                limit_rows=args.get("limit_rows", ws_sheet_reader.DEFAULT_LIMIT_ROWS),
                limit_cols=args.get("limit_cols", ws_sheet_reader.DEFAULT_LIMIT_COLS),
                force_refresh=args.get("force_refresh", False),
                as_markdown=args.get("as_markdown", True),
            )
        except ValueError as e:
            return {"error": str(e)}

    if name == "worqen_ws_force_refresh":
        try:
            return ws_reader.force_refresh(query=args.get("query"))
        except ValueError as e:
            return {"error": str(e)}

    return None

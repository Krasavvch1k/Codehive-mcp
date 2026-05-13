"""
Worqen Workspace MCP tools.

Експортує WORQEN_WS_TOOLS і ws_dispatch — для динамічного виявлення, читання і
запису файлів у Worqen Shared Drive (на додачу до зафіксованих FILE_IDS).

Read tools (Phase 1):
- worqen_ws_list_folder     — один рівень
- worqen_ws_list_all        — BFS-обхід з max_depth
- worqen_ws_resolve         — id за substring/ID
- worqen_ws_read_doc        — docx/gdoc → markdown
- worqen_ws_read_sheet      — gsheet/xlsx → markdown-таблиці
- worqen_ws_force_refresh   — інвалідація кешу (точкова або повна)

Write tools (Phase 2):
- worqen_ws_replace_text    — заміна тексту у docx/gdoc (1 match)
- worqen_ws_insert_text     — вставка тексту after/before/end_of_doc
- worqen_ws_replace_section — заміна секції за heading (Phase 2.5 stub)
- worqen_ws_update_cell     — одна комірка xlsx/gsheet
- worqen_ws_update_range    — 2D-діапазон xlsx/gsheet
- worqen_ws_append_row      — додавання рядка xlsx/gsheet
- worqen_ws_create_doc      — новий gdoc/docx
- worqen_ws_create_sheet    — новий gsheet/xlsx
- worqen_ws_create_folder   — нова папка

Write tools блокуються через WRITE_BLACKLIST_FILE_IDS (US/BUG — для них є
worqen_update_user_story/bug з whitelist полів) і WRITE_BLACKLIST_FOLDERS.
"""

from mcp.types import Tool

from projects.worqen import ws_creator, ws_reader, ws_sheet_reader
from projects.worqen import ws_sheet_writer, ws_writer


WORQEN_WS_TOOLS: list[Tool] = [
    # ---- READ TOOLS (Phase 1) ----
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

    # ---- WRITE TOOLS — DOCS (Phase 2) ----
    Tool(
        name="worqen_ws_replace_text",
        description=(
            "Worqen workspace: замінює РІВНО ОДНЕ входження old_text на new_text у docx або gdoc. "
            "Якщо знайдено 0 або >1 матчів — повертає помилку зі списком контекстів, "
            "щоб ти зробив old_text більш специфічним. "
            "US/BUG xlsx файли заблоковані (use worqen_update_user_story/bug instead). "
            "dry_run=true показує preview без запису."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Substring назви або Drive ID docx/gdoc файлу.",
                },
                "old_text": {
                    "type": "string",
                    "description": "Текст для пошуку (case-sensitive).",
                },
                "new_text": {
                    "type": "string",
                    "description": "Чим замінити.",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "True — preview без запису. Default: false.",
                },
                "force_overwrite": {
                    "type": "boolean",
                    "description": (
                        "True — ігнорувати drive-unchanged check (тільки для docx; "
                        "gdoc використовує revisionId)."
                    ),
                },
            },
            "required": ["query", "old_text", "new_text"],
        },
    ),
    Tool(
        name="worqen_ws_insert_text",
        description=(
            "Worqen workspace: вставка тексту у docx або gdoc. "
            "mode='after'/'before' потребує anchor (унікальний substring). "
            "mode='end_of_doc' (default) — додає у кінець без anchor. "
            "dry_run=true показує preview."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Substring назви або Drive ID docx/gdoc.",
                },
                "text": {
                    "type": "string",
                    "description": "Що вставляти.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["after", "before", "end_of_doc"],
                    "description": "Режим вставки. Default: end_of_doc.",
                },
                "anchor": {
                    "type": "string",
                    "description": (
                        "Для after/before — унікальний substring у документі. "
                        "Для end_of_doc — не передавати."
                    ),
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "True — preview. Default: false.",
                },
                "force_overwrite": {
                    "type": "boolean",
                    "description": "True — ігнорувати drive-unchanged check (тільки docx).",
                },
                "as_paragraph": {
                    "type": "boolean",
                    "description": (
                        "Для gdoc — обгортати text у переноси рядків (як абзац). "
                        "Default: true. Для docx ігнорується."
                    ),
                },
            },
            "required": ["query", "text"],
        },
    ),
    Tool(
        name="worqen_ws_replace_section",
        description=(
            "Worqen workspace: STUB (Phase 2.5). Заміна цілої секції документа за heading-anchor "
            "ще не реалізована. Використовуй worqen_ws_replace_text для точкових правок "
            "або worqen_ws_insert_text(mode='end_of_doc') для додавання."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "heading": {"type": "string"},
                "new_content": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "force_overwrite": {"type": "boolean"},
            },
            "required": ["query", "heading", "new_content"],
        },
    ),

    # ---- WRITE TOOLS — SHEETS (Phase 2) ----
    Tool(
        name="worqen_ws_update_cell",
        description=(
            "Worqen workspace: перезаписує ОДНУ комірку у gsheet або xlsx. "
            "cell — A1-нотація (напр. 'A1', 'BC42'). "
            "value може бути string/int/float/bool/null. "
            "US/BUG xlsx файли заблоковані. dry_run=true — preview."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Substring назви або Drive ID gsheet/xlsx.",
                },
                "sheet": {
                    "type": "string",
                    "description": "Назва аркуша (як у файлі).",
                },
                "cell": {
                    "type": "string",
                    "description": "A1-нотація однієї комірки ('A1', 'BC42').",
                },
                "value": {
                    "description": "Нове значення (string/int/float/bool/null).",
                },
                "dry_run": {"type": "boolean"},
                "force_overwrite": {"type": "boolean"},
            },
            "required": ["query", "sheet", "cell", "value"],
        },
    ),
    Tool(
        name="worqen_ws_update_range",
        description=(
            "Worqen workspace: перезаписує прямокутний діапазон у gsheet/xlsx. "
            "range — A1-нотація (напр. 'A1:C10'). "
            "values — 2D-список рядок-стовпець. "
            "Розмір values має покривати range (інакше Sheets API дасть помилку). "
            "dry_run=true — preview."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "sheet": {"type": "string"},
                "range": {
                    "type": "string",
                    "description": "A1-діапазон ('A1:C10').",
                },
                "values": {
                    "type": "array",
                    "description": "2D-list (list of lists).",
                    "items": {"type": "array"},
                },
                "dry_run": {"type": "boolean"},
                "force_overwrite": {"type": "boolean"},
            },
            "required": ["query", "sheet", "range", "values"],
        },
    ),
    Tool(
        name="worqen_ws_append_row",
        description=(
            "Worqen workspace: додає один рядок у кінець таблиці gsheet/xlsx. "
            "values — 1D-list (не 2D!). "
            "Для xlsx — копіює стиль з попереднього рядка (font/fill/border) якщо "
            "copy_style_from_last=true (default)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "sheet": {"type": "string"},
                "values": {
                    "type": "array",
                    "description": "1D-list значень для одного рядка.",
                },
                "copy_style_from_last": {
                    "type": "boolean",
                    "description": "Для xlsx — копіювати стиль з попереднього рядка. Default: true.",
                },
                "dry_run": {"type": "boolean"},
                "force_overwrite": {"type": "boolean"},
            },
            "required": ["query", "sheet", "values"],
        },
    ),

    # ---- CREATE TOOLS (Phase 2) ----
    Tool(
        name="worqen_ws_create_doc",
        description=(
            "Worqen workspace: створює новий gdoc (default) або docx у Worqen Drive. "
            "parent_folder необов'язковий — default корінь Worqen Drive. "
            "Duplicate name check активний — обійти через allow_duplicate=true."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Назва нового документа.",
                },
                "parent_folder": {
                    "type": "string",
                    "description": (
                        "Папка-батько: name substring або Drive ID. "
                        "Default: корінь Worqen Drive."
                    ),
                },
                "format": {
                    "type": "string",
                    "enum": ["gdoc", "docx"],
                    "description": "Тип файлу. Default: gdoc.",
                },
                "initial_content": {
                    "type": "string",
                    "description": "Опційний початковий текст.",
                },
                "allow_duplicate": {
                    "type": "boolean",
                    "description": "True — створити навіть якщо назва вже зайнята.",
                },
                "dry_run": {"type": "boolean"},
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="worqen_ws_create_sheet",
        description=(
            "Worqen workspace: створює новий gsheet (default) або xlsx у Worqen Drive. "
            "Опційно — header row через параметр columns (1D-list)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "parent_folder": {
                    "type": "string",
                    "description": "Папка-батько: name substring або Drive ID.",
                },
                "format": {
                    "type": "string",
                    "enum": ["gsheet", "xlsx"],
                    "description": "Тип файлу. Default: gsheet.",
                },
                "columns": {
                    "type": "array",
                    "description": "Опційний header row (1D-list імен колонок).",
                    "items": {"type": "string"},
                },
                "allow_duplicate": {"type": "boolean"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="worqen_ws_create_folder",
        description=(
            "Worqen workspace: створює нову папку у Worqen Drive. "
            "parent_folder необов'язковий — default корінь Worqen Drive."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "parent_folder": {
                    "type": "string",
                    "description": "Папка-батько: name substring або Drive ID.",
                },
                "allow_duplicate": {"type": "boolean"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["name"],
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
    # ---- READ ----
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

    # ---- WRITE: DOCS ----
    if name == "worqen_ws_replace_text":
        return ws_writer.ws_replace_text(
            query=args["query"],
            old_text=args["old_text"],
            new_text=args["new_text"],
            dry_run=args.get("dry_run", False),
            force_overwrite=args.get("force_overwrite", False),
        )

    if name == "worqen_ws_insert_text":
        return ws_writer.ws_insert_text(
            query=args["query"],
            text=args["text"],
            mode=args.get("mode", "end_of_doc"),
            anchor=args.get("anchor"),
            dry_run=args.get("dry_run", False),
            force_overwrite=args.get("force_overwrite", False),
            as_paragraph=args.get("as_paragraph", True),
        )

    if name == "worqen_ws_replace_section":
        return ws_writer.ws_replace_section(
            query=args["query"],
            heading=args["heading"],
            new_content=args["new_content"],
            dry_run=args.get("dry_run", False),
            force_overwrite=args.get("force_overwrite", False),
        )

    # ---- WRITE: SHEETS ----
    if name == "worqen_ws_update_cell":
        return ws_sheet_writer.ws_update_cell(
            query=args["query"],
            sheet=args["sheet"],
            cell=args["cell"],
            value=args["value"],
            dry_run=args.get("dry_run", False),
            force_overwrite=args.get("force_overwrite", False),
        )

    if name == "worqen_ws_update_range":
        return ws_sheet_writer.ws_update_range(
            query=args["query"],
            sheet=args["sheet"],
            range_a1=args["range"],
            values=args["values"],
            dry_run=args.get("dry_run", False),
            force_overwrite=args.get("force_overwrite", False),
        )

    if name == "worqen_ws_append_row":
        return ws_sheet_writer.ws_append_row(
            query=args["query"],
            sheet=args["sheet"],
            values=args["values"],
            copy_style_from_last=args.get("copy_style_from_last", True),
            dry_run=args.get("dry_run", False),
            force_overwrite=args.get("force_overwrite", False),
        )

    # ---- CREATE ----
    if name == "worqen_ws_create_doc":
        return ws_creator.ws_create_doc(
            name=args["name"],
            parent_folder=args.get("parent_folder"),
            format=args.get("format", "gdoc"),
            initial_content=args.get("initial_content", ""),
            allow_duplicate=args.get("allow_duplicate", False),
            dry_run=args.get("dry_run", False),
        )

    if name == "worqen_ws_create_sheet":
        return ws_creator.ws_create_sheet(
            name=args["name"],
            parent_folder=args.get("parent_folder"),
            format=args.get("format", "gsheet"),
            columns=args.get("columns"),
            allow_duplicate=args.get("allow_duplicate", False),
            dry_run=args.get("dry_run", False),
        )

    if name == "worqen_ws_create_folder":
        return ws_creator.ws_create_folder(
            name=args["name"],
            parent_folder=args.get("parent_folder"),
            allow_duplicate=args.get("allow_duplicate", False),
            dry_run=args.get("dry_run", False),
        )

    return None

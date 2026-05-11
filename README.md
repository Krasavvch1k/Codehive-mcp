# CodeHive mcp

Multi-project MCP-сервер для CodeHive Agency. Обслуговує два продукти у одному codebase:

- **Worqen** — продуктовий: User Stories, Bug Report, Roadmap, технічна документація, обговорення з командою (xlsx + Google Docs у `Worqen` shared folder).
- **CodeHive Agency** — read-only доступ до shared drive `CodeHive Agency` (gdoc/gsheet/gslides, ієрархічний обхід).

Сервер під'єднується до Claude Desktop через MCP (Streamable HTTP transport через cloudflared), і дає Claude можливість читати/редагувати документи напряму у Google Drive — без копіпасту.

## Що вміє

**37 tools** у двох групах за префіксом:

### Worqen (`worqen_*`, 33 tools)

**User Stories (xlsx):**
- `worqen_list_user_stories`, `worqen_get_user_story`, `worqen_find_us_dependents`
- `worqen_next_us_id`
- `worqen_update_user_story`, `worqen_create_user_story` (з опціональним `use_id` для заповнення пропусків)

**Bug Report (xlsx):**
- `worqen_list_bugs`, `worqen_get_bug`, `worqen_bugs_summary`
- `worqen_next_bug_id`
- `worqen_update_bug`, `worqen_create_bug`

**Документи (docx/gdoc):**
- `worqen_list_doc_sections`, `worqen_get_doc_section`, `worqen_get_doc_block`, `worqen_get_doc_full_text`
- `worqen_search_in_doc`

**Аналітика і валідація:**
- `worqen_bulk_validate_references` — broken refs у Dependencies + цикли (Tarjan SCC)
- `worqen_detect_conflicts` — заборонені терміни, застарілі числа, відкриті питання
- `worqen_validate_id_format`
- `worqen_epics_summary`, `worqen_list_open_questions`
- `worqen_list_ficha`

**Обговорення з командою (Google Docs):**
- `worqen_list_team_discussions`, `worqen_read_team_discussion`, `worqen_search_team_discussions`

**Службові:**
- `worqen_list_files`, `worqen_check_drive_sync`, `worqen_clear_cache`
- `worqen_save_snapshot`, `worqen_list_snapshots`, `worqen_session_changes`
- `worqen_get_session_writes`

### CodeHive Agency (`codehive_*`, 4 tools)

- `codehive_list_folder` — список файлів і підпапок (1 рівень)
- `codehive_list_all_docs` — рекурсивний обхід (BFS, max_depth)
- `codehive_read_doc` — gdoc → markdown
- `codehive_search` — пошук по назві та вмісту

## Стек

- Python 3.13
- MCP SDK (Streamable HTTP, через Starlette)
- Google Drive API + Google Docs API (OAuth user flow)
- openpyxl (xlsx), python-docx (docx)
- cloudflared (тунель для Claude Desktop ↔ локальний сервер)

## Архітектура

```
Codehive-mcp/
├── server.py                  # тонкий transport-shell, dispatch у проєкти
├── shared/                    # generic infrastructure
│   ├── auth.py                # OAuth credentials
│   ├── config.py              # загальні константи (ліміти, шляхи)
│   ├── drive_client.py        # Drive API wrapper + TTL cache
│   ├── snapshot.py            # xlsx state snapshotting
│   ├── response_utils.py      # формат MCP відповідей
│   ├── safety.py              # SafetyError, drive sync check
│   ├── writes_log.py          # журнал write-операцій
│   └── gdoc.py                # docx → markdown (для всіх проєктів)
├── projects/
│   ├── worqen/                # 33 worqen_* tools
│   │   ├── config.py          # FILE_IDS, whitelist полів
│   │   ├── safety.py          # worqen-specific (ensure_today_snapshot)
│   │   ├── tools.py           # WORQEN_TOOLS + worqen_dispatch
│   │   ├── parsers/           # 6 файлів (US, BUG, docs, team_discussions, refs, analytics)
│   │   └── writers/           # us_writer, bug_writer
│   └── codehive/              # 4 codehive_* tools
│       ├── config.py          # CODEHIVE_ROOT_FOLDER_ID
│       ├── gdoc_reader.py     # list_folder, read_doc, search
│       └── tools.py           # CODEHIVE_TOOLS + codehive_dispatch
├── tests/                     # smoke tests (за поверхнею)
│   ├── shared/
│   ├── worqen/
│   └── codehive/
└── scripts/
    └── legacy/                # debug-скрипти (inspect_docx, inspect_xlsx тощо)
```

**Принцип**: `shared/` нічого не знає про проєкти. Проєкти знають про `shared/`, але не одне про одного. Сервер імпортує `<project>.tools` і агрегує `*_TOOLS + *_TOOLS`.

## Як додати новий проєкт

1. Створити `projects/<name>/` зі структурою:
   ```
   projects/<name>/
   ├── __init__.py
   ├── config.py        # проєктні константи
   ├── tools.py         # <NAME>_TOOLS список + <name>_dispatch(name, args, format_response)
   └── <feature>.py     # бізнес-логіка
   ```

2. У `<name>/tools.py`:
   - Назвати кожен tool з префіксом `<name>_*` (щоб уникнути конфліктів між проєктами).
   - Експортувати константу `<NAME>_TOOLS: list[Tool]`.
   - Експортувати функцію `<name>_dispatch(name, args, format_response) -> list[TextContent] | None`. Повертає `None` якщо tool — не з цього проєкту (щоб обгортка спробувала наступний dispatcher).

3. У `server.py`:
   - Імпортувати `<NAME>_TOOLS` і `<name>_dispatch`.
   - Додати у `list_tools()`: `return WORQEN_TOOLS + CODEHIVE_TOOLS + <NAME>_TOOLS`.
   - Додати у `call_tool()`: ще один блок `result = <name>_dispatch(...); if result is not None: return result`.

4. Якщо проєкту потрібна project-specific safety/snapshot — створити `projects/<name>/safety.py` що re-exportує generic з `shared.safety` і додає свої утиліти.

5. Якщо проєкту потрібні нові generic-утиліти — спочатку класти у проєкт, виносити у `shared/` коли стає очевидним що це треба ще одному проєкту (DRY-витяг, а не upfront generalization).

## Встановлення

```bash
git clone https://github.com/Krasavvch1k/Codehive-mcp.git
cd Codehive-mcp

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Google Drive credentials

OAuth user flow:

1. Створи OAuth credentials у [Google Cloud Console](https://console.cloud.google.com/apis/credentials):
   - Тип: **Desktop app**
   - Увімкни **Drive API** і **Docs API** для проєкту
2. Скачай JSON-ключ, перейменуй на `credentials.json`, поклади у корінь репо.
3. При першому запуску сервера відкриється браузер для авторизації. Після авторизації створиться `token.json` (у репо НЕ комітиться).

> `credentials.json` і `token.json` обидва у `.gitignore`. Не коміть.

### `.env` з file IDs

```bash
cp .env.example .env
```

Заповни справжніми ID файлів зі свого Drive (їх можна знайти у URL: `docs.google.com/.../d/{FILE_ID}/edit` для документів, `drive.google.com/drive/folders/{FOLDER_ID}` для папок).

## Як запускати

Сервер працює через **Streamable HTTP + cloudflared tunnel** (не stdio). Двотермінальна процедура — див. **[RUN.md](RUN.md)**.

Коротко:

```bash
# Термінал 1
source venv/bin/activate && python3 server.py

# Термінал 2
cloudflared tunnel --url http://localhost:8765
# → скопіювати https://<random>.trycloudflare.com URL, додати "/mcp", вставити у Claude Desktop Connector
```

## Безпека

- `credentials.json`, `token.json`, `.env` — у `.gitignore`.
- `FILE_IDS` читаються тільки з env (`os.getenv`); у коді нема hardcoded ID.
- **Whitelist полів у writers** — Claude не редагує системні поля (`Status`, `Priority`, `Version`, `Epic` у US; аналогічні у BUG). Зміна цих полів — тільки людиною руками.
- **Drive sync check перед кожним write** — порівнюється `modifiedTime` Drive з baseline, який writer запам'ятав на початку операції. Якщо файл змінився між читанням і записом — операція скасовується.
- **Auto snapshot перед першим write за день** — стан xlsx серіалізується у JSON. Можна порівняти зі станом через `worqen_session_changes`.
- **`worqen_get_session_writes`** — журнал успішних writes за день (поля, час, file_id, before/after — пам'ять про що Claude зробив).

## Ліцензія

Internal tool. Public for transparency / reusability of parts.

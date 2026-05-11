# worqen-mcp

MCP-сервер для роботи з документами проєкту [Worqen](https://worqen.com) у Google Drive.

Сервер під'єднується до Claude Desktop через MCP (Model Context Protocol) і дає Claude можливість читати та редагувати User Stories, Bug Report, Roadmap, технічну документацію і PRD напряму в Google Drive — без копіпасту.

## Що вміє

**33 tools** розділені на групи:

### User Stories (xlsx)
- `list_user_stories` — список з фільтрами (epic, status, priority, version, search)
- `get_user_story` — повна US за ID
- `find_us_dependents` — US які залежать від указаної
- `next_us_id` — наступний вільний US-XXX
- `update_user_story` — оновлення whitelist-полів
- `create_user_story` — створення нової US (з опціональним `use_id` для заповнення пропусків)

### Bug Report (xlsx)
- `list_bugs`, `get_bug`, `bugs_summary`
- `next_bug_id`
- `update_bug`, `create_bug` (з тими ж параметрами що й US)

### Документи (docx/gdoc)
- `list_doc_sections` — TOC документа з breadcrumbs
- `get_doc_section`, `get_doc_block`, `get_doc_full_text`
- `search_in_doc`

### Аналітика і валідація
- `bulk_validate_references` — broken refs у US/BUG + цикли у Dependencies (Tarjan SCC)
- `detect_conflicts` — заборонені терміни, застарілі числа, відкриті питання
- `epics_summary` — статистика по епіках
- `list_open_questions` — сторі що чекають рішень PO

### Обговорення з командою (Google Docs)
- `list_team_discussions`, `read_team_discussion`, `search_team_discussions`

### Службові
- `list_files` — усі файли які знає сервер
- `check_drive_sync` — діагностика синхронізації
- `clear_cache`, `save_snapshot`, `list_snapshots`, `session_changes`
- `get_session_writes` — журнал успішних writes за день

## Стек

- Python 3.10+
- MCP SDK (stdio transport)
- Google Drive API (read + write)
- openpyxl (xlsx)
- python-docx (docx)
- dotenv

## Встановлення

```bash
git clone https://github.com/Krasavvch1k/worqen-mcp.git
cd worqen-mcp

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

> Якщо `requirements.txt` ще немає — встанови вручну:
> ```bash
> pip install mcp google-api-python-client google-auth-httplib2 google-auth-oauthlib \
>             openpyxl python-docx python-dotenv
> ```

## Налаштування

### 1. Google Drive credentials

Створи OAuth credentials у [Google Cloud Console](https://console.cloud.google.com/apis/credentials):
- Тип: **Desktop app**
- Включи Drive API і Docs API для проєкту
- Скачай `credentials.json`, поклади у корінь репо

При першому запуску відкриється браузер для авторизації. Після авторизації створиться `token.json` — у репо НЕ комітиться.

### 2. `.env` з file IDs

Скопіюй шаблон:

```bash
cp .env.example .env
```

Заповни `.env` справжніми ID файлів зі свого Drive (їх можна знайти у URL файлу: `docs.google.com/.../d/{FILE_ID}/edit`).

### 3. Підключення до Claude Desktop

Додай у `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "worqen-mcp": {
      "command": "/абсолютний/шлях/до/worqen-mcp/venv/bin/python",
      "args": ["/абсолютний/шлях/до/worqen-mcp/server.py"]
    }
  }
}
```

Перезапусти Claude Desktop.

## Структура проєкту

```
worqen-mcp/
├── server.py              — MCP сервер, реєстрація tools
├── config.py              — конфіг (FILE_IDS читаються з .env)
├── drive_client.py        — обгортка над Google Drive API
├── snapshot.py            — auto snapshot xlsx файлів
├── response_utils.py      — формат відповідей tools
├── parsers/
│   ├── user_stories.py   — парсинг US xlsx
│   ├── bug_report.py     — парсинг BUG xlsx
│   ├── docs.py           — парсинг docx (структура секцій)
│   ├── team_discussions.py — Google Docs обговорень
│   ├── references.py     — broken refs + Tarjan SCC цикли
│   └── analytics.py      — detect_conflicts, summaries
├── writers/
│   ├── us_writer.py      — оновлення/створення US
│   ├── bug_writer.py     — оновлення/створення BUG
│   ├── safety.py         — Drive sync check, whitelists
│   └── writes_log.py     — журнал успішних writes
├── snapshots/             — auto snapshots (gitignored)
└── writes_log/            — журнал writes по днях (gitignored)
```

## Безпека

- `credentials.json`, `token.json`, `.env` — у `.gitignore`, ніколи не комітимо
- `FILE_IDS` читаються тільки через `os.getenv` — у коді немає захардкоджених ID
- Whitelist полів у writers — Status / Priority / Version / Epic у US (і відповідні в BUG) Claude не редагує, тільки людина
- Drive sync check перед кожним write — захист від race condition між сесіями
- Auto snapshot перед першим write за день — можна відкотити стан через `session_changes`

## Ліцензія

Internal tool. Public for transparency / reusability of parts.

# CodeHive mcp — Інструкція з запуску і вимкнення

## ЩО ЦЕ

Локальний MCP-сервер який дає Claude Desktop доступ до робочих файлів
у Google Drive: Worqen-документи (User Stories, Bug Report, PRD, Tech Doc)
і CodeHive Agency shared drive.

Сервер працює на твоєму компі. Cloudflared тунель робить його доступним
для Claude Desktop по тимчасовому HTTPS URL.

Папка проєкту: `~/Documents/Codehive-mcp`

Повний перелік tools і архітектура — у [README.md](README.md).

---

## ЗАПУСК (КОЖНОГО РАЗУ КОЛИ ХОЧЕШ ПРАЦЮВАТИ)

Тобі потрібні **два термінальних вікна** одночасно.
Закриєш одне — все перестане працювати.

### Термінал 1 — сервер

```bash
cd ~/Documents/Codehive-mcp
source venv/bin/activate
python3 server.py
```

Має з'явитись: `Uvicorn running on http://127.0.0.1:8765`

Залиш це вікно у спокої. **НЕ ЗАКРИВАЙ.**

> **При першому запуску** відкриється браузер для OAuth-авторизації Google.
> Підтверди доступ → створиться `token.json`. У наступні рази
> авторизація не потрібна — токен оновлюється сам.

### Термінал 2 — тунель

Відкрий нове вікно термінала (Cmd+N у Terminal).

```bash
cloudflared tunnel --url http://localhost:8765
```

Через 5-15 секунд у виводі буде блок з URL:
`https://<random-words>.trycloudflare.com`

**Скопіюй цей URL.** До нього треба додати `/mcp` у кінці.

Приклад: якщо тунель видав
`https://words-words-words.trycloudflare.com`,
то для Claude Desktop URL буде
`https://words-words-words.trycloudflare.com/mcp`

**НЕ ЗАКРИВАЙ ЦЕ ВІКНО.**

### Claude Desktop — оновити URL

⚠️ Тимчасові тунелі cloudflared дають **новий URL щоразу**.
Тому при кожному перезапуску тунеля треба оновити URL у Claude.

1. Claude Desktop → **Customize → Connectors**
2. Знайди **Codehive-mcp** → відкрий
3. Edit (або видали і додай заново)
4. Встав новий URL з `/mcp` у кінці
5. **Connect**

Після підключення — у новому чаті `+` біля поля вводу → увімкни галочку Codehive-mcp.

---

## ВИКОРИСТАННЯ

У будь-якому чаті Claude Desktop, наприклад:

- "Покажи user stories у статусі Не реалізовано та пріоритеті Must"
- "Покажи US-062"
- "Скільки P1 багів виправлено?"
- "Знайди в Tech Doc секцію '3.7 Events'"
- "Знайди слово 'commission' у Tech Doc"
- "Який наступний US-XXX?"
- "Покажи всі Ficha які ще не перенесені в US"
- "Що зараз у папці CodeHive Agency у Drive?"

Claude сам обере правильний tool (з префіксом `worqen_*` або `codehive_*`) і викличе його.

---

## ВИМКНЕННЯ

### Коли закінчив роботу

1. Термінал 2 (тунель): натисни **Ctrl+C**
2. Термінал 1 (сервер): натисни **Ctrl+C**
3. Закрий вікна терміналу якщо треба

Сервер не споживає ресурси коли не запущений.
Жодних фонових процесів не лишається.

### Якщо щось зависло

```bash
pkill -f "python3 server.py"
pkill -f "cloudflared"
```

---

## ЯКЩО ЩОСЬ НЕ ПРАЦЮЄ

### "Connection failed" у Claude Desktop

1. Перевір що сервер живий — у Терміналі 1 не має бути помилок
2. Перевір що тунель живий — у Терміналі 2 не має бути ERR
3. Перевір що URL у Claude Desktop правильний (з `/mcp` у кінці)
4. Тимчасовий URL міг змінитись — звіряй з тим що зараз показує Термінал 2

### "Файл не знайдено" або старі дані

```
worqen_clear_cache
```

Викличе скидання кешу. Або просто почекай 60 секунд — TTL автоматичний.

### Claude бачить старі назви тулів (без префікса)

Connector у Claude UI кешує schema агресивно. Після рестарту сервера
старі назви можуть жити ще 5-10 хвилин. Рішення:
- Disconnect/connect connector у Claude Desktop руками, або
- Просто почекати.

### Тунель помер сам по собі

Перезапусти `cloudflared tunnel --url http://localhost:8765`,
скопіюй новий URL, онови у Claude Desktop.

### Хочу перевірити з'єднання без Claude Desktop

```bash
curl -X POST https://твій-тунель.trycloudflare.com/mcp/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1"}}}'
```

Якщо повертає JSON — сервер живий.

---

## ЯК ЗВІЛЬНИТИСЬ ВІД РИТУАЛУ ЗАПУСКУ

Якщо набридне щодня запускати два термінали — є два шляхи:

1. **Bash-скрипт** який стартує обидва процеси однією командою (lazy variant).
2. **VPS $5/міс** — сервер живе постійно, URL не змінюється,
   жодних запусків. Питання комфорту vs $60/рік.

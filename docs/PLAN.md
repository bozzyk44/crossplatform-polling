# Cross-Platform Poll Aggregator Bot — Implementation Plan

## Цель

Единая система, которая создаёт нативные опросы в Telegram и VK, агрегирует голоса в реальном времени и отображает сводные результаты через companion-message на каждой платформе.

---

## Архитектура

```
┌─────────────┐     webhook      ┌──────────────────┐     callback     ┌─────────────┐
│  Telegram   │ ──────────────▸  │                  │  ◂────────────── │     VK      │
│  Bot API    │ ◂──────────────  │   Core Backend   │  ──────────────▸ │  API        │
│             │   sendPoll /     │   (FastAPI)       │   polls.create / │             │
│             │   editMessage    │                  │   wall.post      │             │
└─────────────┘                  │   ┌──────────┐  │                  └─────────────┘
                                 │   │ SQLite / │  │
                                 │   │ Postgres │  │
                                 │   └──────────┘  │
                                 │                  │
                                 │   Admin API /    │
                                 │   CLI             │
                                 └──────────────────┘
```

---

## Стек

- **Python 3.11+**
- **FastAPI** — HTTP-сервер, webhooks, admin API
- **aiogram 3.x** — Telegram-адаптер
- **httpx** — асинхронный HTTP-клиент для прямых вызовов VK API (вместо vkbottle — нестабильна)
- **SQLAlchemy + alembic** — ORM и миграции
- **PostgreSQL** — основная БД (через asyncpg)
- **Pydantic** — валидация данных
- **uvicorn** — ASGI-сервер

---

## Структура проекта

```
poll-aggregator/
├── alembic/                    # Миграции БД
├── app/
│   ├── __init__.py
│   ├── main.py                 # Точка входа: FastAPI app + lifecycle
│   ├── config.py               # Pydantic Settings (env vars)
│   ├── database/
│   │   ├── __init__.py
│   │   ├── engine.py           # create_engine, sessionmaker
│   │   └── models.py           # SQLAlchemy-модели
│   ├── core/
│   │   ├── __init__.py
│   │   ├── schemas.py          # Pydantic-схемы (CreatePoll, Vote, AggregatedResult)
│   │   ├── poll_service.py     # Бизнес-логика: создание опроса, запись голоса, агрегация
│   │   └── aggregator.py       # Пересчёт результатов + триггер обновления companion-messages
│   ├── platforms/
│   │   ├── __init__.py
│   │   ├── base.py             # ABC PlatformAdapter (create_poll, send_companion, update_companion)
│   │   ├── telegram/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py      # TelegramAdapter(PlatformAdapter)
│   │   │   ├── bot.py          # Инициализация aiogram Bot + Dispatcher
│   │   │   └── handlers.py     # poll_answer handler, команды (/newpoll, /status)
│   │   └── vk/
│   │       ├── __init__.py
│   │       ├── adapter.py      # VKAdapter(PlatformAdapter)
│   │       ├── client.py        # Тонкая обёртка над httpx для VK API
│   │       └── handlers.py     # poll_vote_new handler, fallback polling
│   └── admin/
│       ├── __init__.py
│       └── routes.py           # REST API для создания/управления опросами
├── tests/
├── .env.example
├── alembic.ini
├── pyproject.toml
└── README.md
```

---

## Модели данных

### Survey (опрос)

| Поле         | Тип              | Описание                          |
|-------------|------------------|-----------------------------------|
| id          | UUID, PK         | Уникальный ID опроса              |
| title       | str              | Текст вопроса                     |
| options     | JSON (list[str]) | Варианты ответов                  |
| is_active   | bool             | Активен ли опрос                  |
| created_at  | datetime         | Время создания                    |
| closed_at   | datetime, null   | Время закрытия                    |

### PlatformPoll (нативный опрос на платформе)

| Поле                   | Тип          | Описание                                     |
|-----------------------|--------------|----------------------------------------------|
| id                    | int, PK      |                                              |
| survey_id             | FK → Survey  |                                              |
| platform              | enum(tg, vk) | Платформа                                    |
| native_poll_id        | str          | ID нативного опроса (Telegram poll_id / VK)  |
| chat_id               | str          | ID чата/группы/канала                        |
| companion_message_id  | str          | ID сообщения с агрегированными результатами  |

### Vote (голос)

| Поле              | Тип          | Описание                        |
|------------------|--------------|----------------------------------|
| id               | int, PK      |                                  |
| survey_id        | FK → Survey  |                                  |
| platform         | enum(tg, vk) |                                  |
| platform_user_id | str          | ID пользователя на платформе     |
| option_index     | int          | Индекс выбранного варианта       |
| voted_at         | datetime     |                                  |

**Уникальный constraint:** `(survey_id, platform, platform_user_id)` — один голос на пользователя на платформу. При повторном голосовании — UPDATE.

---

## Этапы реализации

### Этап 1 — Фундамент

**Задачи:**
1. Инициализировать проект: `pyproject.toml`, зависимости, `.env.example`
2. Настроить `app/config.py` — Pydantic Settings с переменными: `TELEGRAM_BOT_TOKEN`, `VK_GROUP_TOKEN`, `VK_GROUP_ID`, `DATABASE_URL`, `WEBHOOK_BASE_URL`
3. Создать SQLAlchemy-модели (`Survey`, `PlatformPoll`, `Vote`) и настроить alembic
4. Написать `poll_service.py`:
   - `create_survey(title, options) → Survey`
   - `record_vote(survey_id, platform, user_id, option_index) → None` (upsert)
   - `get_aggregated_results(survey_id) → dict` — подсчёт по option_index с разбивкой по платформам
5. Покрыть `poll_service` тестами

**Результат:** работающее ядро без привязки к платформам.

---

### Этап 2 — Telegram-адаптер

**Задачи:**
1. Инициализировать aiogram 3.x Bot и Dispatcher в `platforms/telegram/bot.py`
2. Реализовать `TelegramAdapter`:
   - `create_poll(survey, chat_id)` — вызывает `bot.send_poll(is_anonymous=False, ...)`, сохраняет `PlatformPoll`
   - `send_companion(survey, chat_id)` — отправляет форматированное сообщение с текущими результатами
   - `update_companion(survey)` — `bot.edit_message_text(...)` с пересчитанными данными
3. Обработчик `poll_answer`:
   - Найти `survey_id` по `poll_id` через `PlatformPoll`
   - Вызвать `record_vote`
   - Вызвать `aggregator.on_vote(survey_id)` → обновить companion-messages на всех платформах
4. Форматирование companion-message:
   ```
   📡 Результаты (все платформы):
   ▸ Лекции     — 1208 (44%)  [TG: 312 · VK: 896]
   ▸ Воркшопы   —  814 (30%)  [TG: 230 · VK: 584]
   ───────────────────────
   Всего: 2745 · Обновлено 12:03
   ```
5. Настроить webhook: `POST /webhook/telegram` в FastAPI, при старте — `bot.set_webhook`
6. Команда `/newpoll` для админов (проверка chat_id или user_id по whitelist)

**Результат:** рабочий Telegram-бот, создающий опросы и обновляющий companion в реальном времени.

---

### Этап 3 — VK-адаптер

**Задачи:**
1. Реализовать `VKClient` — тонкая обёртка над `httpx.AsyncClient` для VK API (`platforms/vk/client.py`):
   - Методы: `call(method, params)`, автоматическая подстановка `access_token` и `v`
   - Обработка ошибок VK API, retry через tenacity при 429/rate-limit
2. Настроить Callback API endpoint: `POST /webhook/vk` в FastAPI (confirmation string + event handling)
3. Реализовать `VKAdapter`:
   - `create_poll(survey, owner_id)` — `polls.create(...)`, затем `wall.post(attachments=poll_...)` в группу
   - `send_companion(survey, peer_id)` — отдельное сообщение / комментарий под постом
   - `update_companion(survey)` — редактирование companion-message
4. Обработчик события `poll_vote_new`:
   - Payload содержит `poll_id`, `user_id`, `option_id`
   - `record_vote` → `aggregator.on_vote`
5. Fallback: если `poll_vote_new` не приходит (анонимный опрос), запустить фоновую задачу:
   - `polls.getById` через `VKClient` с адаптивным интервалом
   - Сравнить счётчики с предыдущим snapshot'ом
   - При изменении — обновить companion
   - Backoff при 429: экспоненциально увеличивать интервал
6. Обработка VK-специфики: опросы прикрепляются к постам на стене, companion может быть комментарием или отдельным постом

**Результат:** VK-бот с push-событиями, companion-message обновляется синхронно с Telegram.

---

### Этап 4 — Aggregator и real-time обновления

**Задачи:**
1. `aggregator.on_vote(survey_id)`:
   - Получить агрегированные результаты из `poll_service`
   - Найти все `PlatformPoll` для этого `survey_id`
   - Вызвать `update_companion` на каждом адаптере
2. Rate-limit буфер для Telegram (max 1 edit/sec per message):
   - Собирать голоса в очередь
   - Flush каждые 2 секунды: один `edit_message_text` с актуальными данными
   - Реализовать через `asyncio` task с `asyncio.Queue`
3. Rate-limit буфер для VK (аналогично, ~3 req/s общий лимит)
4. Тесты: симуляция потока голосов с двух платформ, проверка корректности агрегации

**Результат:** голос на любой платформе обновляет companion-messages везде за 2–3 секунды.

---

### Этап 5 — Admin API

**Задачи:**
1. REST-эндпоинты в `admin/routes.py`:
   - `POST /api/surveys` — создать опрос, автоматически публикует на всех платформах
   - `GET /api/surveys` — список опросов
   - `GET /api/surveys/{id}/results` — агрегированные результаты (JSON)
   - `POST /api/surveys/{id}/close` — закрыть опрос (`stopPoll` в TG, пометить как неактивный)
2. Простая авторизация: API-ключ в заголовке `X-API-Key`, проверка через middleware
3. CLI-обёртка (опционально): `python -m app.cli create "Вопрос?" "Вариант 1" "Вариант 2"`

**Результат:** возможность управлять опросами через HTTP или командную строку.

---

### Этап 6 — Надёжность и деплой

**Задачи:**
1. Graceful shutdown: при остановке сервера — flush буферов, финальное обновление companion
2. Логирование: structlog, уровни по модулям
3. Retry-логика для API-вызовов к Telegram/VK (tenacity)
4. Dockerfile + docker-compose (app + postgres)
5. Health-check endpoint: `GET /health`
6. README с инструкцией по деплою

**Результат:** production-ready сервис для VPS.

---

## Переменные окружения (.env)

```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
VK_GROUP_TOKEN=vk1.a.xxx...
VK_GROUP_ID=123456789
VK_CONFIRMATION_STRING=a1b2c3d4
DATABASE_URL=postgresql+asyncpg://poll_user:poll_pass@db:5432/poll_aggregator
WEBHOOK_BASE_URL=https://your-server.com
ADMIN_API_KEY=your-secret-key
```

---

## Порядок работы с Claude Code

При работе с Claude Code рекомендуется реализовывать проект поэтапно, каждый этап — отдельный промпт:

1. «Реализуй Этап 1» — после завершения проверить тесты
2. «Реализуй Этап 2» — проверить вручную с тестовым Telegram-ботом
3. И так далее

Между этапами можно вносить корректировки: «Добавь поддержку multiple choice в модель Vote» или «Измени формат companion-message».

---

## Открытые вопросы

- **Дедупликация**: не реализуется — считаем голоса, а не уникальных людей. Это прозрачно для пользователей.
- **Анонимные опросы в Telegram**: `poll_answer` не приходит при `is_anonymous=True`. Варианты: либо делать не анонимные, либо ловить `poll` update (только общие счётчики без user_id).
- **VK companion как комментарий или пост**: комментарий логичнее (привязан к посту с опросом), но editing capabilities у комментариев ограничены — проверить API.
- **Масштабирование**: при >10 параллельных опросов с высокой активностью — выделять background worker для обновлений.

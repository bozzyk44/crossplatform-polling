# Cross-Platform Poll Aggregator Bot

Единая система для создания нативных опросов в Telegram и VK с агрегацией голосов в реальном времени.

## Возможности

- Создание нативных опросов одновременно в Telegram и VK
- Агрегация голосов в реальном времени из обеих платформ
- Companion-message с обновляемой сводкой результатов
- Admin API для управления опросами
- VK OAuth — любой админ группы подключает бота через веб-интерфейс
- Шифрование токенов в БД (Fernet/AES)
- Деплой через Docker на VPS с CI/CD (GitHub Actions)

## Стек

- **Python 3.11+** / FastAPI / uvicorn
- **PostgreSQL** — хранилище данных
- **aiogram 3.x** — Telegram Bot API
- **httpx** — прямые вызовы VK API (Callback API)
- **SQLAlchemy 2.x + Alembic** — ORM и миграции
- **Docker + docker-compose** — контейнеризация
- **cryptography** — шифрование VK-токенов (Fernet)

## Быстрый старт

### 1. Клонировать и настроить

```bash
git clone <repo-url>
cd crossplatform-polling

cp .env.example .env
# Заполнить переменные в .env (см. таблицу ниже)
```

### 2. Запустить

```bash
docker compose up -d
```

### 3. Настроить ботов

- **Telegram**: создать бота через [@BotFather](https://t.me/BotFather), записать токен в `.env`
- **VK**: создать Standalone-приложение, настроить OAuth

Подробные инструкции: [docs/setup-bots.md](docs/setup-bots.md)

## Переменные окружения

См. [.env.example](.env.example) для полного списка.

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота от @BotFather |
| `VK_APP_ID` | ID VK-приложения (Standalone) |
| `VK_APP_SECRET` | Защищённый ключ VK-приложения |
| `VK_TOKEN_ENCRYPTION_KEY` | Ключ Fernet для шифрования токенов в БД |
| `DATABASE_URL` | URL подключения к PostgreSQL |
| `WEBHOOK_BASE_URL` | Публичный URL сервера (HTTPS) для вебхуков |
| `ADMIN_API_KEY` | Ключ для Admin API |

## Архитектура

### Telegram

Стандартный бот — добавляется в любой чат/группу, принимает команды и обрабатывает голоса через webhook.

### VK (мультитенантный OAuth)

Бот работает как независимый сервис. Любой админ VK-группы может подключить свою группу:

1. Переходит на `https://your-server.com/vk/connect`
2. Авторизуется через VK OAuth, выдаёт права
3. Выбирает группу из списка (где он админ)
4. Бот автоматически сохраняет зашифрованный токен, настраивает Callback API

Токены хранятся в БД зашифрованными (Fernet/AES-128). Каждая группа получает свой webhook: `/webhook/vk/{group_id}`.

### Безопасность

- Токены VK-групп шифруются перед записью в БД
- CSRF-защита в OAuth через `state` параметр
- Webhook проверяет `group_id` в payload vs URL
- Отключение группы стирает токен из БД
- Admin API защищён ключом в заголовке `X-API-Key`
- Минимальные OAuth-скоупы: `groups`, `wall`

## Структура проекта

```
app/
├── main.py              # FastAPI app + lifecycle
├── config.py            # Настройки (env vars)
├── logging_config.py    # structlog конфигурация
├── database/
│   ├── engine.py        # SQLAlchemy async engine
│   └── models.py        # Survey, PlatformPoll, Vote, ConnectedGroup
├── core/
│   ├── schemas.py       # Pydantic-схемы
│   ├── poll_service.py  # Бизнес-логика
│   ├── aggregator.py    # Агрегация + rate-limit буфер обновлений
│   └── crypto.py        # Шифрование/дешифрование токенов
├── platforms/
│   ├── base.py          # ABC PlatformAdapter
│   ├── telegram/
│   │   ├── bot.py       # aiogram Bot + Dispatcher
│   │   ├── adapter.py   # TelegramAdapter
│   │   └── handlers.py  # /newpoll, poll_answer
│   └── vk/
│       ├── client.py    # httpx обёртка для VK API
│       ├── adapter.py   # VKAdapter (per-group)
│       ├── handlers.py  # Callback API webhook
│       └── oauth.py     # OAuth флоу для подключения групп
└── admin/
    └── routes.py        # REST API для управления опросами
```

## Admin API

Все эндпоинты требуют заголовок `X-API-Key`.

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/api/surveys` | Создать опрос |
| `GET` | `/api/surveys` | Список опросов |
| `GET` | `/api/surveys/{id}/results` | Агрегированные результаты |
| `POST` | `/api/surveys/{id}/close` | Закрыть опрос |

### VK OAuth

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/vk/connect` | Начать подключение группы |
| `GET` | `/vk/callback` | OAuth callback (автоматически) |
| `POST` | `/vk/connect-group` | Выбор группы (автоматически) |
| `POST` | `/vk/disconnect/{group_id}` | Отключить группу |

### Служебные

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/health` | Health-check |
| `POST` | `/webhook/telegram` | Telegram webhook |
| `POST` | `/webhook/vk/{group_id}` | VK Callback API (per-group) |

## Деплой на VPS

```bash
# На сервере
docker compose up -d

# Применить миграции
docker compose exec app alembic upgrade head
```

CI/CD настроен через GitHub Actions — push в `main` автоматически деплоит на VPS.

## Документация

- [docs/setup-bots.md](docs/setup-bots.md) — создание ботов Telegram и VK
- [docs/PLAN.md](docs/PLAN.md) — план реализации

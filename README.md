# Cross-Platform Poll Aggregator Bot

Единая система для создания нативных опросов в Telegram и VK с агрегацией голосов в реальном времени.

## Возможности

- Создание нативных опросов одновременно в Telegram и VK
- Агрегация голосов в реальном времени из обеих платформ
- Companion-message с обновляемой сводкой результатов
- Admin API для управления опросами
- Деплой через Docker на VPS

## Стек

- **Python 3.11+** / FastAPI / uvicorn
- **PostgreSQL** — хранилище данных
- **aiogram 3.x** — Telegram Bot API
- **httpx** — прямые вызовы VK API (Callback API)
- **SQLAlchemy 2.x + Alembic** — ORM и миграции
- **Docker + docker-compose** — контейнеризация

## Быстрый старт

### Локальная разработка

```bash
# Клонировать репо
git clone <repo-url>
cd crossplatform-polling

# Создать .env из примера
cp .env.example .env
# Заполнить переменные в .env

# Запустить через Docker
docker compose up -d
```

### Переменные окружения

См. [.env.example](.env.example) для полного списка.

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота от @BotFather |
| `VK_GROUP_TOKEN` | Токен сообщества VK |
| `VK_GROUP_ID` | ID группы VK |
| `VK_CONFIRMATION_STRING` | Строка подтверждения для Callback API |
| `DATABASE_URL` | URL подключения к PostgreSQL |
| `WEBHOOK_BASE_URL` | Публичный URL сервера для вебхуков |
| `ADMIN_API_KEY` | Ключ для Admin API |

## Структура проекта

```
app/
├── main.py              # FastAPI app + lifecycle
├── config.py            # Настройки (env vars)
├── database/
│   ├── engine.py        # SQLAlchemy engine
│   └── models.py        # Модели: Survey, PlatformPoll, Vote
├── core/
│   ├── schemas.py       # Pydantic-схемы
│   ├── poll_service.py  # Бизнес-логика
│   └── aggregator.py    # Агрегация + обновление companion
├── platforms/
│   ├── base.py          # ABC PlatformAdapter
│   ├── telegram/        # Telegram-адаптер (aiogram)
│   └── vk/              # VK-адаптер (httpx + VK API)
└── admin/
    └── routes.py        # REST API для управления
```

## Деплой на VPS

```bash
# На сервере
docker compose -f docker-compose.yml up -d

# Применить миграции
docker compose exec app alembic upgrade head
```

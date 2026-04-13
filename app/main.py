from contextlib import asynccontextmanager

import structlog
from aiogram.types import Update
from fastapi import FastAPI, Request

from app.admin.routes import router as admin_router
from app.config import settings
from app.core.aggregator import start_flush_task, stop_flush_task
from app.database.engine import engine
from app.database.models import Base
from app.logging_config import setup_logging
from app.platforms.telegram.bot import bot, dp
from app.platforms.telegram.handlers import router as tg_router
from app.platforms.vk.handlers import router as vk_router

setup_logging()
logger = structlog.get_logger()

# Register Telegram handlers
dp.include_router(tg_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if settings.telegram_bot_token:
        webhook_url = f"{settings.webhook_base_url}/webhook/telegram"
        await bot.set_webhook(webhook_url)
        logger.info("telegram_webhook_set", url=webhook_url)

    start_flush_task()
    logger.info("app_started")

    yield

    stop_flush_task()
    if settings.telegram_bot_token:
        await bot.delete_webhook()
    from app.platforms.vk.client import vk_client

    await vk_client.close()
    await engine.dispose()
    logger.info("app_stopped")


app = FastAPI(title="Poll Aggregator", version="0.1.0", lifespan=lifespan)


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}


app.include_router(vk_router)
app.include_router(admin_router)


@app.get("/health")
async def health():
    return {"status": "ok"}

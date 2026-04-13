import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings
from app.core import poll_service
from app.core.schemas import AggregatedResult, CreateSurvey, SurveyOut
from app.database.engine import async_session
from app.database.models import Platform

logger = structlog.get_logger()
router = APIRouter(prefix="/api", tags=["admin"])
api_key_header = APIKeyHeader(name="X-API-Key")


async def verify_api_key(key: str = Security(api_key_header)):
    if key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")


@router.post("/surveys", response_model=SurveyOut, dependencies=[Depends(verify_api_key)])
async def create_survey(data: CreateSurvey):
    async with async_session() as session:
        survey = await poll_service.create_survey(session, data.title, data.options)

        # Publish to all configured platforms
        for platform, adapter_factory in _get_adapters():
            try:
                adapter = adapter_factory()
                chat_id = _get_chat_id(platform)
                if not chat_id:
                    continue

                native_poll_id = await adapter.create_poll(survey, chat_id)
                result = await poll_service.get_aggregated_results(session, survey.id)
                companion_id = await adapter.send_companion(survey, chat_id, result)
                await poll_service.register_platform_poll(
                    session, survey.id, platform, native_poll_id, chat_id, companion_id
                )
                logger.info("poll_published", platform=platform.value, survey_id=str(survey.id))
            except Exception:
                logger.exception("poll_publish_failed", platform=platform.value)

        return survey


@router.get("/surveys", response_model=list[SurveyOut], dependencies=[Depends(verify_api_key)])
async def list_surveys():
    from sqlalchemy import select

    from app.database.models import Survey

    async with async_session() as session:
        result = await session.execute(select(Survey).order_by(Survey.created_at.desc()))
        return list(result.scalars().all())


@router.get(
    "/surveys/{survey_id}/results",
    response_model=AggregatedResult,
    dependencies=[Depends(verify_api_key)],
)
async def get_results(survey_id: uuid.UUID):
    async with async_session() as session:
        result = await poll_service.get_aggregated_results(session, survey_id)
        if not result:
            raise HTTPException(status_code=404, detail="Survey not found")
        return result


@router.post(
    "/surveys/{survey_id}/close",
    response_model=SurveyOut,
    dependencies=[Depends(verify_api_key)],
)
async def close_survey(survey_id: uuid.UUID):
    async with async_session() as session:
        survey = await poll_service.close_survey(session, survey_id)
        if not survey:
            raise HTTPException(status_code=404, detail="Survey not found or already closed")
        return survey


def _get_adapters():
    adapters = []
    if settings.telegram_bot_token:
        from app.platforms.telegram.adapter import TelegramAdapter
        adapters.append((Platform.tg, TelegramAdapter))
    if settings.vk_group_token:
        from app.platforms.vk.adapter import VKAdapter
        adapters.append((Platform.vk, VKAdapter))
    return adapters


def _get_chat_id(platform: Platform) -> str | None:
    # Chat IDs are provided per-request in the future;
    # for now, return None (caller must provide via /newpoll command or API extension)
    return None

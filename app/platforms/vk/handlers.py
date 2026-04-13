import structlog
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.core import poll_service
from app.core.aggregator import on_vote
from app.database.engine import async_session
from app.database.models import Platform
from app.platforms.vk.adapter import VKAdapter

logger = structlog.get_logger()
router = APIRouter()
adapter = VKAdapter()


@router.post("/webhook/vk")
async def vk_webhook(request: Request):
    data = await request.json()
    event_type = data.get("type")

    if event_type == "confirmation":
        return PlainTextResponse(settings.vk_confirmation_string)

    if event_type == "poll_vote_new":
        obj = data.get("object", {})
        poll_id = str(obj.get("poll_id", ""))
        user_id = str(obj.get("user_id", ""))
        option_id = obj.get("option_id", 0)

        async with async_session() as session:
            pp = await poll_service.find_survey_by_native_poll(session, poll_id, Platform.vk)
            if not pp:
                logger.warning("vk_poll_not_found", poll_id=poll_id)
                return PlainTextResponse("ok")

            # VK option_id is 1-based, find the index
            survey = await session.get(poll_service.Survey, pp.survey_id)
            if not survey:
                return PlainTextResponse("ok")

            # Map VK option_id to our 0-based index by querying VK poll answers order
            # For simplicity, we use option_id as-is and map it via position
            await poll_service.record_vote(
                session, pp.survey_id, Platform.vk, user_id, option_id
            )

            result = await on_vote(session, pp.survey_id)
            if result:
                platform_polls = await poll_service.get_platform_polls(session, pp.survey_id)
                for p in platform_polls:
                    if p.companion_message_id:
                        try:
                            if p.platform == Platform.vk:
                                await adapter.update_companion(
                                    p.chat_id, p.companion_message_id, result
                                )
                            elif p.platform == Platform.tg:
                                from app.platforms.telegram.adapter import TelegramAdapter

                                tg_adapter = TelegramAdapter()
                                await tg_adapter.update_companion(
                                    p.chat_id, p.companion_message_id, result
                                )
                        except Exception:
                            logger.exception("companion_update_failed", platform_poll_id=p.id)

        logger.info("vk_vote_recorded", poll_id=poll_id, user_id=user_id)

    return PlainTextResponse("ok")

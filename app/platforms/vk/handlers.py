import structlog
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.core import poll_service
from app.core.aggregator import on_vote
from app.database.engine import async_session
from app.database.models import ConnectedGroup, Platform
from app.platforms.vk.adapter import VKAdapter

logger = structlog.get_logger()
router = APIRouter()


@router.post("/webhook/vk/{group_id}")
async def vk_webhook(group_id: int, request: Request):
    data = await request.json()
    event_type = data.get("type")

    # Verify group_id matches payload
    payload_group_id = data.get("group_id")
    if payload_group_id and int(payload_group_id) != group_id:
        logger.warning("vk_group_id_mismatch", url_id=group_id, payload_id=payload_group_id)
        return PlainTextResponse("ok")

    if event_type == "confirmation":
        async with async_session() as session:
            result = await session.execute(
                select(ConnectedGroup).where(ConnectedGroup.vk_group_id == group_id)
            )
            group = result.scalar_one_or_none()
            if group and group.confirmation_string:
                return PlainTextResponse(group.confirmation_string)
        return PlainTextResponse("")

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

            survey = await session.get(poll_service.Survey, pp.survey_id)
            if not survey:
                return PlainTextResponse("ok")

            await poll_service.record_vote(
                session, pp.survey_id, Platform.vk, user_id, option_id
            )

            result = await on_vote(session, pp.survey_id)
            if result:
                platform_polls = await poll_service.get_platform_polls(session, pp.survey_id)
                for p in platform_polls:
                    if not p.companion_message_id:
                        continue
                    try:
                        if p.platform == Platform.vk:
                            adapter = VKAdapter(group_id)
                            await adapter.update_companion(
                                p.chat_id, p.companion_message_id, result
                            )
                        elif p.platform == Platform.tg:
                            from app.platforms.telegram.adapter import TelegramAdapter

                            await TelegramAdapter().update_companion(
                                p.chat_id, p.companion_message_id, result
                            )
                    except Exception:
                        logger.exception("companion_update_failed", platform_poll_id=p.id)

        logger.info("vk_vote_recorded", poll_id=poll_id, user_id=user_id)

    return PlainTextResponse("ok")

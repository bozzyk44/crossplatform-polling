import structlog
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, PollAnswer

from app.core import poll_service
from app.core.aggregator import on_vote
from app.database.engine import async_session
from app.database.models import Platform
from app.platforms.telegram.adapter import TelegramAdapter

logger = structlog.get_logger()
router = Router()
adapter = TelegramAdapter()


@router.poll_answer()
async def handle_poll_answer(poll_answer: PollAnswer):
    if not poll_answer.option_ids:
        return

    async with async_session() as session:
        pp = await poll_service.find_survey_by_native_poll(
            session, str(poll_answer.poll_id), Platform.tg
        )
        if not pp:
            logger.warning("poll_not_found", poll_id=poll_answer.poll_id)
            return

        option_index = poll_answer.option_ids[0]
        await poll_service.record_vote(
            session,
            pp.survey_id,
            Platform.tg,
            str(poll_answer.user.id),
            option_index,
        )

        result = await on_vote(session, pp.survey_id)
        if result:
            platform_polls = await poll_service.get_platform_polls(session, pp.survey_id)
            for p in platform_polls:
                if p.companion_message_id and p.platform == Platform.tg:
                    try:
                        await adapter.update_companion(p.chat_id, p.companion_message_id, result)
                    except Exception:
                        logger.exception("companion_update_failed", platform_poll_id=p.id)

    logger.info(
        "vote_recorded",
        platform="tg",
        poll_id=poll_answer.poll_id,
        user_id=poll_answer.user.id,
    )


@router.message(Command("newpoll"))
async def handle_new_poll(message: Message):
    if not message.text:
        return

    parts = message.text.split("\n")
    if len(parts) < 3:
        await message.reply(
            "Формат:\n/newpoll\nВопрос\nВариант 1\nВариант 2\n..."
        )
        return

    title = parts[1].strip()
    options = [p.strip() for p in parts[2:] if p.strip()]

    if len(options) < 2:
        await message.reply("Нужно минимум 2 варианта ответа.")
        return

    async with async_session() as session:
        survey = await poll_service.create_survey(session, title, options)
        native_poll_id = await adapter.create_poll(survey, str(message.chat.id))
        await poll_service.register_platform_poll(
            session, survey.id, Platform.tg, native_poll_id, str(message.chat.id)
        )


        result = await poll_service.get_aggregated_results(session, survey.id)
        companion_msg_id = await adapter.send_companion(survey, str(message.chat.id), result)

        # Update platform_poll with companion message id
        pp = await poll_service.find_survey_by_native_poll(session, native_poll_id, Platform.tg)
        if pp:
            pp.companion_message_id = companion_msg_id
            await session.commit()

    logger.info("poll_created", survey_id=str(survey.id), chat_id=message.chat.id)


@router.message(Command("status"))
async def handle_status(message: Message):
    await message.reply("Используйте Admin API для просмотра статуса опросов.")

from app.core.aggregator import format_companion_message
from app.core.schemas import AggregatedResult
from app.database.models import Survey
from app.platforms.base import PlatformAdapter
from app.platforms.telegram.bot import bot


class TelegramAdapter(PlatformAdapter):
    async def create_poll(self, survey: Survey, chat_id: str) -> str:
        msg = await bot.send_poll(
            chat_id=int(chat_id),
            question=survey.title,
            options=[{"text": o} for o in survey.options],
            is_anonymous=False,
        )
        return str(msg.poll.id)

    async def send_companion(self, survey: Survey, chat_id: str, result: AggregatedResult) -> str:
        text = format_companion_message(result)
        msg = await bot.send_message(chat_id=int(chat_id), text=text)
        return str(msg.message_id)

    async def update_companion(
        self, chat_id: str, message_id: str, result: AggregatedResult
    ) -> None:
        text = format_companion_message(result)
        await bot.edit_message_text(
            chat_id=int(chat_id),
            message_id=int(message_id),
            text=text,
        )

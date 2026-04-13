import json

from app.config import settings
from app.core.aggregator import format_companion_message
from app.core.schemas import AggregatedResult
from app.database.models import Survey
from app.platforms.base import PlatformAdapter
from app.platforms.vk.client import vk_client


class VKAdapter(PlatformAdapter):
    async def create_poll(self, survey: Survey, chat_id: str) -> str:
        owner_id = f"-{settings.vk_group_id}"
        poll = await vk_client.call(
            "polls.create",
            owner_id=owner_id,
            question=survey.title,
            is_anonymous="0",
            add_answers=json.dumps([{"text": o} for o in survey.options]),
        )
        poll_id = str(poll["id"])

        # Attach poll to a wall post
        await vk_client.call(
            "wall.post",
            owner_id=owner_id,
            from_group="1",
            attachments=f"poll{owner_id}_{poll_id}",
            message=survey.title,
        )
        return poll_id

    async def send_companion(self, survey: Survey, chat_id: str, result: AggregatedResult) -> str:
        text = format_companion_message(result)
        owner_id = f"-{settings.vk_group_id}"
        resp = await vk_client.call(
            "wall.post",
            owner_id=owner_id,
            from_group="1",
            message=text,
        )
        return str(resp["post_id"])

    async def update_companion(
        self, chat_id: str, message_id: str, result: AggregatedResult
    ) -> None:
        text = format_companion_message(result)
        owner_id = f"-{settings.vk_group_id}"
        await vk_client.call(
            "wall.edit",
            owner_id=owner_id,
            post_id=message_id,
            message=text,
        )

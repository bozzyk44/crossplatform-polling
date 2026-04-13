import json

from app.core.aggregator import format_companion_message
from app.core.schemas import AggregatedResult
from app.database.models import Survey
from app.platforms.base import PlatformAdapter
from app.platforms.vk.client import get_client_for_group


class VKAdapter(PlatformAdapter):
    def __init__(self, group_id: int):
        self._group_id = group_id

    async def create_poll(self, survey: Survey, chat_id: str) -> str:
        client = await get_client_for_group(self._group_id)
        owner_id = f"-{self._group_id}"
        try:
            poll = await client.call(
                "polls.create",
                owner_id=owner_id,
                question=survey.title,
                is_anonymous="0",
                add_answers=json.dumps([{"text": o} for o in survey.options]),
            )
            poll_id = str(poll["id"])

            await client.call(
                "wall.post",
                owner_id=owner_id,
                from_group="1",
                attachments=f"poll{owner_id}_{poll_id}",
                message=survey.title,
            )
            return poll_id
        finally:
            await client.close()

    async def send_companion(
        self, survey: Survey, chat_id: str, result: AggregatedResult
    ) -> str:
        client = await get_client_for_group(self._group_id)
        text = format_companion_message(result)
        owner_id = f"-{self._group_id}"
        try:
            resp = await client.call(
                "wall.post",
                owner_id=owner_id,
                from_group="1",
                message=text,
            )
            return str(resp["post_id"])
        finally:
            await client.close()

    async def update_companion(
        self, chat_id: str, message_id: str, result: AggregatedResult
    ) -> None:
        client = await get_client_for_group(self._group_id)
        text = format_companion_message(result)
        owner_id = f"-{self._group_id}"
        try:
            await client.call(
                "wall.edit",
                owner_id=owner_id,
                post_id=message_id,
                message=text,
            )
        finally:
            await client.close()

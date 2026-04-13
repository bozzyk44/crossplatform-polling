from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = structlog.get_logger()

VK_API_VERSION = "5.199"
VK_API_BASE = "https://api.vk.com/method"


class VKAPIError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"VK API error {code}: {message}")


class VKRateLimitError(VKAPIError):
    pass


class VKClient:
    def __init__(self, token: str | None = None):
        self._client = httpx.AsyncClient(timeout=30.0)
        self._token = token

    @retry(
        retry=retry_if_exception_type(VKRateLimitError),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(5),
    )
    async def call(self, method: str, **params: Any) -> dict:
        if not self._token:
            raise VKAPIError(0, "No access token configured")

        params["access_token"] = self._token
        params["v"] = VK_API_VERSION

        resp = await self._client.post(f"{VK_API_BASE}/{method}", data=params)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            code = data["error"]["error_code"]
            msg = data["error"]["error_msg"]
            if code == 6:  # Too many requests
                logger.warning("vk_rate_limit", method=method)
                raise VKRateLimitError(code, msg)
            raise VKAPIError(code, msg)

        return data["response"]

    async def close(self):
        await self._client.aclose()


async def get_client_for_group(group_id: int) -> VKClient:
    """Get a VKClient with the token for a specific connected group."""
    from sqlalchemy import select

    from app.core.crypto import decrypt_token
    from app.database.engine import async_session
    from app.database.models import ConnectedGroup

    async with async_session() as session:
        result = await session.execute(
            select(ConnectedGroup).where(
                ConnectedGroup.vk_group_id == group_id,
                ConnectedGroup.is_active.is_(True),
            )
        )
        group = result.scalar_one_or_none()
        if not group:
            raise VKAPIError(0, f"Group {group_id} is not connected")

        token = decrypt_token(group.encrypted_token)
        return VKClient(token=token)

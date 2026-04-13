from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings

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
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=30.0)
        self._token = settings.vk_group_token
        self._group_id = settings.vk_group_id

    @retry(
        retry=retry_if_exception_type(VKRateLimitError),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(5),
    )
    async def call(self, method: str, **params: Any) -> dict:
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


vk_client = VKClient()

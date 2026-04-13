from abc import ABC, abstractmethod

from app.core.schemas import AggregatedResult
from app.database.models import Survey


class PlatformAdapter(ABC):
    @abstractmethod
    async def create_poll(self, survey: Survey, chat_id: str) -> str:
        """Create a native poll on the platform. Returns native_poll_id."""

    @abstractmethod
    async def send_companion(self, survey: Survey, chat_id: str, result: AggregatedResult) -> str:
        """Send companion message with aggregated results. Returns message_id."""

    @abstractmethod
    async def update_companion(
        self, chat_id: str, message_id: str, result: AggregatedResult
    ) -> None:
        """Update existing companion message with new results."""

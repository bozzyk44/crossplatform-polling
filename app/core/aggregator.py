import asyncio
import uuid

import structlog

from app.core import poll_service
from app.core.schemas import AggregatedResult
from app.database.engine import async_session

logger = structlog.get_logger()

# Rate-limit buffer: collects survey_ids and flushes companion updates every N seconds
_pending_updates: set[uuid.UUID] = set()
_flush_task: asyncio.Task | None = None
FLUSH_INTERVAL = 2.0  # seconds


def format_companion_message(result: AggregatedResult) -> str:
    header = (
        "\U0001f4e1 Результаты (все платформы):\n"
    )
    lines = [header]
    for opt in result.options:
        pct = (opt.total / result.total_votes * 100) if result.total_votes else 0
        parts = " \u00b7 ".join(f"{p.upper()}: {c}" for p, c in sorted(opt.by_platform.items()))
        platform_info = f"  [{parts}]" if parts else ""
        lines.append(f"\u25b8 {opt.text} \u2014 {opt.total} ({pct:.0f}%){platform_info}")

    lines.append("\u2500" * 23)
    lines.append(f"\u0412\u0441\u0435\u0433\u043e: {result.total_votes}")
    return "\n".join(lines)


async def _get_adapter(platform_name: str):
    """Lazy import to avoid circular deps."""
    if platform_name == "tg":
        from app.platforms.telegram.adapter import TelegramAdapter
        return TelegramAdapter()
    elif platform_name == "vk":
        from app.platforms.vk.adapter import VKAdapter
        return VKAdapter()
    return None


async def _flush_updates():
    """Background task: flush pending companion updates every FLUSH_INTERVAL seconds."""
    while True:
        await asyncio.sleep(FLUSH_INTERVAL)
        if not _pending_updates:
            continue

        survey_ids = list(_pending_updates)
        _pending_updates.clear()

        for survey_id in survey_ids:
            try:
                async with async_session() as session:
                    result = await poll_service.get_aggregated_results(session, survey_id)
                    if not result:
                        continue

                    platform_polls = await poll_service.get_platform_polls(session, survey_id)
                    for pp in platform_polls:
                        if not pp.companion_message_id:
                            continue
                        adapter = await _get_adapter(pp.platform.value)
                        if adapter:
                            try:
                                await adapter.update_companion(
                                    pp.chat_id, pp.companion_message_id, result
                                )
                            except Exception:
                                logger.exception(
                                    "companion_update_failed",
                                    platform=pp.platform.value,
                                    poll_id=pp.id,
                                )
            except Exception:
                logger.exception("flush_update_failed", survey_id=str(survey_id))


def start_flush_task():
    """Start the background flush task. Call once at app startup."""
    global _flush_task
    if _flush_task is None or _flush_task.done():
        _flush_task = asyncio.create_task(_flush_updates())


def stop_flush_task():
    """Stop the background flush task. Call at app shutdown."""
    global _flush_task
    if _flush_task and not _flush_task.done():
        _flush_task.cancel()


async def on_vote(session, survey_id: uuid.UUID) -> AggregatedResult | None:
    """Called after each vote. Queues companion update and returns results."""
    _pending_updates.add(survey_id)
    return await poll_service.get_aggregated_results(session, survey_id)

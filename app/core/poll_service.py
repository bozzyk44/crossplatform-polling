import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import AggregatedResult, OptionResult
from app.database.models import Platform, PlatformPoll, Survey, Vote


async def create_survey(session: AsyncSession, title: str, options: list[str]) -> Survey:
    survey = Survey(title=title, options=options)
    session.add(survey)
    await session.commit()
    await session.refresh(survey)
    return survey


async def close_survey(session: AsyncSession, survey_id: uuid.UUID) -> Survey | None:
    survey = await session.get(Survey, survey_id)
    if not survey or not survey.is_active:
        return None
    survey.is_active = False
    survey.closed_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(survey)
    return survey


async def record_vote(
    session: AsyncSession,
    survey_id: uuid.UUID,
    platform: Platform,
    platform_user_id: str,
    option_index: int,
) -> None:
    now = datetime.now(UTC)
    existing = await session.execute(
        select(Vote).where(
            Vote.survey_id == survey_id,
            Vote.platform == platform,
            Vote.platform_user_id == platform_user_id,
        )
    )
    vote = existing.scalar_one_or_none()
    if vote:
        vote.option_index = option_index
        vote.voted_at = now
    else:
        session.add(
            Vote(
                survey_id=survey_id,
                platform=platform,
                platform_user_id=platform_user_id,
                option_index=option_index,
                voted_at=now,
            )
        )
    await session.commit()


async def get_aggregated_results(
    session: AsyncSession, survey_id: uuid.UUID
) -> AggregatedResult | None:
    survey = await session.get(Survey, survey_id)
    if not survey:
        return None

    stmt = (
        select(Vote.option_index, Vote.platform, func.count())
        .where(Vote.survey_id == survey_id)
        .group_by(Vote.option_index, Vote.platform)
    )
    rows = (await session.execute(stmt)).all()

    options_map: dict[int, dict[str, int]] = {}
    for option_index, platform, count in rows:
        options_map.setdefault(option_index, {})[platform.value] = count

    option_results = []
    total_votes = 0
    for i, text in enumerate(survey.options):
        by_platform = options_map.get(i, {})
        total = sum(by_platform.values())
        total_votes += total
        option_results.append(
            OptionResult(index=i, text=text, total=total, by_platform=by_platform)
        )

    return AggregatedResult(
        survey_id=survey.id,
        title=survey.title,
        options=option_results,
        total_votes=total_votes,
    )


async def register_platform_poll(
    session: AsyncSession,
    survey_id: uuid.UUID,
    platform: Platform,
    native_poll_id: str,
    chat_id: str,
    companion_message_id: str | None = None,
) -> PlatformPoll:
    pp = PlatformPoll(
        survey_id=survey_id,
        platform=platform,
        native_poll_id=native_poll_id,
        chat_id=chat_id,
        companion_message_id=companion_message_id,
    )
    session.add(pp)
    await session.commit()
    await session.refresh(pp)
    return pp


async def find_survey_by_native_poll(
    session: AsyncSession, native_poll_id: str, platform: Platform
) -> PlatformPoll | None:
    stmt = select(PlatformPoll).where(
        PlatformPoll.native_poll_id == native_poll_id,
        PlatformPoll.platform == platform,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_platform_polls(
    session: AsyncSession, survey_id: uuid.UUID
) -> list[PlatformPoll]:
    stmt = select(PlatformPoll).where(PlatformPoll.survey_id == survey_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

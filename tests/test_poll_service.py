import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.poll_service import (
    close_survey,
    create_survey,
    find_survey_by_native_poll,
    get_aggregated_results,
    get_platform_polls,
    record_vote,
    register_platform_poll,
)
from app.database.models import Platform


async def test_create_survey(session: AsyncSession):
    survey = await create_survey(session, "Лучший язык?", ["Python", "Go", "Rust"])
    assert survey.id is not None
    assert survey.title == "Лучший язык?"
    assert survey.options == ["Python", "Go", "Rust"]
    assert survey.is_active is True


async def test_close_survey(session: AsyncSession):
    survey = await create_survey(session, "Test?", ["A", "B"])
    closed = await close_survey(session, survey.id)
    assert closed is not None
    assert closed.is_active is False
    assert closed.closed_at is not None

    # closing again returns None
    assert await close_survey(session, survey.id) is None


async def test_close_nonexistent(session: AsyncSession):
    assert await close_survey(session, uuid.uuid4()) is None


async def test_record_vote_and_aggregate(session: AsyncSession):
    survey = await create_survey(session, "Test?", ["A", "B", "C"])

    await record_vote(session, survey.id, Platform.tg, "user1", 0)
    await record_vote(session, survey.id, Platform.tg, "user2", 0)
    await record_vote(session, survey.id, Platform.vk, "user3", 1)
    await record_vote(session, survey.id, Platform.vk, "user4", 2)

    result = await get_aggregated_results(session, survey.id)
    assert result is not None
    assert result.total_votes == 4
    assert result.options[0].total == 2
    assert result.options[0].by_platform == {"tg": 2}
    assert result.options[1].total == 1
    assert result.options[1].by_platform == {"vk": 1}
    assert result.options[2].total == 1


async def test_vote_upsert(session: AsyncSession):
    """Re-voting should update the option, not create a duplicate."""
    survey = await create_survey(session, "Test?", ["A", "B"])

    await record_vote(session, survey.id, Platform.tg, "user1", 0)
    await record_vote(session, survey.id, Platform.tg, "user1", 1)  # change vote

    result = await get_aggregated_results(session, survey.id)
    assert result.total_votes == 1
    assert result.options[0].total == 0
    assert result.options[1].total == 1


async def test_aggregation_empty(session: AsyncSession):
    survey = await create_survey(session, "Empty?", ["A", "B"])
    result = await get_aggregated_results(session, survey.id)
    assert result is not None
    assert result.total_votes == 0


async def test_aggregation_nonexistent(session: AsyncSession):
    assert await get_aggregated_results(session, uuid.uuid4()) is None


async def test_register_and_find_platform_poll(session: AsyncSession):
    survey = await create_survey(session, "Test?", ["A", "B"])
    pp = await register_platform_poll(session, survey.id, Platform.tg, "poll_123", "chat_456")
    assert pp.id is not None
    assert pp.native_poll_id == "poll_123"

    found = await find_survey_by_native_poll(session, "poll_123", Platform.tg)
    assert found is not None
    assert found.survey_id == survey.id

    # not found on other platform
    assert await find_survey_by_native_poll(session, "poll_123", Platform.vk) is None


async def test_get_platform_polls(session: AsyncSession):
    survey = await create_survey(session, "Test?", ["A", "B"])
    await register_platform_poll(session, survey.id, Platform.tg, "p1", "c1")
    await register_platform_poll(session, survey.id, Platform.vk, "p2", "c2")

    polls = await get_platform_polls(session, survey.id)
    assert len(polls) == 2

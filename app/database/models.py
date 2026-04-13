import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Platform(enum.StrEnum):
    tg = "tg"
    vk = "vk"


class Survey(Base):
    __tablename__ = "surveys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    options: Mapped[list] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    platform_polls: Mapped[list["PlatformPoll"]] = relationship(back_populates="survey")
    votes: Mapped[list["Vote"]] = relationship(back_populates="survey")


class PlatformPoll(Base):
    __tablename__ = "platform_polls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    survey_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("surveys.id"), nullable=False
    )
    platform: Mapped[Platform] = mapped_column(Enum(Platform), nullable=False)
    native_poll_id: Mapped[str] = mapped_column(String(255), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(255), nullable=False)
    companion_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    survey: Mapped["Survey"] = relationship(back_populates="platform_polls")


class Vote(Base):
    __tablename__ = "votes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    survey_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("surveys.id"), nullable=False
    )
    platform: Mapped[Platform] = mapped_column(Enum(Platform), nullable=False)
    platform_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    option_index: Mapped[int] = mapped_column(Integer, nullable=False)
    voted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    survey: Mapped["Survey"] = relationship(back_populates="votes")

    __table_args__ = (
        UniqueConstraint("survey_id", "platform", "platform_user_id", name="uq_vote_per_user"),
    )

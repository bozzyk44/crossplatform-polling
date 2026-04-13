import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateSurvey(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    options: list[str] = Field(min_length=2, max_length=10)


class SurveyOut(BaseModel):
    id: uuid.UUID
    title: str
    options: list[str]
    is_active: bool
    created_at: datetime
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class OptionResult(BaseModel):
    index: int
    text: str
    total: int
    by_platform: dict[str, int]


class AggregatedResult(BaseModel):
    survey_id: uuid.UUID
    title: str
    options: list[OptionResult]
    total_votes: int

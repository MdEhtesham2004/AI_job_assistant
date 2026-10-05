import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import (
    InterviewDifficulty,
    InterviewRound,
    InterviewSpeaker,
    InterviewStatus,
    InterviewVerdict,
)


class InterviewCreate(BaseModel):
    round: InterviewRound = InterviewRound.MIXED
    difficulty: InterviewDifficulty = InterviewDifficulty.MID
    retry_of_id: uuid.UUID | None = None  # "Retry weak questions" of an earlier interview


class InterviewCreated(BaseModel):
    interview_id: uuid.UUID
    task_id: uuid.UUID


class InterviewJob(BaseModel):
    id: uuid.UUID
    title: str
    company: str


class InterviewSummary(BaseModel):
    id: uuid.UUID
    status: InterviewStatus
    round: InterviewRound
    difficulty: InterviewDifficulty
    minutes: int
    job: InterviewJob
    application_id: uuid.UUID | None
    retry_of_id: uuid.UUID | None
    verdict: InterviewVerdict | None
    overall_score: int | None
    started_at: datetime | None
    seconds_used: int
    created_at: datetime


class TurnRead(BaseModel):
    model_config = {"from_attributes": True}

    seq: int
    speaker: InterviewSpeaker
    text: str
    original_text: str | None
    offset_ms: int
    edited: bool


class PlanQuestionRead(BaseModel):
    id: str
    kind: str
    topic: str
    question: str


class ReportRead(BaseModel):
    verdict: InterviewVerdict
    overall_score: int
    report: dict[str, Any]
    pdf_url: str | None


class InterviewDetail(InterviewSummary):
    error: str | None
    deadline_at: datetime | None
    ended_at: datetime | None
    plan_task_id: uuid.UUID | None
    report_task_id: uuid.UUID | None
    thin_description: bool
    # The questions are shown only after the call, so the interview stays a surprise.
    questions: list[PlanQuestionRead]
    turns: list[TurnRead]
    report: ReportRead | None
    estimated_cost_usd: Decimal


class SessionRead(BaseModel):
    """Short-lived OpenAI Realtime token: the browser connects to OpenAI with it."""

    client_secret: str
    expires_at: datetime
    deadline_at: datetime
    seconds_left: int
    model: str
    connect_url: str
    provider: str  # openai (WebRTC) | gemini (WebSocket)
    wrap_up: str
    reconnect: bool


class TurnWrite(BaseModel):
    seq: int = Field(ge=0, le=10_000)
    speaker: InterviewSpeaker
    text: str = Field(max_length=8000)
    offset_ms: int = Field(default=0, ge=0, le=7_200_000)


class TurnsWrite(BaseModel):
    turns: list[TurnWrite] = Field(min_length=1, max_length=50)


class TurnEdit(BaseModel):
    text: str = Field(min_length=1, max_length=4000)

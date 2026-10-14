import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class DigestJob(BaseModel):
    job_id: uuid.UUID
    title: str
    company: str
    location: str | None
    score: int
    decision: str


class DigestRead(BaseModel):
    digest_date: date
    created_at: datetime
    jobs: list[DigestJob]
    new_jobs: int
    scored: int
    emailed: bool
    email_error: str | None
    is_today: bool


class DigestState(BaseModel):
    digest: DigestRead | None
    running_task_id: uuid.UUID | None


class SkillGapRead(BaseModel):
    skill: str
    jobs: int
    examples: list[str]


class SkillPlanRead(BaseModel):
    id: uuid.UUID
    created_at: datetime
    gaps: list[dict[str, Any]]
    plan: dict[str, Any]


class SkillsRead(BaseModel):
    jobs_analyzed: int
    gaps: list[SkillGapRead]
    strengths: list[SkillGapRead]
    plan: SkillPlanRead | None
    running_task_id: uuid.UUID | None


class AnswerRead(BaseModel):
    key: str
    question: str
    answer: str
    edited: bool
    custom: bool
    check: list[str] = []  # numbers not found in the resume/profile: check them


class AnswersRead(BaseModel):
    job_id: uuid.UUID
    answers: list[AnswerRead]
    updated_at: datetime | None
    running_task_id: uuid.UUID | None


class AnswersRequest(BaseModel):
    custom_questions: list[str] = Field(default_factory=list, max_length=3)


class AnswerEdit(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)


class PrepRead(BaseModel):
    job_id: uuid.UUID
    pack: dict[str, Any] | None
    updated_at: datetime | None
    pdf_url: str | None
    running_task_id: uuid.UUID | None

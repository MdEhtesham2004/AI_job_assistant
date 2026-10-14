import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.enums import ParseStatus, ResumeKind, TaskStatus


class ResumeVersionSummary(BaseModel):
    id: uuid.UUID
    version_no: int
    kind: ResumeKind
    file_name: str
    mime_type: str
    file_size: int
    parse_status: ParseStatus
    parse_error: str | None
    derived_from_id: uuid.UUID | None
    is_active: bool
    ats_score: int | None
    created_at: datetime


class ResumeOverview(BaseModel):
    resume_id: uuid.UUID | None
    title: str | None
    active_version_id: uuid.UUID | None
    versions: list[ResumeVersionSummary]


class AtsReportRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    ats_score: int
    section_scores: dict[str, int]
    strengths: list[str]
    missing_skills: list[str]
    top_roles: list[str]
    suggestions: list[str]
    linkedin_summary: dict[str, str] | None
    model: str
    prompt_version: str
    created_at: datetime
    updated_at: datetime


class ActiveTask(BaseModel):
    id: uuid.UUID
    type: str
    status: TaskStatus
    progress: int


class ResumeVersionDetail(ResumeVersionSummary):
    parsed: dict[str, Any] | None
    download_url: str
    ats_report: AtsReportRead | None
    active_tasks: list[ActiveTask]


class ResumeUploaded(BaseModel):
    version: ResumeVersionSummary
    task_id: uuid.UUID

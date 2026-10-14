import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import (
    ApplicationChannel,
    ApplicationStatus,
    ContactApproval,
    ContactVerification,
    DocumentStatus,
    ResumeKind,
    StatusChangeSource,
)


class ApplicationCreate(BaseModel):
    channel: ApplicationChannel = ApplicationChannel.PORTAL
    resume_version_id: uuid.UUID | None = None  # default: the job's tailored resume, else active
    cover_letter_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None  # email channel: who receives it
    next_action: str | None = Field(default=None, max_length=500)


class ApplicationUpdate(BaseModel):
    channel: ApplicationChannel | None = None
    resume_version_id: uuid.UUID | None = None
    cover_letter_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    next_action: str | None = Field(default=None, max_length=500)


class StatusChange(BaseModel):
    to_status: ApplicationStatus
    note: str | None = Field(default=None, max_length=1000)


class MarkApplied(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class ApplicationJob(BaseModel):
    id: uuid.UUID
    title: str
    company: str
    location: str | None
    apply_url: str | None


class ApplicationSummary(BaseModel):
    id: uuid.UUID
    job: ApplicationJob
    channel: ApplicationChannel
    status: ApplicationStatus
    next_action: str | None
    applied_at: datetime | None
    last_status_at: datetime
    created_at: datetime
    match_score: int | None


class ResumeRef(BaseModel):
    id: uuid.UUID
    version_no: int
    kind: ResumeKind
    file_name: str
    download_url: str


class CoverLetterRef(BaseModel):
    id: uuid.UUID
    status: DocumentStatus
    download_url: str | None


class HistoryEntry(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    source: StatusChangeSource
    note: str | None
    created_at: datetime


class ContactRef(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    approval: ContactApproval
    verification: ContactVerification


class ApplicationDetail(ApplicationSummary):
    resume: ResumeRef | None
    cover_letter: CoverLetterRef | None
    contact: ContactRef | None
    history: list[HistoryEntry]
    allowed_next: list[ApplicationStatus]  # what the user may choose now


class ApplicationCounts(BaseModel):
    counts: dict[str, int]
    total: int

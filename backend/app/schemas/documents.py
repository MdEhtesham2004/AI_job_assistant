import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import DocumentStatus, ResumeKind
from app.schemas.jobs import ActiveJobTask


class VersionRef(BaseModel):
    id: uuid.UUID
    version_no: int
    kind: ResumeKind
    file_name: str


class SourceResume(VersionRef):
    parsed: dict[str, Any] | None


class TailoredRead(VersionRef):
    parsed: dict[str, Any]
    download_url: str
    created_at: datetime
    updated_at: datetime
    warnings: list[str]  # checker findings after user edits (empty for generated ones)
    emphasized_skills: list[str]  # skills of the tailored resume that the job mentions


class CoverLetterRead(BaseModel):
    id: uuid.UUID
    resume_version_id: uuid.UUID
    content_md: str
    status: DocumentStatus
    download_url: str | None
    word_count: int
    warnings: list[str]
    created_at: datetime
    updated_at: datetime


class JobDocumentsRead(BaseModel):
    job_id: uuid.UUID
    job_title: str
    company: str
    source: VersionRef | None  # what new documents will be based on
    tailored: TailoredRead | None
    tailored_from: SourceResume | None  # the master it was made from (side-by-side)
    cover_letter: CoverLetterRead | None
    active_tasks: list[ActiveJobTask]


class CoverLetterRequest(BaseModel):
    contact_name: str | None = Field(default=None, max_length=100)


class CoverLetterUpdate(BaseModel):
    content_md: str | None = Field(default=None, min_length=50, max_length=10_000)
    status: DocumentStatus | None = None

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import (
    ApplicationStatus,
    ContactApproval,
    ContactSource,
    ContactVerification,
    DncSource,
    EmailStatus,
    EmailType,
    ReplyCategory,
)

# ---------- Gmail ----------


class GmailStatusRead(BaseModel):
    configured: bool
    connected: bool
    status: str | None
    account_email: str | None
    can_send: bool
    can_read: bool
    connected_at: datetime | None


class GmailConnectRead(BaseModel):
    auth_url: str


# ---------- contacts ----------


class ContactJob(BaseModel):
    id: uuid.UUID
    title: str
    company: str


class ContactRead(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    role_title: str | None
    company: str | None
    source: ContactSource
    source_url: str | None
    source_excerpt: str | None
    verification: ContactVerification
    verified_at: datetime | None
    approval: ContactApproval
    approved_at: datetime | None
    blocked: bool
    job: ContactJob | None
    created_at: datetime


class ContactCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    name: str | None = Field(default=None, max_length=200)
    role_title: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    job_id: uuid.UUID | None = None
    source_url: str | None = Field(default=None, max_length=1000)


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    role_title: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    approval: ContactApproval | None = None


class ContactCounts(BaseModel):
    counts: dict[str, int]
    total: int


class DiscoverRequest(BaseModel):
    keyword: str = Field(min_length=2, max_length=100)
    max_posts: int = Field(default=50, ge=5, le=200)
    posted_limit: Literal["24h", "week", "month"] = "week"


class DoNotContactCreate(BaseModel):
    email: str | None = Field(default=None, max_length=254)
    domain: str | None = Field(default=None, max_length=253)
    reason: str | None = Field(default=None, max_length=500)


class DoNotContactRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: str | None
    domain: str | None
    reason: str | None
    source: DncSource
    created_at: datetime


# ---------- emails ----------


class DraftRequest(BaseModel):
    contact_id: uuid.UUID | None = None  # default: the application's contact


class AttachmentRead(BaseModel):
    id: uuid.UUID
    file_name: str
    mime_type: str
    file_size: int
    download_url: str


class EmailContact(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    approval: ContactApproval
    verification: ContactVerification
    # Evidence, so the approval queue can approve contact + email in one look.
    source: ContactSource
    source_url: str | None
    source_excerpt: str | None
    role_title: str | None


class EmailApplication(BaseModel):
    id: uuid.UUID
    status: ApplicationStatus
    job_id: uuid.UUID
    job_title: str
    company: str
    match_score: int | None = None


class EmailRead(BaseModel):
    id: uuid.UUID
    email_type: EmailType
    status: EmailStatus
    from_address: str
    to_address: str
    subject: str
    body_text: str
    approved_at: datetime | None
    scheduled_for: datetime | None
    sent_at: datetime | None
    error: str | None
    gmail_thread_id: str | None
    contact: EmailContact | None
    application: EmailApplication
    attachments: list[AttachmentRead]
    warnings: list[str]
    updated_at: datetime


class EmailUpdate(BaseModel):
    subject: str | None = Field(default=None, max_length=200)
    body_text: str | None = Field(default=None, max_length=10_000)
    contact_id: uuid.UUID | None = None


class ApproveBatch(BaseModel):
    email_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    approve_contacts: bool = False  # approval queue: approve pending contacts too


# ---------- replies & automation (Phase 13) ----------


class ReplyClassificationRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    category: ReplyCategory
    confidence: float
    summary: str
    suggested_action: str | None
    applied_transition: bool
    user_confirmed: bool | None


class ReplyRead(BaseModel):
    id: uuid.UUID
    status: EmailStatus  # received | bounced
    from_address: str
    subject: str
    body_text: str
    received_at: datetime | None
    classification: ReplyClassificationRead | None


class ReplyConfirm(BaseModel):
    accept: bool


class AutomationRun(BaseModel):
    task_id: uuid.UUID
    status: str
    progress: int
    result: dict[str, object] | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class AutomationStatus(BaseModel):
    keywords: list[str]
    ready: bool  # resume parsed + Gmail connected
    not_ready_reason: str | None
    saved_ready: int  # saved jobs with an approved contact and no application
    fetch_allowed: bool  # admin switch (Settings › Platform)
    fetch_problem: str | None  # e.g. no keywords
    max_jobs: int
    last_run: AutomationRun | None


class AutomationRunRequest(BaseModel):
    mode: Literal["saved", "fetch"] = "saved"


class PlatformSettings(BaseModel):
    automation_fetch_enabled: bool


class ApproveBatchRead(BaseModel):
    approved: list[uuid.UUID]
    errors: dict[str, str]


class OutboxSummaryRead(BaseModel):
    counts: dict[str, int]
    sent_today: int
    daily_cap: int
    interval_seconds: int
    next_slot: datetime | None
    gmail_connected: bool
    gmail_email: str | None

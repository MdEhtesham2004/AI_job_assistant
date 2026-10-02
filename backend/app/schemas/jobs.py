import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.jobs import Experience
from app.models.enums import (
    DescriptionQuality,
    JobSource,
    SearchRunStatus,
    TaskStatus,
    UserJobState,
)

DatePosted = Literal["all", "today", "3days", "week", "month"]
MAX_PAGES_PER_REQUEST = 3
# "Load more" stops here: 10 pages ≈ 100 jobs for one search.
MAX_PAGES_PER_SEARCH = 10


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


class JobSearchRequest(BaseModel):
    keywords: str = Field(min_length=2, max_length=200)
    location: str | None = Field(default=None, max_length=100)
    experience: Experience | None = None
    remote_only: bool = False
    country: str = Field(default="in", pattern=r"^[a-zA-Z]{2}$")
    date_posted: DatePosted = "week"
    # JSearch pages of ~10 jobs fetched at once (more results, more quota).
    num_pages: int = Field(default=1, ge=1, le=MAX_PAGES_PER_REQUEST)

    _clean_text = field_validator("keywords", "location")(_clean)

    @field_validator("country")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.lower()


class JobSearchStarted(BaseModel):
    task_id: uuid.UUID
    run_id: uuid.UUID


class JobSummary(BaseModel):
    id: uuid.UUID
    title: str
    company: str
    location: str | None
    is_remote: bool
    employment_type: str | None
    posted_at: datetime | None
    apply_url: str | None
    source: JobSource
    description_quality: DescriptionQuality
    state: UserJobState | None
    first_found_at: datetime | None


class ActiveJobTask(BaseModel):
    id: uuid.UUID
    type: str
    status: TaskStatus
    progress: int


class JobDetail(JobSummary):
    description: str | None  # the user's pasted text if any, else the job's own
    has_own_description: bool
    notes: str | None
    company_domain: str | None
    salary_min: Decimal | None
    salary_max: Decimal | None
    salary_currency: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    active_tasks: list[ActiveJobTask]


class JobUpdate(BaseModel):
    state: Literal["new", "saved", "skipped", "archived"] | None = None
    notes: str | None = Field(default=None, max_length=5000)
    # Pasted job description; "" removes it.
    description: str | None = Field(default=None, max_length=50_000)


class JobCounts(BaseModel):
    new: int
    saved: int
    analyzed: int
    skipped: int
    archived: int


class SearchRunRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    saved_search_id: uuid.UUID | None
    task_id: uuid.UUID | None
    status: SearchRunStatus
    query: dict[str, Any]
    results_count: int
    new_jobs_count: int
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    pages_loaded: int
    can_load_more: bool


class SearchResultJob(JobSummary):
    # True when this search added the job to your list; False = it was already there.
    is_new: bool


class SearchRunDetail(SearchRunRead):
    jobs: list[SearchResultJob]


class SuggestedRoles(BaseModel):
    roles: list[str]
    location: str | None
    hint: str | None


class SavedSearchBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    keywords: str = Field(min_length=2, max_length=200)
    location: str | None = Field(default=None, max_length=100)
    experience: Experience | None = None
    remote_only: bool = False
    country: str = Field(default="in", pattern=r"^[a-zA-Z]{2}$")
    schedule_cron: str = Field(default="0 8 * * *", max_length=100)
    is_active: bool = True

    _clean_text = field_validator("name", "keywords", "location")(_clean)


class SavedSearchCreate(SavedSearchBase):
    pass


class SavedSearchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    keywords: str | None = Field(default=None, min_length=2, max_length=200)
    location: str | None = Field(default=None, max_length=100)
    experience: Experience | None = None
    remote_only: bool | None = None
    country: str | None = Field(default=None, pattern=r"^[a-zA-Z]{2}$")
    schedule_cron: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class SavedSearchRead(BaseModel):
    id: uuid.UUID
    name: str
    keywords: str
    location: str | None
    experience: Experience | None
    remote_only: bool
    country: str
    schedule_cron: str
    is_active: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime

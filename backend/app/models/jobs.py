import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, text_enum
from app.models.enums import (
    DescriptionQuality,
    JobSource,
    JobStatus,
    JobVisibility,
    SearchRunStatus,
    UserJobState,
)


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Phase 0 §5.3 — shared job catalog: a job is stored once, whoever found it."""

    __tablename__ = "jobs"

    source: Mapped[JobSource] = mapped_column(text_enum(JobSource, "job_source"), nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[JobVisibility] = mapped_column(
        text_enum(JobVisibility, "job_visibility"),
        nullable=False,
        default=JobVisibility.PUBLIC,
        server_default=JobVisibility.PUBLIC.value,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    company_domain: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(2))
    is_remote: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    employment_type: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    description_quality: Mapped[DescriptionQuality] = mapped_column(
        text_enum(DescriptionQuality, "description_quality"), nullable=False
    )
    apply_url: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    dedupe_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        text_enum(JobStatus, "job_status"),
        nullable=False,
        default=JobStatus.ACTIVE,
        server_default=JobStatus.ACTIVE.value,
    )
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("source", "external_id"),
        CheckConstraint(
            "(visibility = 'private') = (created_by_user_id IS NOT NULL)", name="private_has_owner"
        ),
        Index("ix_jobs_dedupe_hash", "dedupe_hash"),
        Index("ix_jobs_posted_at", "posted_at"),
    )


class UserJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One user's view of a shared job: state, notes, pasted description."""

    __tablename__ = "user_jobs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[UserJobState] = mapped_column(
        text_enum(UserJobState, "user_job_state"),
        nullable=False,
        default=UserJobState.NEW,
        server_default=UserJobState.NEW.value,
    )
    description_override: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    first_found_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "job_id"),
        Index("ix_user_jobs_user_id_state", "user_id", "state"),
    )


class SavedSearch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "saved_searches"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text)
    experience: Mapped[str | None] = mapped_column(Text)
    remote_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    country: Mapped[str] = mapped_column(
        String(2), nullable=False, default="in", server_default="in"
    )
    schedule_cron: Mapped[str] = mapped_column(
        Text, nullable=False, default="0 8 * * *", server_default="0 8 * * *"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_saved_searches_user_id", "user_id"),)


class JobSearchRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "job_search_runs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    saved_search_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("saved_searches.id", ondelete="SET NULL")
    )
    source: Mapped[JobSource] = mapped_column(text_enum(JobSource, "job_source"), nullable=False)
    query: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[SearchRunStatus] = mapped_column(
        text_enum(SearchRunStatus, "search_run_status"),
        nullable=False,
        default=SearchRunStatus.QUEUED,
        server_default=SearchRunStatus.QUEUED.value,
    )
    results_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    new_jobs_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL")
    )
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_job_search_runs_user_id_created_at", "user_id", "created_at"),)


class JobSearchResult(CreatedAtMixin, Base):
    """Which jobs one search run returned, in JSearch's order."""

    __tablename__ = "job_search_results"

    search_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_search_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # True when this run added the job to the user's list (False: it was already there).
    is_new: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

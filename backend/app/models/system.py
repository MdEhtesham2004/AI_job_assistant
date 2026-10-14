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
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, text_enum
from app.models.enums import ActorType, NotificationSeverity, TaskStatus


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Phase 0 §5.8 — background task tracking (used from Phase 6)."""

    __tablename__ = "tasks"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    celery_id: Mapped[str | None] = mapped_column(Text, unique=True)
    status: Mapped[TaskStatus] = mapped_column(
        text_enum(TaskStatus, "task_status"),
        nullable=False,
        default=TaskStatus.QUEUED,
        server_default=TaskStatus.QUEUED.value,
    )
    progress: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("progress BETWEEN 0 AND 100", name="progress_range"),
        Index("ix_tasks_user_id_status_created_at", "user_id", "status", text("created_at DESC")),
    )


class AuditLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Phase 0 §5.8 — append-only audit trail; survives user deletion (user_id → NULL)."""

    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_type: Mapped[ActorType] = mapped_column(
        text_enum(ActorType, "actor_type"), nullable=False
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)

    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_audit_logs_created_at", text("created_at DESC")),
    )


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Phase 0 section 5.8 - in-app notifications (bell + list)."""

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[NotificationSeverity] = mapped_column(
        text_enum(NotificationSeverity, "notification_severity"),
        nullable=False,
        default=NotificationSeverity.INFO,
        server_default=NotificationSeverity.INFO.value,
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_notifications_user_id_read_at", "user_id", "read_at"),
        Index("ix_notifications_user_id_created_at", "user_id", text("created_at DESC")),
    )


class AiCall(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Phase 0 section 5.8 - one row per LLM call (cost, latency, cache hits, budget)."""

    __tablename__ = "ai_calls"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=Decimal(0))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (Index("ix_ai_calls_user_id_created_at", "user_id", "created_at"),)


class AppSettings(TimestampMixin, Base):
    """Platform-wide switches only an admin may change (one row, id = 1)."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    # Phase 13: "Fetch new jobs & automate" calls Apify (paid) — off until an admin allows it.
    automation_fetch_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # Cost control (Phase 14): paid calls per user. 0 = unlimited. Cache hits never count.
    jsearch_requests_per_month: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default=text("60")
    )
    # Apify bills per post returned: the monthly allowance is in posts.
    apify_posts_per_month: Mapped[int] = mapped_column(
        Integer, nullable=False, default=300, server_default=text("300")
    )
    apify_runs_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default=text("3")
    )
    # Contacts › Find LinkedIn posts (and automation): most posts one fetch may return.
    apify_max_posts_per_fetch: Mapped[int] = mapped_column(
        Integer, nullable=False, default=25, server_default=text("25")
    )
    # Find jobs: most JSearch pages (10 jobs = 1 billed request each) one search may fetch.
    jsearch_max_pages: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    jsearch_allow_load_more: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    # AI mock interview (Phase 15): started interviews per user per month; call length.
    interviews_per_month: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default=text("10")
    )
    interview_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=6, server_default=text("6")
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("interviews_per_month >= 0", name="interviews_non_negative"),
        CheckConstraint("interview_minutes BETWEEN 2 AND 30", name="interview_minutes_range"),
        CheckConstraint(
            "jsearch_requests_per_month >= 0 AND apify_posts_per_month >= 0 "
            "AND apify_runs_per_day >= 0",
            name="quotas_non_negative",
        ),
        CheckConstraint("jsearch_max_pages BETWEEN 1 AND 3", name="jsearch_max_pages_range"),
        CheckConstraint(
            "apify_max_posts_per_fetch BETWEEN 5 AND 200", name="apify_max_posts_range"
        ),
    )


class ProviderCall(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One call to a paid data API (JSearch, Apify) — or a cache hit that avoided one.

    Feeds the per-user quotas and Admin › Analytics. `units` is what the provider bills:
    JSearch requests (1 per page), Apify posts returned.
    """

    __tablename__ = "provider_calls"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)  # jsearch | apify
    cache_key: Mapped[str] = mapped_column(Text, nullable=False)
    query: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    cached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    results: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal(0))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quota_remaining: Mapped[int | None] = mapped_column(Integer)  # JSearch plan, from headers
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_provider_calls_user_id_provider_created_at", "user_id", "provider", "created_at"),
        Index("ix_provider_calls_provider_created_at", "provider", "created_at"),
    )

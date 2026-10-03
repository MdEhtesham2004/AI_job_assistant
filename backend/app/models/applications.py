import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, text_enum
from app.models.enums import ApplicationChannel, ApplicationStatus, StatusChangeSource


class Application(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Phase 0 §5.6 — one application per job per user. contact_id follows in Phase 12."""

    __tablename__ = "applications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[ApplicationChannel] = mapped_column(
        text_enum(ApplicationChannel, "application_channel"),
        nullable=False,
        default=ApplicationChannel.EMAIL,
        server_default=ApplicationChannel.EMAIL.value,
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        text_enum(ApplicationStatus, "application_status"),
        nullable=False,
        default=ApplicationStatus.READY_TO_APPLY,
        server_default=ApplicationStatus.READY_TO_APPLY.value,
    )
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="SET NULL")
    )
    cover_letter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cover_letters.id", ondelete="SET NULL")
    )
    next_action: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "job_id"),
        Index("ix_applications_user_id_status", "user_id", "status"),
    )


class ApplicationStatusHistory(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only: rows are never updated or deleted by the application."""

    __tablename__ = "application_status_history"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    # Two columns of the same enum need two CHECK names.
    from_status: Mapped[ApplicationStatus | None] = mapped_column(
        text_enum(ApplicationStatus, "from_status")
    )
    to_status: Mapped[ApplicationStatus] = mapped_column(
        text_enum(ApplicationStatus, "to_status"), nullable=False
    )
    source: Mapped[StatusChangeSource] = mapped_column(
        text_enum(StatusChangeSource, "status_change_source"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        Index(
            "ix_application_status_history_application_id_created_at",
            "application_id",
            "created_at",
        ),
    )

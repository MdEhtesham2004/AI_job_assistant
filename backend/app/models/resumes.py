import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, text_enum
from app.models.enums import ParseStatus, ResumeKind


class Resume(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Phase 0 §5.2 — one master resume per user (versions hold the files)."""

    __tablename__ = "resumes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(
        Text, nullable=False, default="Master resume", server_default="Master resume"
    )
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_versions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    __table_args__ = (Index("ix_resumes_user_id", "user_id"),)


class ResumeVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Phase 0 §5.2 — never deleted while referenced; a new upload is a new version."""

    __tablename__ = "resume_versions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[ResumeKind] = mapped_column(text_enum(ResumeKind, "resume_kind"), nullable=False)
    derived_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="SET NULL"), nullable=True
    )
    # FK to jobs is added in Phase 8 together with the jobs table.
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    file_key: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    text_content: Mapped[str | None] = mapped_column(Text)
    parsed: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    parse_status: Mapped[ParseStatus] = mapped_column(
        text_enum(ParseStatus, "parse_status"),
        nullable=False,
        default=ParseStatus.PENDING,
        server_default=ParseStatus.PENDING.value,
    )
    parse_error: Mapped[str | None] = mapped_column(Text)
    content_html: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("resume_id", "version_no"),
        CheckConstraint("(kind = 'tailored') = (job_id IS NOT NULL)", name="tailored_has_job"),
        # (resume_id, version_no) is already indexed by its unique constraint.
        Index("ix_resume_versions_user_id", "user_id"),
    )


class ResumeAtsReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Phase 0 §5.2 — general ATS quality report for one resume version."""

    __tablename__ = "resume_ats_reports"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    resume_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False
    )
    ats_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    section_scores: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    strengths: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    missing_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    top_roles: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    suggestions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    linkedin_summary: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("ats_score BETWEEN 0 AND 100", name="ats_score_range"),
        Index("ix_resume_ats_reports_user_id", "user_id"),
        Index("ix_resume_ats_reports_resume_version_id", "resume_version_id"),
    )

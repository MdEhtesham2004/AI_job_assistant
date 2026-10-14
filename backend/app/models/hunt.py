"""Phase 16 — easier job hunt: daily digest, skill-gap plan, screening answers."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import Date, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Digest(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One day's best matches for one user (at most one per local day)."""

    __tablename__ = "digests"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    digest_date: Mapped[date] = mapped_column(Date, nullable=False)  # the user's local day
    # [{job_id, title, company, location, score, decision}], best first.
    jobs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    new_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # AI calls made
    emailed: Mapped[bool] = mapped_column(nullable=False, default=False)
    email_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("user_id", "digest_date", name="uq_digests_user_id_digest_date"),
    )


class SkillPlanRecord(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A 2-week learning plan for the user's most frequent skill gaps."""

    __tablename__ = "skill_plans"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    gaps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    plan: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("ix_skill_plans_user_id_created_at", "user_id", "created_at"),)


class InterviewPrep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Phase 17 — a one-page preparation pack for a real interview at one job."""

    __tablename__ = "interview_preps"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="SET NULL")
    )
    pack: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    file_key: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_interview_preps_user_id_job_id"),
    )


class ScreeningAnswers(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ready-to-paste answers to application-form questions for one job."""

    __tablename__ = "screening_answers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    # [{key, question, answer, edited, custom}]
    answers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_screening_answers_user_id_job_id"),
    )

"""Phase 15 — AI mock interview: plan, transcript (no audio is stored) and report."""

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
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, text_enum
from app.models.enums import (
    InterviewDifficulty,
    InterviewRound,
    InterviewSpeaker,
    InterviewStatus,
    InterviewVerdict,
)


class Interview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One mock interview for one job (6 minutes by default)."""

    __tablename__ = "interviews"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="SET NULL")
    )
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="SET NULL")
    )
    # "Retry weak questions": the interview whose weak answers this one repeats.
    retry_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id", ondelete="SET NULL")
    )
    round: Mapped[InterviewRound] = mapped_column(
        text_enum(InterviewRound, "interview_round"), nullable=False
    )
    difficulty: Mapped[InterviewDifficulty] = mapped_column(
        text_enum(InterviewDifficulty, "interview_difficulty"), nullable=False
    )
    status: Mapped[InterviewStatus] = mapped_column(
        text_enum(InterviewStatus, "interview_status"),
        nullable=False,
        default=InterviewStatus.PLANNING,
        server_default=InterviewStatus.PLANNING.value,
    )
    minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    plan_task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    report_task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seconds_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # reconnects
    model: Mapped[str | None] = mapped_column(Text)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal(0)
    )

    __table_args__ = (
        Index("ix_interviews_user_id_created_at", "user_id", "created_at"),
        Index("ix_interviews_user_id_job_id", "user_id", "job_id"),
        Index("ix_interviews_user_id_started_at", "user_id", "started_at"),
        CheckConstraint("minutes BETWEEN 2 AND 30", name="minutes_range"),
    )


class InterviewTurn(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One spoken turn, as text (from the realtime session's transcription events)."""

    __tablename__ = "interview_turns"

    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[InterviewSpeaker] = mapped_column(
        text_enum(InterviewSpeaker, "interview_speaker"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    original_text: Mapped[str | None] = mapped_column(Text)  # before the user's correction
    offset_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("interview_id", "seq", name="uq_interview_turns_interview_seq"),
    )


class InterviewReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "interview_reports"

    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    verdict: Mapped[InterviewVerdict] = mapped_column(
        text_enum(InterviewVerdict, "interview_verdict"), nullable=False
    )
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    file_key: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("overall_score BETWEEN 0 AND 100", name="overall_score_range"),
    )

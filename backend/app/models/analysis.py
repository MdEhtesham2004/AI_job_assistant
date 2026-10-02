import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, text_enum
from app.models.enums import AnalysisDecision


class JobAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Phase 0 §5.4 — how well one resume version fits one job. One row per pair (cache)."""

    __tablename__ = "job_analyses"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    resume_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False
    )
    # skills, experience, technology, education, location — each 0-100, from the AI.
    component_scores: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    weights_used: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    # Computed by the backend from component scores × weights (deterministic, auditable).
    match_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    matched_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    missing_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    recommendations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    red_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    seniority_fit: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[AnalysisDecision] = mapped_column(
        text_enum(AnalysisDecision, "analysis_decision"), nullable=False
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("job_id", "resume_version_id"),
        CheckConstraint("match_score BETWEEN 0 AND 100", name="match_score_range"),
        Index("ix_job_analyses_user_id_match_score", "user_id", "match_score"),
    )

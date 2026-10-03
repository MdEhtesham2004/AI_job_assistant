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
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, text_enum
from app.models.enums import ApprovalStatus, UserRole


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Phase 0 §5.1. Login is allowed only when is_active and approval_status = approved."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        text_enum(UserRole, "user_role"),
        nullable=False,
        default=UserRole.USER,
        server_default=UserRole.USER.value,
    )
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        text_enum(ApprovalStatus, "approval_status"),
        nullable=False,
        default=ApprovalStatus.PENDING,
        server_default=ApprovalStatus.PENDING.value,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # Kept in sync with role = admin (required by fastapi-users in Phase 4).
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_users_approval_status", "approval_status"),)

    def __repr__(self) -> str:
        return f"<User {self.email} role={self.role} status={self.approval_status}>"


class AuthRefreshToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Phase 0 §5.1 (+ family_id). Only the SHA-256 of the token is stored.

    Every rotation creates a new row in the same family; reusing a revoked token revokes
    the whole family (token theft detection).
    """

    __tablename__ = "auth_refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth_refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(INET)

    __table_args__ = (
        Index("ix_auth_refresh_tokens_user_id_expires_at", "user_id", "expires_at"),
        Index("ix_auth_refresh_tokens_family_id", "family_id"),
    )


DEFAULT_SCORE_WEIGHTS = {
    "skills": 40,
    "experience": 25,
    "technology": 20,
    "education": 10,
    "location": 5,
}


class Profile(TimestampMixin, Base):
    """Phase 0 section 5.1 - 1:1 with users (created on first access)."""

    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    phone: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    headline: Mapped[str | None] = mapped_column(Text)
    links: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, default="Asia/Kolkata", server_default="Asia/Kolkata"
    )


class UserSettings(TimestampMixin, Base):
    """Phase 0 section 5.1 - per-user preferences; most are used from later phases."""

    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    threshold_use_master: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=85, server_default=text("85")
    )
    threshold_tailor: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=65, server_default=text("65")
    )
    score_weights: Mapped[dict[str, int]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: dict(DEFAULT_SCORE_WEIGHTS),
        server_default=text(
            """'{"skills": 40, "experience": 25, "technology": 20, """
            """"education": 10, "location": 5}'::jsonb"""
        ),
    )
    auto_analyze_new_jobs: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    daily_send_cap: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=25, server_default=text("25")
    )
    send_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=90, server_default=text("90")
    )
    recipient_cooldown_days: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=30, server_default=text("30")
    )
    follow_up_days: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=7, server_default=text("7")
    )
    no_response_days: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=21, server_default=text("21")
    )
    linkedin_source_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    automation_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    automation_min_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=70, server_default=text("70")
    )
    # Phase 13 pipeline: LinkedIn keywords searched on a schedule, capped per run.
    automation_keywords: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    automation_interval_hours: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=24, server_default=text("24")
    )
    automation_max_jobs: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=5, server_default=text("5")
    )
    automation_posted_limit: Mapped[str] = mapped_column(
        Text, nullable=False, default="week", server_default="week"
    )
    automation_tailor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    automation_cover_letter: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    automation_last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    llm_models: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    monthly_ai_budget_usd: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=Decimal("5.00"), server_default=text("5.00")
    )

    __table_args__ = (
        CheckConstraint(
            "threshold_use_master BETWEEN 0 AND 100 AND threshold_tailor BETWEEN 0 AND 100",
            name="threshold_range",
        ),
        CheckConstraint("threshold_tailor < threshold_use_master", name="threshold_order"),
        CheckConstraint(
            "daily_send_cap >= 0 AND send_interval_seconds >= 0 AND recipient_cooldown_days >= 0 "
            "AND follow_up_days >= 0 AND no_response_days >= 0 AND monthly_ai_budget_usd >= 0",
            name="non_negative",
        ),
        CheckConstraint(
            "automation_min_score BETWEEN 0 AND 100", name="automation_min_score_range"
        ),
    )

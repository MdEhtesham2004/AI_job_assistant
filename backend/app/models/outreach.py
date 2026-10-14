"""Phase 12/13 — Gmail, contacts, do-not-contact, emails, reply classifications (Phase 0 §5)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, text_enum
from app.models.enums import (
    ContactApproval,
    ContactSource,
    ContactVerification,
    DncSource,
    EmailDirection,
    EmailStatus,
    EmailType,
    OAuthStatus,
    ReplyCategory,
)


class OAuthAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The user's connected Gmail. Tokens are Fernet-encrypted, never stored in clear."""

    __tablename__ = "oauth_accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    account_email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    access_token_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    refresh_token_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[OAuthStatus] = mapped_column(
        text_enum(OAuthStatus, "oauth_status"),
        nullable=False,
        default=OAuthStatus.CONNECTED,
        server_default=OAuthStatus.CONNECTED.value,
    )
    gmail_history_id: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("user_id", "provider"),)


class Contact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A recruiter address. Per user, never shared; needs the user's approval."""

    __tablename__ = "contacts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    role_title: Mapped[str | None] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Text)
    company_domain: Mapped[str | None] = mapped_column(Text)
    source: Mapped[ContactSource] = mapped_column(
        text_enum(ContactSource, "contact_source"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    source_excerpt: Mapped[str | None] = mapped_column(Text)  # evidence
    verification: Mapped[ContactVerification] = mapped_column(
        text_enum(ContactVerification, "contact_verification"),
        nullable=False,
        default=ContactVerification.UNVERIFIED,
        server_default=ContactVerification.UNVERIFIED.value,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval: Mapped[ContactApproval] = mapped_column(
        text_enum(ContactApproval, "contact_approval"),
        nullable=False,
        default=ContactApproval.PENDING,
        server_default=ContactApproval.PENDING.value,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("user_id", "email"),
        CheckConstraint(
            "approval <> 'approved' OR verification <> 'invalid'", name="approved_not_invalid"
        ),
        Index("ix_contacts_user_id_approval", "user_id", "approval"),
    )


class DoNotContact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "do_not_contact"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str | None] = mapped_column(CITEXT)
    domain: Mapped[str | None] = mapped_column(CITEXT)
    reason: Mapped[str | None] = mapped_column(Text)
    source: Mapped[DncSource] = mapped_column(text_enum(DncSource, "dnc_source"), nullable=False)

    __table_args__ = (
        CheckConstraint("(email IS NULL) <> (domain IS NULL)", name="target"),
        Index(
            "uq_do_not_contact_user_id_email",
            "user_id",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
        Index(
            "uq_do_not_contact_user_id_domain",
            "user_id",
            "domain",
            unique=True,
            postgresql_where=text("domain IS NOT NULL"),
        ),
    )


class Email(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One email. Outbound emails carry an idempotency key, so the same email never goes twice."""

    __tablename__ = "emails"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL")
    )
    direction: Mapped[EmailDirection] = mapped_column(
        text_enum(EmailDirection, "email_direction"), nullable=False
    )
    email_type: Mapped[EmailType] = mapped_column(
        text_enum(EmailType, "email_type"), nullable=False
    )
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    in_reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emails.id", ondelete="SET NULL")
    )
    from_address: Mapped[str] = mapped_column(CITEXT, nullable=False)
    to_address: Mapped[str] = mapped_column(CITEXT, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[EmailStatus] = mapped_column(
        text_enum(EmailStatus, "email_status"), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gmail_message_id: Mapped[str | None] = mapped_column(Text, unique=True)
    gmail_thread_id: Mapped[str | None] = mapped_column(Text)
    # Message-ID we set (Gmail replaces it, so it only marks "Gmail was called").
    message_id_header: Mapped[str | None] = mapped_column(Text)
    # The Message-ID Gmail really used — follow-ups reply to it (In-Reply-To/References).
    rfc822_message_id: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(
            "uq_emails_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("direction = 'outbound'"),
        ),
        CheckConstraint(
            "direction <> 'outbound' OR idempotency_key IS NOT NULL", name="outbound_has_key"
        ),
        CheckConstraint(
            "status <> 'sent' OR (approved_at IS NOT NULL AND sent_at IS NOT NULL)",
            name="sent_requires_approval",
        ),
        Index("ix_emails_user_id_status_scheduled_for", "user_id", "status", "scheduled_for"),
        Index("ix_emails_gmail_thread_id", "gmail_thread_id"),
    )


class ReplyClassification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """AI reading of one inbound reply (Phase 13). One per inbound email."""

    __tablename__ = "reply_classifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    category: Mapped[ReplyCategory] = mapped_column(
        text_enum(ReplyCategory, "reply_category"), nullable=False
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action: Mapped[str | None] = mapped_column(Text)
    applied_transition: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # NULL = not asked / not answered yet; True/False = the user's answer.
    user_confirmed: Mapped[bool | None] = mapped_column(Boolean)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )


class EmailAttachment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_attachments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emails.id", ondelete="CASCADE"), nullable=False
    )
    file_key: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="SET NULL")
    )
    cover_letter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cover_letters.id", ondelete="SET NULL")
    )

    __table_args__ = (Index("ix_email_attachments_email_id", "email_id"),)

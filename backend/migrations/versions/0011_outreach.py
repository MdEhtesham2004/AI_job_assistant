"""Phase 12: Gmail accounts, contacts, do-not-contact, emails, attachments

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-03 10:51:23.985215
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JOB_SOURCES = "'jsearch', 'manual', 'legacy_sheet'"
_JOB_SOURCE_TABLES = ("jobs", "job_search_runs")


def _job_source(values: str, length: int) -> None:
    for table in _JOB_SOURCE_TABLES:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_job_source")
        op.alter_column(table, "source", type_=sa.String(length=length), existing_nullable=False)
        op.create_check_constraint(op.f(f"ck_{table}_job_source"), table, f"source IN ({values})")


def upgrade() -> None:
    # LinkedIn hiring posts become private jobs ('linkedin_post' needs 13 characters).
    _job_source(_JOB_SOURCES + ", 'linkedin_post'", 13)
    op.create_table(
        "do_not_contact",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("domain", postgresql.CITEXT(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=6),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('user', 'reply', 'bounce')", name=op.f("ck_do_not_contact_dnc_source")
        ),
        sa.CheckConstraint(
            "(email IS NULL) <> (domain IS NULL)", name=op.f("ck_do_not_contact_target")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_do_not_contact_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_do_not_contact")),
    )
    op.create_index(
        "uq_do_not_contact_user_id_domain",
        "do_not_contact",
        ["user_id", "domain"],
        unique=True,
        postgresql_where=sa.text("domain IS NOT NULL"),
    )
    op.create_index(
        "uq_do_not_contact_user_id_email",
        "do_not_contact",
        ["user_id", "email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.create_table(
        "oauth_accounts",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("account_email", postgresql.CITEXT(), nullable=False),
        sa.Column("access_token_enc", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token_enc", sa.LargeBinary(), nullable=True),
        sa.Column("scopes", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=9),
            server_default="connected",
            nullable=False,
        ),
        sa.Column("gmail_history_id", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('connected', 'expired', 'revoked', 'error')",
            name=op.f("ck_oauth_accounts_oauth_status"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_oauth_accounts_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_accounts")),
        sa.UniqueConstraint("user_id", "provider", name=op.f("uq_oauth_accounts_user_id_provider")),
    )
    op.create_table(
        "contacts",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("role_title", sa.Text(), nullable=True),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("company_domain", sa.Text(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=13),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column(
            "verification",
            sa.String(length=10),
            server_default="unverified",
            nullable=False,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approval",
            sa.String(length=8),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "approval <> 'approved' OR verification <> 'invalid'",
            name=op.f("ck_contacts_approved_not_invalid"),
        ),
        sa.CheckConstraint(
            "approval IN ('pending', 'approved', 'rejected')",
            name=op.f("ck_contacts_contact_approval"),
        ),
        sa.CheckConstraint(
            "source IN ('user', 'job_posting', 'linkedin_post', 'hunter', 'company_site', "
            "'legacy_import')",
            name=op.f("ck_contacts_contact_source"),
        ),
        sa.CheckConstraint(
            "verification IN ('unverified', 'valid', 'risky', 'invalid')",
            name=op.f("ck_contacts_contact_verification"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_contacts_job_id"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_contacts_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacts")),
        sa.UniqueConstraint("user_id", "email", name=op.f("uq_contacts_user_id_email")),
    )
    op.create_index(
        "ix_contacts_user_id_approval", "contacts", ["user_id", "approval"], unique=False
    )
    op.create_table(
        "emails",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column(
            "direction",
            sa.String(length=8),
            nullable=False,
        ),
        sa.Column(
            "email_type",
            sa.String(length=11),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("in_reply_to_id", sa.UUID(), nullable=True),
        sa.Column("from_address", postgresql.CITEXT(), nullable=False),
        sa.Column("to_address", postgresql.CITEXT(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=8),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gmail_message_id", sa.Text(), nullable=True),
        sa.Column("gmail_thread_id", sa.Text(), nullable=True),
        sa.Column("message_id_header", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "direction <> 'outbound' OR idempotency_key IS NOT NULL",
            name=op.f("ck_emails_outbound_has_key"),
        ),
        sa.CheckConstraint(
            "direction IN ('outbound', 'inbound')", name=op.f("ck_emails_email_direction")
        ),
        sa.CheckConstraint(
            "email_type IN ('application', 'follow_up_1', 'follow_up_2', 'reply')",
            name=op.f("ck_emails_email_type"),
        ),
        sa.CheckConstraint(
            "status <> 'sent' OR (approved_at IS NOT NULL AND sent_at IS NOT NULL)",
            name=op.f("ck_emails_sent_requires_approval"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'queued', 'sending', 'sent', 'failed', 'bounced', "
            "'rejected', 'received')",
            name=op.f("ck_emails_email_status"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_emails_application_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["contacts.id"], name=op.f("fk_emails_contact_id"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["in_reply_to_id"],
            ["emails.id"],
            name=op.f("fk_emails_in_reply_to_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_emails_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_emails")),
        sa.UniqueConstraint("gmail_message_id", name=op.f("uq_emails_gmail_message_id")),
    )
    op.create_index("ix_emails_gmail_thread_id", "emails", ["gmail_thread_id"], unique=False)
    op.create_index(
        "ix_emails_user_id_status_scheduled_for",
        "emails",
        ["user_id", "status", "scheduled_for"],
        unique=False,
    )
    op.create_index(
        "uq_emails_idempotency_key",
        "emails",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("direction = 'outbound'"),
    )
    op.create_table(
        "email_attachments",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("email_id", sa.UUID(), nullable=False),
        sa.Column("file_key", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("resume_version_id", sa.UUID(), nullable=True),
        sa.Column("cover_letter_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["cover_letter_id"],
            ["cover_letters.id"],
            name=op.f("fk_email_attachments_cover_letter_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["email_id"],
            ["emails.id"],
            name=op.f("fk_email_attachments_email_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resume_version_id"],
            ["resume_versions.id"],
            name=op.f("fk_email_attachments_resume_version_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_email_attachments_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_attachments")),
    )
    op.create_index(
        "ix_email_attachments_email_id", "email_attachments", ["email_id"], unique=False
    )
    op.add_column("applications", sa.Column("contact_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_applications_contact_id"),
        "applications",
        "contacts",
        ["contact_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(op.f("fk_applications_contact_id"), "applications", type_="foreignkey")
    op.drop_column("applications", "contact_id")
    op.drop_index("ix_email_attachments_email_id", table_name="email_attachments")
    op.drop_table("email_attachments")
    op.drop_index(
        "uq_emails_idempotency_key",
        table_name="emails",
        postgresql_where=sa.text("direction = 'outbound'"),
    )
    op.drop_index("ix_emails_user_id_status_scheduled_for", table_name="emails")
    op.drop_index("ix_emails_gmail_thread_id", table_name="emails")
    op.drop_table("emails")
    op.drop_index("ix_contacts_user_id_approval", table_name="contacts")
    op.drop_table("contacts")
    op.drop_table("oauth_accounts")
    op.drop_index(
        "uq_do_not_contact_user_id_email",
        table_name="do_not_contact",
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.drop_index(
        "uq_do_not_contact_user_id_domain",
        table_name="do_not_contact",
        postgresql_where=sa.text("domain IS NOT NULL"),
    )
    op.drop_table("do_not_contact")
    op.execute("DELETE FROM jobs WHERE source = 'linkedin_post'")
    _job_source(_JOB_SOURCES, 12)

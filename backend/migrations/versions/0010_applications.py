"""Phase 11: applications, application_status_history

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-02

Written by hand from the models (Phase 0 §5.6). applications.contact_id (FK contacts)
is added in Phase 12 together with the contacts table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = (
    "('ready_to_apply', 'waiting_for_approval', 'approved', 'sending', 'applied', 'responded', "
    "'interview', 'offer', 'rejected_by_user', 'failed', 'rejected', 'no_response', 'withdrawn')"
)


def _id() -> sa.Column:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _now(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "applications",
        _id(),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(length=8), server_default="email", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="ready_to_apply", nullable=False),
        sa.Column("resume_version_id", sa.UUID(), nullable=True),
        sa.Column("cover_letter_id", sa.UUID(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        _now("last_status_at"),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(
            "channel IN ('email', 'portal', 'referral')",
            name=op.f("ck_applications_application_channel"),
        ),
        sa.CheckConstraint(
            f"status IN {STATUSES}", name=op.f("ck_applications_application_status")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_applications_user_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_applications_job_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["resume_version_id"],
            ["resume_versions.id"],
            name=op.f("fk_applications_resume_version_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["cover_letter_id"],
            ["cover_letters.id"],
            name=op.f("fk_applications_cover_letter_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
        sa.UniqueConstraint("user_id", "job_id", name=op.f("uq_applications_user_id_job_id")),
    )
    op.create_index("ix_applications_user_id_status", "applications", ["user_id", "status"])

    op.create_table(
        "application_status_history",
        _id(),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=11), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        _now("created_at"),
        sa.CheckConstraint(
            f"from_status IN {STATUSES}", name=op.f("ck_application_status_history_from_status")
        ),
        sa.CheckConstraint(
            f"to_status IN {STATUSES}", name=op.f("ck_application_status_history_to_status")
        ),
        sa.CheckConstraint(
            "source IN ('user', 'system', 'email_reply')",
            name=op.f("ck_application_status_history_status_change_source"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_application_status_history_user_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_application_status_history_application_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_status_history")),
    )
    op.create_index(
        "ix_application_status_history_application_id_created_at",
        "application_status_history",
        ["application_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_application_status_history_application_id_created_at",
        table_name="application_status_history",
    )
    op.drop_table("application_status_history")
    op.drop_index("ix_applications_user_id_status", table_name="applications")
    op.drop_table("applications")

"""Phase 13: reply classifications, Gmail's real Message-ID, automation settings

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-03 13:18:17.340894
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reply_classifications",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("email_id", sa.UUID(), nullable=False),
        sa.Column(
            "category",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=True),
        sa.Column(
            "applied_transition", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("user_confirmed", sa.Boolean(), nullable=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
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
            "category IN ('interview_invite', 'info_request', 'rejection', 'offer', "
            "'auto_reply', 'other')",
            name=op.f("ck_reply_classifications_reply_category"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_reply_classifications_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["email_id"],
            ["emails.id"],
            name=op.f("fk_reply_classifications_email_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_reply_classifications_user_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reply_classifications")),
        sa.UniqueConstraint("email_id", name=op.f("uq_reply_classifications_email_id")),
    )
    op.add_column("emails", sa.Column("rfc822_message_id", sa.Text(), nullable=True))
    op.add_column(
        "user_settings",
        sa.Column(
            "automation_keywords",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "automation_interval_hours",
            sa.SmallInteger(),
            server_default=sa.text("24"),
            nullable=False,
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "automation_max_jobs", sa.SmallInteger(), server_default=sa.text("5"), nullable=False
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column("automation_posted_limit", sa.Text(), server_default="week", nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "automation_tailor", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "automation_cover_letter", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column("automation_last_run_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "automation_last_run_at")
    op.drop_column("user_settings", "automation_cover_letter")
    op.drop_column("user_settings", "automation_tailor")
    op.drop_column("user_settings", "automation_posted_limit")
    op.drop_column("user_settings", "automation_max_jobs")
    op.drop_column("user_settings", "automation_interval_hours")
    op.drop_column("user_settings", "automation_keywords")
    op.drop_column("emails", "rfc822_message_id")
    op.drop_table("reply_classifications")

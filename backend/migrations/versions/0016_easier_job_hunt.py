"""Phase 16 easier job hunt: digests, skill_plans, screening_answers, digest settings

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-05 16:08:19.060928
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "digests",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("digest_date", sa.Date(), nullable=False),
        sa.Column("jobs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("new_jobs", sa.Integer(), nullable=False),
        sa.Column("scored", sa.Integer(), nullable=False),
        sa.Column("emailed", sa.Boolean(), nullable=False),
        sa.Column("email_error", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_digests_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_digests")),
        sa.UniqueConstraint("user_id", "digest_date", name="uq_digests_user_id_digest_date"),
    )
    op.create_table(
        "skill_plans",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("gaps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_skill_plans_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_plans")),
    )
    op.create_index(
        "ix_skill_plans_user_id_created_at", "skill_plans", ["user_id", "created_at"], unique=False
    )
    op.create_table(
        "screening_answers",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_screening_answers_job_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_screening_answers_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_screening_answers")),
        sa.UniqueConstraint("user_id", "job_id", name="uq_screening_answers_user_id_job_id"),
    )
    op.add_column("profiles", sa.Column("notice_period", sa.Text(), nullable=True))
    op.add_column("profiles", sa.Column("expected_salary", sa.Text(), nullable=True))
    op.add_column(
        "user_settings",
        sa.Column("digest_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("digest_hour", sa.SmallInteger(), server_default=sa.text("8"), nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "digest_min_score", sa.SmallInteger(), server_default=sa.text("70"), nullable=False
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column("digest_email", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_user_settings_digest_range"),
        "user_settings",
        "digest_hour BETWEEN 0 AND 23 AND digest_min_score BETWEEN 0 AND 100",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_user_settings_digest_range"), "user_settings", type_="check")
    op.drop_column("user_settings", "digest_email")
    op.drop_column("user_settings", "digest_min_score")
    op.drop_column("user_settings", "digest_hour")
    op.drop_column("user_settings", "digest_enabled")
    op.drop_column("profiles", "expected_salary")
    op.drop_column("profiles", "notice_period")
    op.drop_table("screening_answers")
    op.drop_index("ix_skill_plans_user_id_created_at", table_name="skill_plans")
    op.drop_table("skill_plans")
    op.drop_table("digests")

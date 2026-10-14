"""Phase 9: job_analyses

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-02

Written by hand from the model (Phase 0 §5.4): one analysis per job + resume version.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def _now(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "job_analyses",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("resume_version_id", sa.UUID(), nullable=False),
        sa.Column("component_scores", JSONB, nullable=False),
        sa.Column("weights_used", JSONB, nullable=False),
        sa.Column("match_score", sa.SmallInteger(), nullable=False),
        sa.Column("matched_skills", JSONB, nullable=False),
        sa.Column("missing_skills", JSONB, nullable=False),
        sa.Column("recommendations", JSONB, nullable=False),
        sa.Column("red_flags", JSONB, nullable=False),
        sa.Column("seniority_fit", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(length=10), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(
            "decision IN ('use_master', 'tailor', 'skip')",
            name=op.f("ck_job_analyses_analysis_decision"),
        ),
        sa.CheckConstraint(
            "match_score BETWEEN 0 AND 100", name=op.f("ck_job_analyses_match_score_range")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_job_analyses_user_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_job_analyses_job_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["resume_version_id"],
            ["resume_versions.id"],
            name=op.f("fk_job_analyses_resume_version_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_analyses")),
        sa.UniqueConstraint(
            "job_id", "resume_version_id", name=op.f("uq_job_analyses_job_id_resume_version_id")
        ),
    )
    op.create_index(
        "ix_job_analyses_user_id_match_score", "job_analyses", ["user_id", "match_score"]
    )


def downgrade() -> None:
    op.drop_index("ix_job_analyses_user_id_match_score", table_name="job_analyses")
    op.drop_table("job_analyses")

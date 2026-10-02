"""Phase 10: cover_letters

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-02

Written by hand from the model (Phase 0 §5.4). Tailored resumes need no new table:
they are resume_versions with kind = 'tailored' and job_id set (FK added in 0006).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "cover_letters",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("resume_version_id", sa.UUID(), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("file_key", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=5), server_default="draft", nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(
            "status IN ('draft', 'final')", name=op.f("ck_cover_letters_document_status")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_cover_letters_user_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_cover_letters_job_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["resume_version_id"],
            ["resume_versions.id"],
            name=op.f("fk_cover_letters_resume_version_id"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cover_letters")),
    )
    op.create_index("ix_cover_letters_user_id_job_id", "cover_letters", ["user_id", "job_id"])


def downgrade() -> None:
    op.drop_index("ix_cover_letters_user_id_job_id", table_name="cover_letters")
    op.drop_table("cover_letters")

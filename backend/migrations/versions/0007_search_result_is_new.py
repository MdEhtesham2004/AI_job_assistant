"""Phase 8 (admin change request): job_search_results.is_new

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-02

Search results show "New" vs "Already in your list". Stored when the result is saved —
comparing timestamps from two clocks (app and database) is not reliable.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job_search_results",
        sa.Column("is_new", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("job_search_results", "is_new")

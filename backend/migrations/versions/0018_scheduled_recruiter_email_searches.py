"""Phase 19 scheduled recruiter-email searches: saved-search type + per-user switch

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-12 21:01:58.795054
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "saved_searches", sa.Column("kind", sa.Text(), server_default="jobs", nullable=False)
    )
    op.add_column(
        "saved_searches", sa.Column("posted_limit", sa.Text(), server_default="24h", nullable=False)
    )
    op.add_column(
        "saved_searches", sa.Column("max_posts", sa.Integer(), server_default="25", nullable=False)
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "linkedin_schedule_allowed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    for name, condition in (
        ("kind_valid", "kind IN ('jobs', 'linkedin')"),
        ("posted_limit_valid", "posted_limit IN ('24h', 'week', 'month')"),
        ("max_posts_range", "max_posts BETWEEN 5 AND 200"),
    ):
        op.create_check_constraint(op.f(f"ck_saved_searches_{name}"), "saved_searches", condition)


def downgrade() -> None:
    for name in ("kind_valid", "posted_limit_valid", "max_posts_range"):
        op.drop_constraint(op.f(f"ck_saved_searches_{name}"), "saved_searches", type_="check")
    op.drop_column("user_settings", "linkedin_schedule_allowed")
    op.drop_column("saved_searches", "max_posts")
    op.drop_column("saved_searches", "posted_limit")
    op.drop_column("saved_searches", "kind")

"""Phase 14 cost control: paid-API call log (provider_calls) and per-user quotas

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-04 13:26:42.990979
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_calls",
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("cache_key", sa.Text(), nullable=False),
        sa.Column("query", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cached", sa.Boolean(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("results", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("quota_remaining", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_provider_calls_user_id"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_calls")),
    )
    op.create_index(
        "ix_provider_calls_provider_created_at",
        "provider_calls",
        ["provider", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_provider_calls_user_id_provider_created_at",
        "provider_calls",
        ["user_id", "provider", "created_at"],
        unique=False,
    )
    columns = [
        ("jsearch_requests_per_month", sa.Integer(), "60"),
        ("jsearch_max_pages", sa.Integer(), "1"),
        ("jsearch_allow_load_more", sa.Boolean(), "true"),
        ("apify_posts_per_month", sa.Integer(), "300"),
        ("apify_runs_per_day", sa.Integer(), "3"),
        ("apify_max_posts_per_fetch", sa.Integer(), "25"),
    ]
    for name, type_, default in columns:
        op.add_column(
            "app_settings",
            sa.Column(name, type_, server_default=sa.text(default), nullable=False),
        )
    for name, condition in CHECKS.items():
        op.create_check_constraint(op.f(f"ck_app_settings_{name}"), "app_settings", condition)


CHECKS = {
    "quotas_non_negative": (
        "jsearch_requests_per_month >= 0 AND apify_posts_per_month >= 0 AND apify_runs_per_day >= 0"
    ),
    "jsearch_max_pages_range": "jsearch_max_pages BETWEEN 1 AND 3",
    "apify_max_posts_range": "apify_max_posts_per_fetch BETWEEN 5 AND 200",
}
# Includes names from earlier drafts of this (unreleased) revision, so any dev or test
# database that ran one can still be downgraded.
DRAFT_COLUMNS = (
    "jsearch_requests_per_month",
    "jsearch_max_pages",
    "jsearch_allow_load_more",
    "apify_posts_per_month",
    "apify_runs_per_month",
    "apify_runs_per_day",
    "apify_max_posts_per_fetch",
)


def downgrade() -> None:
    for name in CHECKS:
        op.execute(f"ALTER TABLE app_settings DROP CONSTRAINT IF EXISTS ck_app_settings_{name}")
    for column in DRAFT_COLUMNS:
        op.execute(f"ALTER TABLE app_settings DROP COLUMN IF EXISTS {column}")
    op.drop_index("ix_provider_calls_user_id_provider_created_at", table_name="provider_calls")
    op.drop_index("ix_provider_calls_provider_created_at", table_name="provider_calls")
    op.drop_table("provider_calls")

"""Phase 20: daily apply pipeline hour (user_settings.automation_hour)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-13 11:48:03.935496
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column(
            "automation_hour", sa.SmallInteger(), server_default=sa.text("10"), nullable=False
        ),
    )

    op.create_check_constraint(
        op.f("ck_user_settings_automation_hour_range"),
        "user_settings",
        "automation_hour BETWEEN 0 AND 23",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_user_settings_automation_hour_range"), "user_settings", type_="check"
    )
    op.drop_column("user_settings", "automation_hour")

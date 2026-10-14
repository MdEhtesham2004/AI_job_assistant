"""Phase 15 AI mock interview: interviews, interview_turns, interview_reports, limits

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-04 15:17:20.736931
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = "'planning', 'ready', 'in_progress', 'ended', 'reporting', 'completed', 'failed'"


def _timestamps(updated: bool = True) -> list[sa.Column]:  # type: ignore[type-arg]
    cols = [
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]
    if updated:
        cols.append(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            )
        )
    return cols


def upgrade() -> None:
    op.create_table(
        "interviews",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=True),
        sa.Column("resume_version_id", sa.UUID(), nullable=True),
        sa.Column("retry_of_id", sa.UUID(), nullable=True),
        sa.Column("round", sa.String(length=10), nullable=False),
        sa.Column("difficulty", sa.String(length=6), nullable=False),
        sa.Column("status", sa.String(length=11), server_default="planning", nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("plan_task_id", sa.UUID(), nullable=True),
        sa.Column("report_task_id", sa.UUID(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("seconds_used", sa.Integer(), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=10, scale=4), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "round IN ('mixed', 'hr', 'technical', 'behavioral')",
            name=op.f("ck_interviews_interview_round"),
        ),
        sa.CheckConstraint(
            "difficulty IN ('entry', 'mid', 'senior')",
            name=op.f("ck_interviews_interview_difficulty"),
        ),
        sa.CheckConstraint(f"status IN ({STATUSES})", name=op.f("ck_interviews_interview_status")),
        sa.CheckConstraint("minutes BETWEEN 2 AND 30", name=op.f("ck_interviews_minutes_range")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_interviews_user_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_interviews_job_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_interviews_application_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resume_version_id"],
            ["resume_versions.id"],
            name=op.f("fk_interviews_resume_version_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["retry_of_id"],
            ["interviews.id"],
            name=op.f("fk_interviews_retry_of_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interviews")),
    )
    for name, cols in (
        ("ix_interviews_user_id_created_at", ["user_id", "created_at"]),
        ("ix_interviews_user_id_job_id", ["user_id", "job_id"]),
        ("ix_interviews_user_id_started_at", ["user_id", "started_at"]),
    ):
        op.create_index(name, "interviews", cols, unique=False)

    op.create_table(
        "interview_turns",
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(length=11), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("offset_ms", sa.Integer(), nullable=False),
        sa.Column("edited", sa.Boolean(), nullable=False),
        *_timestamps(updated=False),
        sa.CheckConstraint(
            "speaker IN ('interviewer', 'candidate')",
            name=op.f("ck_interview_turns_interview_speaker"),
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_interview_turns_interview_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_interview_turns_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview_turns")),
        sa.UniqueConstraint("interview_id", "seq", name=op.f("uq_interview_turns_interview_seq")),
    )

    op.create_table(
        "interview_reports",
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("verdict", sa.String(length=8), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("file_key", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "verdict IN ('ready', 'almost', 'practice')",
            name=op.f("ck_interview_reports_interview_verdict"),
        ),
        sa.CheckConstraint(
            "overall_score BETWEEN 0 AND 100",
            name=op.f("ck_interview_reports_overall_score_range"),
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_interview_reports_interview_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_interview_reports_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview_reports")),
        sa.UniqueConstraint("interview_id", name=op.f("uq_interview_reports_interview_id")),
    )

    op.add_column(
        "app_settings",
        sa.Column(
            "interviews_per_month", sa.Integer(), server_default=sa.text("10"), nullable=False
        ),
    )
    op.add_column(
        "app_settings",
        sa.Column("interview_minutes", sa.Integer(), server_default=sa.text("6"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_app_settings_interviews_non_negative"), "app_settings", "interviews_per_month >= 0"
    )
    op.create_check_constraint(
        op.f("ck_app_settings_interview_minutes_range"),
        "app_settings",
        "interview_minutes BETWEEN 2 AND 30",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_app_settings_interview_minutes_range"), "app_settings", "check")
    op.drop_constraint(op.f("ck_app_settings_interviews_non_negative"), "app_settings", "check")
    op.drop_column("app_settings", "interview_minutes")
    op.drop_column("app_settings", "interviews_per_month")
    op.drop_table("interview_reports")
    op.drop_table("interview_turns")
    for name in (
        "ix_interviews_user_id_started_at",
        "ix_interviews_user_id_job_id",
        "ix_interviews_user_id_created_at",
    ):
        op.drop_index(name, table_name="interviews")
    op.drop_table("interviews")

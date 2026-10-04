import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import ApplicationStatus


class RateRead(BaseModel):
    key: str
    applied: int
    responded: int
    rate: float | None


class ActivityRead(BaseModel):
    application_id: uuid.UUID
    job_title: str
    company: str
    to_status: ApplicationStatus
    source: str
    note: str | None
    at: datetime


class DashboardRead(BaseModel):
    jobs_found: int
    jobs_new_this_week: int
    stages: dict[str, int]  # same groups as the Applications board
    statuses: dict[str, int]
    waiting_for_approval: int
    applied_total: int
    responses: int
    response_rate: float | None
    interviews: int  # ever reached (from the timeline)
    offers: int
    rejected: int
    emails_sent: int
    emails_sent_today: int
    tasks_running: int
    ai_cost_month_usd: Decimal
    by_source: list[RateRead]
    by_resume: list[RateRead]
    activity: list[ActivityRead]

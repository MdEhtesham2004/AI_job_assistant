import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class AuditEntryRead(BaseModel):
    id: uuid.UUID
    created_at: datetime
    actor_type: str
    user_email: str | None
    action: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    data: dict[str, Any] | None
    ip_address: str | None


class FeatureCost(BaseModel):
    feature: str
    cost_usd: Decimal
    calls: int


class UserUsageRead(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    applications: int
    emails_sent_30d: int
    ai_cost_month_usd: Decimal
    last_login_at: datetime | None
    # Paid data APIs this month (real calls only; cache hits are free).
    jsearch_requests_month: int = 0
    apify_posts_month: int = 0


class ProviderUsageRead(BaseModel):
    provider: str  # jsearch | apify
    calls: int  # real (billed) calls this month
    cache_hits: int  # answered from the shared cache: no cost
    cache_rate: float | None
    units: int  # what the provider bills: JSearch requests, Apify posts
    cost_usd: Decimal  # estimate from the configured prices (0 = no price set)
    failed: int


class AnalyticsRead(BaseModel):
    users_by_status: dict[str, int]
    jobs_in_catalog: int
    applications_total: int
    emails_sent_30d: int
    ai_cost_month_usd: Decimal
    ai_calls_month: int
    ai_cost_by_feature: list[FeatureCost]
    users: list[UserUsageRead]
    failed_tasks_7d: int
    providers: list[ProviderUsageRead] = []
    jsearch_quota_remaining: int | None = None  # RapidAPI plan, from the last real call


class ErrorRead(BaseModel):
    task_id: uuid.UUID
    type: str
    user_email: str | None
    error: str | None
    attempts: int
    created_at: datetime
    finished_at: datetime | None

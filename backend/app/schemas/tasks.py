import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.enums import NotificationSeverity, TaskStatus


class TaskRead(BaseModel):
    id: uuid.UUID
    type: str
    status: TaskStatus
    progress: int
    attempts: int
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TaskCreated(BaseModel):
    task_id: uuid.UUID


class NotificationRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    type: str
    title: str
    body: str | None
    link: str | None
    severity: NotificationSeverity
    read_at: datetime | None
    created_at: datetime


class UnreadCount(BaseModel):
    unread: int


class ServiceCheck(BaseModel):
    status: str  # ok | error | disabled | not_configured
    details: dict[str, Any] = {}


class SystemStatus(BaseModel):
    status: str  # ok | degraded
    checked_at: datetime
    services: dict[str, ServiceCheck]
    tasks: dict[str, int]

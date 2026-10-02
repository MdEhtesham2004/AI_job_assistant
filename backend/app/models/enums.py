"""Enums from Phase 0 §3. Stored as text + CHECK constraint; values are the DB strings."""

from enum import StrEnum


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActorType(StrEnum):
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


class ResumeKind(StrEnum):
    MASTER = "master"
    IMPROVED = "improved"
    TAILORED = "tailored"


class ParseStatus(StrEnum):
    PENDING = "pending"
    PARSED = "parsed"
    FAILED = "failed"


class NotificationSeverity(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"

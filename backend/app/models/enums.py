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


class JobSource(StrEnum):
    JSEARCH = "jsearch"
    MANUAL = "manual"
    LEGACY_SHEET = "legacy_sheet"
    LINKEDIN_POST = "linkedin_post"  # Phase 12: a hiring post with an email (private job)


class JobVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class DescriptionQuality(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"


class JobStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    DUPLICATE = "duplicate"


class UserJobState(StrEnum):
    NEW = "new"
    SAVED = "saved"
    ANALYZED = "analyzed"
    SKIPPED = "skipped"
    ARCHIVED = "archived"


class SearchRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AnalysisDecision(StrEnum):
    USE_MASTER = "use_master"
    TAILOR = "tailor"
    SKIP = "skip"


class DocumentStatus(StrEnum):
    DRAFT = "draft"
    FINAL = "final"


class ApplicationChannel(StrEnum):
    EMAIL = "email"
    PORTAL = "portal"
    REFERRAL = "referral"


class ApplicationStatus(StrEnum):
    """Phase 0 §6.2. Discovery states (new/saved/analyzed/skipped) live in user_jobs."""

    READY_TO_APPLY = "ready_to_apply"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    APPROVED = "approved"
    SENDING = "sending"
    APPLIED = "applied"
    RESPONDED = "responded"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED_BY_USER = "rejected_by_user"
    FAILED = "failed"
    REJECTED = "rejected"
    NO_RESPONSE = "no_response"
    WITHDRAWN = "withdrawn"


class StatusChangeSource(StrEnum):
    USER = "user"
    SYSTEM = "system"
    EMAIL_REPLY = "email_reply"


class OAuthStatus(StrEnum):
    CONNECTED = "connected"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ERROR = "error"


class ContactSource(StrEnum):
    USER = "user"
    JOB_POSTING = "job_posting"
    LINKEDIN_POST = "linkedin_post"
    HUNTER = "hunter"
    COMPANY_SITE = "company_site"
    LEGACY_IMPORT = "legacy_import"


class ContactVerification(StrEnum):
    UNVERIFIED = "unverified"
    VALID = "valid"
    RISKY = "risky"
    INVALID = "invalid"


class ContactApproval(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class DncSource(StrEnum):
    USER = "user"
    REPLY = "reply"
    BOUNCE = "bounce"


class EmailDirection(StrEnum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class EmailType(StrEnum):
    APPLICATION = "application"
    FOLLOW_UP_1 = "follow_up_1"
    FOLLOW_UP_2 = "follow_up_2"
    REPLY = "reply"


class EmailStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    BOUNCED = "bounced"
    REJECTED = "rejected"
    RECEIVED = "received"


class ReplyCategory(StrEnum):
    INTERVIEW_INVITE = "interview_invite"
    INFO_REQUEST = "info_request"
    REJECTION = "rejection"
    OFFER = "offer"
    AUTO_REPLY = "auto_reply"
    OTHER = "other"


class NotificationSeverity(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"

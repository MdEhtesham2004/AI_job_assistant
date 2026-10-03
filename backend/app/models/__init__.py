"""Import every model module here so Alembic autogenerate sees all tables."""

from app.models.accounts import AuthRefreshToken, Profile, User, UserSettings
from app.models.analysis import JobAnalysis
from app.models.applications import Application, ApplicationStatusHistory
from app.models.documents import CoverLetter
from app.models.jobs import Job, JobSearchResult, JobSearchRun, SavedSearch, UserJob
from app.models.outreach import (
    Contact,
    DoNotContact,
    Email,
    EmailAttachment,
    OAuthAccount,
    ReplyClassification,
)
from app.models.resumes import Resume, ResumeAtsReport, ResumeVersion
from app.models.system import AiCall, AppSettings, AuditLog, Notification, Task

__all__ = [
    "AiCall",
    "AppSettings",
    "Application",
    "ApplicationStatusHistory",
    "AuditLog",
    "AuthRefreshToken",
    "Contact",
    "CoverLetter",
    "DoNotContact",
    "Email",
    "EmailAttachment",
    "Job",
    "JobAnalysis",
    "JobSearchResult",
    "JobSearchRun",
    "Notification",
    "OAuthAccount",
    "Profile",
    "ReplyClassification",
    "Resume",
    "ResumeAtsReport",
    "ResumeVersion",
    "SavedSearch",
    "Task",
    "User",
    "UserJob",
    "UserSettings",
]

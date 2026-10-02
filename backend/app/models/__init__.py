"""Import every model module here so Alembic autogenerate sees all tables."""

from app.models.accounts import AuthRefreshToken, Profile, User, UserSettings
from app.models.analysis import JobAnalysis
from app.models.documents import CoverLetter
from app.models.jobs import Job, JobSearchResult, JobSearchRun, SavedSearch, UserJob
from app.models.resumes import Resume, ResumeAtsReport, ResumeVersion
from app.models.system import AiCall, AuditLog, Notification, Task

__all__ = [
    "AiCall",
    "AuditLog",
    "AuthRefreshToken",
    "CoverLetter",
    "Job",
    "JobAnalysis",
    "JobSearchResult",
    "JobSearchRun",
    "Notification",
    "Profile",
    "Resume",
    "ResumeAtsReport",
    "ResumeVersion",
    "SavedSearch",
    "Task",
    "User",
    "UserJob",
    "UserSettings",
]

"""Import every model module here so Alembic autogenerate sees all tables."""

from app.models.accounts import AuthRefreshToken, Profile, User, UserSettings
from app.models.analysis import JobAnalysis
from app.models.applications import Application, ApplicationStatusHistory
from app.models.documents import CoverLetter
from app.models.hunt import Digest, InterviewPrep, ScreeningAnswers, SkillPlanRecord
from app.models.interviews import Interview, InterviewReport, InterviewTurn
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
from app.models.system import AiCall, AppSettings, AuditLog, Notification, ProviderCall, Task

__all__ = [
    "AiCall",
    "AppSettings",
    "Application",
    "ApplicationStatusHistory",
    "AuditLog",
    "AuthRefreshToken",
    "Contact",
    "CoverLetter",
    "Digest",
    "DoNotContact",
    "Email",
    "EmailAttachment",
    "Interview",
    "InterviewPrep",
    "InterviewReport",
    "InterviewTurn",
    "Job",
    "JobAnalysis",
    "JobSearchResult",
    "JobSearchRun",
    "Notification",
    "OAuthAccount",
    "Profile",
    "ProviderCall",
    "ReplyClassification",
    "ScreeningAnswers",
    "SkillPlanRecord",
    "Resume",
    "ResumeAtsReport",
    "ResumeVersion",
    "SavedSearch",
    "Task",
    "User",
    "UserJob",
    "UserSettings",
]

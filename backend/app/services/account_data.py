"""Account › Export my data / Delete my account (Phase 14, GDPR-style).

Export: one ZIP with a JSON file per table (only this user's rows) and every stored file.
Delete: password check, last-admin guard, Gmail access revoked, files removed, then the
user row — the database cascades everything that belongs to the user. The audit log keeps
an entry (user_id becomes NULL), so the deletion itself stays traceable.
"""

import io
import json
import uuid
import zipfile
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, ValidationAppError
from app.core.security import verify_password
from app.integrations.storage import Storage
from app.models.accounts import Profile, User, UserSettings
from app.models.analysis import JobAnalysis
from app.models.applications import Application, ApplicationStatusHistory
from app.models.documents import CoverLetter
from app.models.enums import ActorType, UserRole
from app.models.interviews import Interview, InterviewReport, InterviewTurn
from app.models.jobs import Job, JobSearchRun, SavedSearch, UserJob
from app.models.outreach import Contact, DoNotContact, Email, EmailAttachment, ReplyClassification
from app.models.resumes import Resume, ResumeAtsReport, ResumeVersion
from app.models.system import AiCall, AuditLog, Notification, Task
from app.services.gmail_account import GmailAccountService

# Never exported: secrets and internal-only columns.
SKIP_COLUMNS = {"hashed_password", "access_token_enc", "refresh_token_enc", "raw"}
OWNED_TABLES: list[tuple[str, Any]] = [
    ("profile", Profile),
    ("settings", UserSettings),
    ("resumes", Resume),
    ("resume_versions", ResumeVersion),
    ("ats_reports", ResumeAtsReport),
    ("user_jobs", UserJob),
    ("saved_searches", SavedSearch),
    ("search_runs", JobSearchRun),
    ("match_scores", JobAnalysis),
    ("cover_letters", CoverLetter),
    ("interviews", Interview),
    ("interview_turns", InterviewTurn),
    ("interview_reports", InterviewReport),
    ("applications", Application),
    ("application_history", ApplicationStatusHistory),
    ("contacts", Contact),
    ("do_not_contact", DoNotContact),
    ("emails", Email),
    ("email_attachments", EmailAttachment),
    ("reply_classifications", ReplyClassification),
    ("notifications", Notification),
    ("tasks", Task),
    ("ai_usage", AiCall),
]


def _value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return None
    if hasattr(value, "value"):  # enums
        return value.value
    return value


def _row(instance: Any) -> dict[str, Any]:
    return {
        attr.key: _value(getattr(instance, attr.key))
        for attr in inspect(instance).mapper.column_attrs
        if attr.key not in SKIP_COLUMNS
    }


async def export_zip(session: AsyncSession, storage: Storage, user: User) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "account.json",
            json.dumps(
                {
                    "exported_at": datetime.now(UTC).isoformat(),
                    "user": _row(user),
                },
                indent=2,
                ensure_ascii=False,
            ),
        )
        for name, model in OWNED_TABLES:
            rows: Sequence[Any] = (
                await session.scalars(select(model).where(model.user_id == user.id))
            ).all()
            archive.writestr(
                f"data/{name}.json",
                json.dumps([_row(r) for r in rows], indent=2, ensure_ascii=False),
            )
        # The jobs themselves (shared catalog rows the user has in their list).
        jobs = (
            await session.scalars(
                select(Job)
                .join(UserJob, UserJob.job_id == Job.id)
                .where(UserJob.user_id == user.id)
            )
        ).all()
        archive.writestr(
            "data/jobs.json", json.dumps([_row(j) for j in jobs], indent=2, ensure_ascii=False)
        )
        for key in await storage.list_prefix(f"users/{user.id}/"):
            archive.writestr(f"files/{key.split('/', 2)[-1]}", await storage.read(key))
    return buffer.getvalue()


async def delete_account(
    session: AsyncSession,
    settings: Settings,
    storage: Storage,
    user: User,
    *,
    password: str,
    confirm_email: str,
) -> int:
    """Returns the number of stored files removed."""
    if confirm_email.strip().lower() != user.email.lower():
        raise ValidationAppError("Type your email address to confirm.", code="CONFIRM_MISMATCH")
    if not verify_password(password, user.hashed_password):
        raise ValidationAppError("The password is not correct.", code="WRONG_PASSWORD")
    if user.role is UserRole.ADMIN:
        admins = await session.scalar(
            select(func.count()).select_from(User).where(User.role == UserRole.ADMIN)
        )
        if (admins or 0) <= 1:
            raise ConflictError(
                "You are the only admin. Make another user admin before deleting your account.",
                code="LAST_ADMIN",
            )
    # Revoke Gmail at Google (best effort) before the tokens are deleted with the user.
    await GmailAccountService(session, user.id, settings).disconnect()
    removed = await storage.delete_prefix(f"users/{user.id}/")
    session.add(
        AuditLog(
            user_id=user.id,  # becomes NULL when the user row goes (ON DELETE SET NULL)
            actor_type=ActorType.USER,
            action="user.self_delete",
            entity_type="user",
            entity_id=user.id,
            data={"files_removed": removed},
        )
    )
    await session.flush()
    await session.delete(user)
    await session.commit()
    return removed

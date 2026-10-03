"""Application emails (Module 08): draft → approve → scheduled send through Gmail.

Safety rules, enforced here and in the database:
- only approved emails are sent; the application and email change in one transaction;
- one outbound email per (user, application, type): unique idempotency key;
- `queued → sending` is a single conditional UPDATE, so a retry or a second worker can
  never send twice; a message stuck in `sending` is reconciled by its Message-ID;
- do-not-contact, approved contact, daily cap, minimum gap (+ jitter), same-recipient
  cooldown and a connected Gmail are checked again right before sending.
"""

import random
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError, ValidationAppError
from app.domain.outreach import (
    IDEMPOTENCY_HEADER,
    Attachment,
    SendingDisabledError,
    SendRules,
    build_message,
    idempotency_key,
    next_slot,
)
from app.integrations.ai import AiClient
from app.integrations.gmail import GmailAuthError, GmailSendError, GmailUncertainError
from app.integrations.storage import Storage
from app.models.applications import Application
from app.models.documents import CoverLetter
from app.models.enums import (
    ApplicationChannel,
    ApplicationStatus,
    ContactApproval,
    ContactVerification,
    EmailDirection,
    EmailStatus,
    EmailType,
    JobSource,
    NotificationSeverity,
    ParseStatus,
    StatusChangeSource,
)
from app.models.jobs import Job
from app.models.outreach import Contact, Email, EmailAttachment
from app.models.resumes import ResumeVersion
from app.models.system import Task
from app.prompts import documents as document_prompts
from app.prompts import outreach as prompts
from app.prompts.outreach import EmailDraft
from app.prompts.resumes import ParsedResume
from app.repositories.applications import ApplicationRepository
from app.repositories.documents import CoverLetterRepository
from app.repositories.jobs import UserJobRepository
from app.repositories.outreach import (
    ContactRepository,
    DoNotContactRepository,
    EmailAttachmentRepository,
    EmailRepository,
    OutboxFilters,
    due_emails,
    stuck_sending,
)
from app.repositories.profiles import ProfileRepository, UserSettingsRepository
from app.repositories.resumes import ResumeVersionRepository
from app.repositories.tasks import TaskRepository
from app.services.ai import AiService
from app.services.analysis import effective_description
from app.services.applications import ApplicationService
from app.services.contacts import known_company
from app.services.cover_letters import body_of, problems
from app.services.documents import DocumentRejectedError, _hints
from app.services.gmail_account import GmailAccountService
from app.services.notifications import notify
from app.services.tasks import TaskDispatcher, TaskService

logger = structlog.get_logger("app.outreach")

EMAIL_ENTITY = "email"
EMAIL_WORDS = (80, 200)
# Drafting is possible from these application statuses (re-drafting replaces the draft).
DRAFTABLE = frozenset(
    {
        ApplicationStatus.READY_TO_APPLY,
        ApplicationStatus.WAITING_FOR_APPROVAL,
        ApplicationStatus.REJECTED_BY_USER,
        ApplicationStatus.FAILED,
    }
)
RECONCILE_AFTER = timedelta(minutes=5)
IMMEDIATE = timedelta(seconds=5)


# ---------- shared helpers ----------


# Titles and abbreviations that are not a first name ("Md Ehtesham" → "Ehtesham", seen live).
_NOT_FIRST_NAMES = frozenset({"md", "mohd", "mr", "mrs", "ms", "miss", "dr", "er", "sri", "shri"})


def _first_name(name: str | None) -> str | None:
    for word in (name or "").split():
        first = word.strip(",.")
        if first.lower() in _NOT_FIRST_NAMES:
            continue
        return first if first[:1].isalpha() and len(first) > 1 else None
    return None


def compose_body(paragraphs: list[str], *, contact_name: str | None, resume: ParsedResume) -> str:
    first = _first_name(contact_name)
    greeting = f"Dear {first}," if first else "Dear Hiring Team,"
    body = [" ".join(p.split()) for p in paragraphs if p.strip()]
    signature = "\n".join(
        line
        for line in ["Best regards,", resume.name or "", resume.phone or "", *resume.links]
        if line
    )
    return "\n\n".join([greeting, *body, signature])


def email_problems(
    body: str, *, resume_text: str, job: Job, job_text: str, lacking: list[str]
) -> list[str]:
    found = problems(
        body,
        resume_text=resume_text,
        job_text=job_text,
        company=known_company(job.company),
        title=job.title,
        lacking=lacking,
        word_range=EMAIL_WORDS,
        aim="120-180",
    )
    if "attach" not in body_of(body).lower():
        found.append("does not mention the attached resume")
    return found


def _resume_attachment_name(resume: ParsedResume, version: ResumeVersion) -> str:
    suffix = PurePath(version.file_name).suffix or ".pdf"
    name = (resume.name or "").strip()
    return f"{name} - Resume{suffix}" if name else f"Resume{suffix}"


async def _rules(
    session: AsyncSession, user_id: uuid.UUID, settings: Settings
) -> tuple[SendRules, int]:
    user_settings = await UserSettingsRepository(session, owner_id=user_id).get_or_create()
    profile = await ProfileRepository(session, owner_id=user_id).get_or_create()
    try:
        tz = ZoneInfo(profile.timezone)
    except Exception:  # unknown zone name: fall back to UTC
        tz = ZoneInfo("UTC")
    return (
        SendRules(
            daily_cap=user_settings.daily_send_cap,
            interval_seconds=user_settings.send_interval_seconds,
            window_start_hour=settings.send_window_start_hour,
            tz=tz,
        ),
        user_settings.recipient_cooldown_days,
    )


def _day_start(now: datetime, tz: ZoneInfo) -> datetime:
    local = now.astimezone(tz)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


# ---------- drafting (worker) ----------


@dataclass(frozen=True)
class DraftInputs:
    application: Application
    job: Job
    version: ResumeVersion
    letter: CoverLetter | None
    contact: Contact


async def draft_inputs(
    session: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID
) -> DraftInputs:
    application = await ApplicationRepository(session, owner_id=user_id).get(application_id)
    if application is None:
        raise NotFoundError("Application not found.")
    job = await session.get(Job, application.job_id)
    assert job is not None
    version = (
        await ResumeVersionRepository(session, owner_id=user_id).get(application.resume_version_id)
        if application.resume_version_id
        else None
    )
    if version is None or version.parse_status is not ParseStatus.PARSED or not version.parsed:
        raise ConflictError(
            "Choose a parsed resume for this application first.", code="RESUME_REQUIRED"
        )
    contact = (
        await ContactRepository(session, owner_id=user_id).get(application.contact_id)
        if application.contact_id
        else None
    )
    if contact is None:
        raise ConflictError("Choose who to send it to first.", code="CONTACT_REQUIRED")
    letter = (
        await CoverLetterRepository(session, owner_id=user_id).get(application.cover_letter_id)
        if application.cover_letter_id
        else None
    )
    return DraftInputs(application, job, version, letter, contact)


async def generate_draft(
    session: AsyncSession,
    *,
    ai: AiClient,
    settings: Settings,
    user_id: uuid.UUID,
    application_id: uuid.UUID,
) -> Email:
    inputs = await draft_inputs(session, user_id, application_id)
    account = await GmailAccountService(session, user_id, settings).connected()
    application, job, version, letter, contact = (
        inputs.application,
        inputs.job,
        inputs.version,
        inputs.letter,
        inputs.contact,
    )
    resume = ParsedResume.model_validate(version.parsed)
    user_job = await UserJobRepository(session, owner_id=user_id).for_job(job.id)
    job_text = effective_description(job, user_job)
    hints = await _hints(session, user_id, job, version)
    attachments = ["my resume"] + (["a cover letter"] if letter and letter.file_key else [])
    found_via = "your LinkedIn post" if job.source is JobSource.LINKEDIN_POST else "the job posting"
    messages = prompts.email_messages(
        resume.model_dump(),
        {
            "title": job.title,
            "company": known_company(job.company),
            "location": job.location,
            "description": job_text[:8000],
        },
        found_via=found_via,
        attachments=attachments,
        do_not_claim=hints.do_not_claim,
    )
    resume_text = (version.text_content or "") + " " + str(version.parsed or "")
    draft: tuple[str, str] | None = None
    found: list[str] = []
    model = ""
    for _ in range(2):  # one retry with the problems listed
        result = await AiService(session, ai).complete_json(
            user_id=user_id,
            task_type="application_email",
            prompt_version=prompts.EMAIL_VERSION,
            messages=messages,
            output=EmailDraft,
        )
        model = result.model
        body = compose_body(result.data.paragraphs, contact_name=contact.name, resume=resume)
        found = email_problems(
            body, resume_text=resume_text, job=job, job_text=job_text, lacking=hints.do_not_claim
        )
        if not found:
            draft = (" ".join(result.data.subject.split())[:200], body)
            break
        messages = [
            *messages,
            {"role": "assistant", "content": result.data.model_dump_json()},
            document_prompts.retry_message(found),
        ]
    if draft is None:
        raise DocumentRejectedError(
            "The email draft did not pass the checks (" + "; ".join(found[:3]) + ")."
        )

    emails = EmailRepository(session, owner_id=user_id)
    email = await emails.outbound_for(application.id)
    if email is not None and email.status not in (
        EmailStatus.DRAFT,
        EmailStatus.REJECTED,
        EmailStatus.FAILED,
    ):
        raise ConflictError(
            "This application's email is already approved or sent.", code="EMAIL_LOCKED"
        )
    if email is None:
        email = await emails.add(
            Email(
                application_id=application.id,
                direction=EmailDirection.OUTBOUND,
                email_type=EmailType.APPLICATION,
                idempotency_key=idempotency_key(user_id, application.id, EmailType.APPLICATION),
                from_address=account.account_email,
                to_address=contact.email,
                subject=draft[0],
                body_text=draft[1],
                status=EmailStatus.DRAFT,
            )
        )
    else:
        email.from_address = account.account_email
        email.to_address = contact.email
        email.subject, email.body_text = draft
        email.status = EmailStatus.DRAFT
        email.approved_at = email.scheduled_for = None
        email.error = email.message_id_header = None
    email.contact_id = contact.id
    email.model, email.prompt_version = model, prompts.EMAIL_VERSION
    await _attach(session, user_id, email, resume, version, letter, job)
    _to_waiting(session, user_id, application, "Email drafted")
    notify(
        session,
        user_id,
        type="email_drafted",
        title=f"Email ready for review: {job.title}",
        body="Review and approve it in the Outbox.",
        link="/outbox",
    )
    await session.commit()
    return email


async def _attach(
    session: AsyncSession,
    user_id: uuid.UUID,
    email: Email,
    resume: ParsedResume,
    version: ResumeVersion,
    letter: CoverLetter | None,
    job: Job,
) -> None:
    for old in await EmailAttachmentRepository(session, owner_id=user_id).for_email(email.id):
        await session.delete(old)
    repo = EmailAttachmentRepository(session, owner_id=user_id)
    await repo.add(
        EmailAttachment(
            email_id=email.id,
            file_key=version.file_key,
            file_name=_resume_attachment_name(resume, version),
            mime_type=version.mime_type,
            file_size=version.file_size,
            resume_version_id=version.id,
        )
    )
    if letter is not None and letter.file_key:
        await repo.add(
            EmailAttachment(
                email_id=email.id,
                file_key=letter.file_key,
                file_name=f"{resume.name + ' - ' if resume.name else ''}Cover Letter.pdf",
                mime_type="application/pdf",
                file_size=0,
                cover_letter_id=letter.id,
            )
        )


def _to_waiting(
    session: AsyncSession, user_id: uuid.UUID, application: Application, note: str
) -> None:
    apps = ApplicationService(session, user_id)
    if application.status is ApplicationStatus.REJECTED_BY_USER:
        apps.apply(
            application, ApplicationStatus.READY_TO_APPLY, note="Prepared again", outbox=True
        )
    if application.status is not ApplicationStatus.WAITING_FOR_APPROVAL:
        apps.apply(application, ApplicationStatus.WAITING_FOR_APPROVAL, note=note, outbox=True)


# ---------- sending (worker) ----------


@dataclass(frozen=True)
class SendOutcome:
    status: str  # sent | failed | rescheduled | skipped | uncertain
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "detail": self.detail}


class EmailSender:
    def __init__(
        self, session: AsyncSession, user_id: uuid.UUID, settings: Settings, storage: Storage
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.settings = settings
        self.storage = storage
        self.emails = EmailRepository(session, owner_id=user_id)
        self.apps = ApplicationService(session, user_id)

    async def _application(self, email: Email) -> Application:
        application = await ApplicationRepository(self.session, owner_id=self.user_id).get(
            email.application_id
        )
        assert application is not None
        return application

    async def _fail(self, email: Email, reason: str) -> SendOutcome:
        email.status = EmailStatus.FAILED
        email.error = reason
        application = await self._application(email)
        if application.status is ApplicationStatus.SENDING:
            self.apps.apply(
                application,
                ApplicationStatus.FAILED,
                note=reason,
                source=StatusChangeSource.SYSTEM,
            )
        job = await self.session.get(Job, application.job_id)
        notify(
            self.session,
            self.user_id,
            type="email_failed",
            title=f"Email not sent: {job.title if job else 'application'}",
            body=reason,
            link="/outbox",
            severity=NotificationSeverity.ERROR,
        )
        await self.session.commit()
        return SendOutcome("failed", reason)

    async def _checks(
        self, email: Email, rules: SendRules, cooldown_days: int, now: datetime
    ) -> str | None:
        """Pre-send checks (Module 08). A reason means: do not send."""
        if email.approved_at is None:
            return "The email was not approved."
        if await DoNotContactRepository(self.session, owner_id=self.user_id).blocks(
            email.to_address
        ):
            return f"{email.to_address} is on your do-not-contact list."
        contact = (
            await ContactRepository(self.session, owner_id=self.user_id).get(email.contact_id)
            if email.contact_id
            else None
        )
        if contact is None or contact.approval is not ContactApproval.APPROVED:
            return "The contact is no longer approved."
        if contact.verification is ContactVerification.INVALID:
            return "The address cannot receive email."
        if contact.email != email.to_address:
            return "The contact's address changed — draft the email again."
        if cooldown_days:
            last = await self.emails.last_sent_to(email.to_address, exclude=email.id)
            if last is not None and last > now - timedelta(days=cooldown_days):
                return (
                    f"You already emailed {email.to_address} on {last:%d %b %Y} "
                    f"(wait {cooldown_days} days between emails to one person)."
                )
        return None

    async def send(self, email_id: uuid.UUID) -> SendOutcome:
        now = datetime.now(UTC)
        email = await self.emails.get(email_id)
        if email is None or email.status is not EmailStatus.QUEUED:
            return SendOutcome("skipped", email.status.value if email else "missing")
        if email.scheduled_for and email.scheduled_for > now + IMMEDIATE:
            return SendOutcome("skipped", "not due yet")
        rules, cooldown_days = await _rules(self.session, self.user_id, self.settings)
        # Daily cap, counted again now (other emails may have gone out meanwhile).
        if await self.emails.sent_today_count(_day_start(now, rules.tz)) >= rules.daily_cap:
            try:
                email.scheduled_for = next_slot(
                    now,
                    await self.emails.taken_slots(_day_start(now, rules.tz)),
                    rules,
                    random.randint(0, self.settings.send_jitter_seconds),
                )
            except SendingDisabledError as exc:
                await self.session.rollback()
                return SendOutcome("skipped", str(exc))
            await self.session.commit()
            return SendOutcome("rescheduled", email.scheduled_for.isoformat())

        if not await self.emails.claim_for_sending(email.id, now + IMMEDIATE):
            await self.session.rollback()
            return SendOutcome("skipped", "already taken")
        await self.session.refresh(email)
        application = await self._application(email)
        self.apps.apply(
            application, ApplicationStatus.SENDING, note=None, source=StatusChangeSource.SYSTEM
        )
        await self.session.commit()

        reason = await self._checks(email, rules, cooldown_days, now)
        if reason:
            return await self._fail(email, reason)
        try:
            gmail, account = await GmailAccountService(
                self.session, self.user_id, self.settings
            ).api()
        except AppError as exc:
            return await self._fail(email, exc.message)
        if account.account_email != email.from_address:
            return await self._fail(
                email, f"Gmail is now connected as {account.account_email} — draft the email again."
            )

        attachments: list[Attachment] = []
        for item in await EmailAttachmentRepository(self.session, owner_id=self.user_id).for_email(
            email.id
        ):
            try:
                data = await self.storage.read(item.file_key)
            except AppError:
                return await self._fail(email, f"The attachment {item.file_name} is missing.")
            attachments.append(Attachment(item.file_name, item.mime_type, data))
        resume = await self._sender_name(email)
        mime, message_id = build_message(
            from_address=email.from_address,
            from_name=resume,
            to_address=email.to_address,
            subject=email.subject,
            body=email.body_text,
            attachments=attachments,
            idempotency=email.idempotency_key or "",
        )
        email.message_id_header = message_id  # saved first: reconciliation searches for it
        await self.session.commit()

        try:
            sent = await gmail.send(mime)
        except GmailUncertainError:
            logger.warning("outreach.send_uncertain", email_id=str(email.id))
            return SendOutcome("uncertain", "Gmail did not answer; checking again shortly.")
        except GmailAuthError as exc:
            await GmailAccountService(self.session, self.user_id, self.settings).mark_revoked()
            return await self._fail(email, exc.message)
        except GmailSendError as exc:
            return await self._fail(email, exc.message)
        await self._mark_sent(email, sent.message_id, sent.thread_id)
        return SendOutcome("sent", sent.message_id)

    async def _sender_name(self, email: Email) -> str | None:
        application = await self._application(email)
        if application.resume_version_id:
            version = await ResumeVersionRepository(self.session, owner_id=self.user_id).get(
                application.resume_version_id
            )
            if version and version.parsed:
                return ParsedResume.model_validate(version.parsed).name or None
        return None

    async def _mark_sent(self, email: Email, message_id: str, thread_id: str) -> None:
        now = datetime.now(UTC)
        email.status = EmailStatus.SENT
        email.sent_at = now
        email.gmail_message_id, email.gmail_thread_id = message_id, thread_id
        email.error = None
        application = await self._application(email)
        if application.status is ApplicationStatus.SENDING:
            self.apps.apply(
                application,
                ApplicationStatus.APPLIED,
                note=f"Email sent to {email.to_address}",
                source=StatusChangeSource.SYSTEM,
                evidence={"gmail_message_id": message_id, "gmail_thread_id": thread_id},
            )
        job = await self.session.get(Job, application.job_id)
        company = known_company(job.company) if job else ""
        notify(
            self.session,
            self.user_id,
            type="email_sent",
            title=f"Applied{' to ' + company if company else ''} — {job.title if job else ''}",
            body=f"Sent from Gmail to {email.to_address}.",
            link=f"/applications/{application.id}",
            severity=NotificationSeverity.SUCCESS,
        )
        await self.session.commit()
        logger.info("outreach.sent", email_id=str(email.id))

    async def reconcile(self, email: Email) -> SendOutcome:
        """An email stuck in `sending`: did Gmail get it? Look for our idempotency header in
        Sent mail (Gmail rewrites the Message-ID, so that cannot be searched)."""
        if not email.message_id_header:  # set right before the Gmail call
            return await self._fail(email, "Sending was interrupted before Gmail was called.")
        try:
            gmail, _ = await GmailAccountService(self.session, self.user_id, self.settings).api()
            found = await gmail.find_sent(
                to_address=email.to_address,
                header=IDEMPOTENCY_HEADER,
                value=email.idempotency_key or "",
                after=(email.approved_at or email.updated_at) - timedelta(hours=1),
            )
        except AppError as exc:
            logger.warning(
                "outreach.reconcile_unavailable", email_id=str(email.id), error=exc.message
            )
            return SendOutcome("uncertain", exc.message)
        if found is not None:
            await self._mark_sent(email, found.message_id, found.thread_id)
            return SendOutcome("sent", "found in Gmail")
        return await self._fail(email, "Gmail has no record of this email — it was not sent.")


async def dispatch_outbox(
    session: AsyncSession,
    settings: Settings,
    dispatcher: TaskDispatcher,
    storage: Storage,
    now: datetime,
) -> dict[str, int]:
    """Beat, every minute: start sends that are due; repair emails stuck in `sending`."""
    started = 0
    for email in await due_emails(session, now):
        active = await TaskRepository(session, owner_id=email.user_id).active_for(
            EMAIL_ENTITY, email.id
        )
        if any(task.type == "email_send" for task in active):
            continue
        await TaskService(session, email.user_id, dispatcher).create(
            "email_send", {"email_id": str(email.id)}, entity_type=EMAIL_ENTITY, entity_id=email.id
        )
        started += 1
    repaired = 0
    for email in await stuck_sending(session, now - RECONCILE_AFTER):
        outcome = await EmailSender(session, email.user_id, settings, storage).reconcile(email)
        repaired += outcome.status != "uncertain"
    return {"started": started, "reconciled": repaired}


# ---------- API side ----------


@dataclass(frozen=True)
class EmailView:
    email: Email
    application: Application
    job: Job
    contact: Contact | None
    attachments: Sequence[EmailAttachment]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OutboxSummary:
    counts: dict[str, int]
    sent_today: int
    daily_cap: int
    interval_seconds: int
    next_slot: datetime | None
    gmail_connected: bool
    gmail_email: str | None


@dataclass(frozen=True)
class BatchResult:
    approved: list[uuid.UUID]
    errors: dict[str, str]


class EmailService:
    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        settings: Settings,
        dispatcher: TaskDispatcher,
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.settings = settings
        self.dispatcher = dispatcher
        self.emails = EmailRepository(session, owner_id=user_id)
        self.attachments = EmailAttachmentRepository(session, owner_id=user_id)
        self.applications = ApplicationRepository(session, owner_id=user_id)
        self.apps = ApplicationService(session, user_id)
        self.contacts = ContactRepository(session, owner_id=user_id)

    async def _email(self, email_id: uuid.UUID, *, for_update: bool = False) -> Email:
        email = (
            await self.emails.get_for_update(email_id)
            if for_update
            else await self.emails.get(email_id)
        )
        if email is None or email.direction is not EmailDirection.OUTBOUND:
            raise NotFoundError("Email not found.")
        return email

    async def _application(self, application_id: uuid.UUID) -> Application:
        application = await self.applications.get(application_id)
        if application is None:
            raise NotFoundError("Application not found.")
        return application

    async def view(self, email: Email) -> EmailView:
        application = await self._application(email.application_id)
        job = await self.session.get(Job, application.job_id)
        assert job is not None
        contact = await self.contacts.get(email.contact_id) if email.contact_id else None
        warnings: list[str] = []
        if email.status is EmailStatus.DRAFT:
            warnings = await self._warnings(email, application, job, contact)
        return EmailView(
            email, application, job, contact, await self.attachments.for_email(email.id), warnings
        )

    async def _warnings(
        self, email: Email, application: Application, job: Job, contact: Contact | None
    ) -> list[str]:
        found: list[str] = []
        if contact is None:
            found.append("No recipient — choose a contact.")
        else:
            if contact.approval is not ContactApproval.APPROVED:
                found.append(f"{contact.email} is not approved yet.")
            if contact.verification is ContactVerification.INVALID:
                found.append(f"{contact.email} cannot receive email.")
            if await DoNotContactRepository(self.session, owner_id=self.user_id).blocks(
                contact.email
            ):
                found.append(f"{contact.email} is on your do-not-contact list.")
        version = (
            await ResumeVersionRepository(self.session, owner_id=self.user_id).get(
                application.resume_version_id
            )
            if application.resume_version_id
            else None
        )
        if version is not None and version.parsed:
            user_job = await UserJobRepository(self.session, owner_id=self.user_id).for_job(job.id)
            hints = await _hints(self.session, self.user_id, job, version)
            found += email_problems(
                email.body_text,
                resume_text=(version.text_content or "") + " " + str(version.parsed),
                job=job,
                job_text=effective_description(job, user_job),
                lacking=hints.do_not_claim,
            )
        return found

    # ---------- draft ----------

    async def start_draft(self, application_id: uuid.UUID, contact_id: uuid.UUID | None) -> Task:
        application = await self._application(application_id)
        if application.channel is not ApplicationChannel.EMAIL:
            raise ConflictError(
                "Switch the application to 'Email' to send it from Gmail.", code="NOT_EMAIL_CHANNEL"
            )
        if application.status not in DRAFTABLE:
            raise ConflictError(
                "This application's email is already approved or sent.", code="EMAIL_LOCKED"
            )
        await GmailAccountService(self.session, self.user_id, self.settings).connected()
        if contact_id is not None:
            contact = await self.contacts.get(contact_id)
            if contact is None:
                raise NotFoundError("Contact not found.")
            application.contact_id = contact.id
        contact = (
            await self.contacts.get(application.contact_id) if application.contact_id else None
        )
        if contact is None:
            raise ValidationAppError("Choose who to send it to.", code="CONTACT_REQUIRED")
        if contact.approval is not ContactApproval.APPROVED:
            raise ConflictError("Approve the contact first.", code="CONTACT_NOT_APPROVED")
        if await DoNotContactRepository(self.session, owner_id=self.user_id).blocks(contact.email):
            raise ConflictError(
                "That address is on your do-not-contact list.", code="DO_NOT_CONTACT"
            )
        await draft_inputs(self.session, self.user_id, application.id)  # resume present?
        await self.session.commit()
        running = await TaskRepository(self.session, owner_id=self.user_id).active_for(
            "application", application.id
        )
        for task in running:
            if task.type == "email_draft":
                return task
        return await TaskService(self.session, self.user_id, self.dispatcher).create(
            "email_draft",
            {"application_id": str(application.id)},
            entity_type="application",
            entity_id=application.id,
        )

    async def for_application(self, application_id: uuid.UUID) -> EmailView | None:
        await self._application(application_id)
        email = await self.emails.outbound_for(application_id)
        return await self.view(email) if email else None

    async def edit(self, email_id: uuid.UUID, changes: dict[str, Any]) -> Email:
        email = await self._email(email_id, for_update=True)
        if email.status is not EmailStatus.DRAFT:
            raise ConflictError("Only drafts can be edited.", code="EMAIL_LOCKED")
        if changes.get("subject") is not None:
            subject = " ".join(str(changes["subject"]).split())
            if not subject:
                raise ValidationAppError("The subject cannot be empty.")
            email.subject = subject
        if changes.get("body_text") is not None:
            body = str(changes["body_text"]).replace("\r\n", "\n").strip()
            if len(body) < 20:
                raise ValidationAppError("The email is too short.")
            email.body_text = body
        if changes.get("contact_id") is not None:
            contact = await self.contacts.get(changes["contact_id"])
            if contact is None:
                raise NotFoundError("Contact not found.")
            email.contact_id = contact.id
            email.to_address = contact.email
            application = await self._application(email.application_id)
            application.contact_id = contact.id
        await self.session.commit()
        await self.session.refresh(email)
        return email

    # ---------- approve / reject / cancel / retry ----------

    async def approve(self, email_id: uuid.UUID) -> Email:
        email = await self._email(email_id, for_update=True)
        if email.status in (EmailStatus.QUEUED, EmailStatus.SENDING, EmailStatus.SENT):
            return email  # approving twice changes nothing (and never sends twice)
        if email.status is not EmailStatus.DRAFT:
            raise ConflictError("Only drafts can be approved.", code="EMAIL_LOCKED")
        application = await self._application(email.application_id)
        account = await GmailAccountService(self.session, self.user_id, self.settings).connected()
        if account.account_email != email.from_address:
            raise ConflictError(
                f"Gmail is now connected as {account.account_email} — draft the email again.",
                code="GMAIL_ACCOUNT_CHANGED",
            )
        contact = await self.contacts.get(email.contact_id) if email.contact_id else None
        if contact is None or contact.email != email.to_address:
            raise ConflictError("Choose the recipient again.", code="CONTACT_REQUIRED")
        if contact.approval is not ContactApproval.APPROVED:
            raise ConflictError(f"Approve {contact.email} first.", code="CONTACT_NOT_APPROVED")
        if contact.verification is ContactVerification.INVALID:
            raise ConflictError(f"{contact.email} cannot receive email.", code="CONTACT_INVALID")
        if await DoNotContactRepository(self.session, owner_id=self.user_id).blocks(contact.email):
            raise ConflictError(
                f"{contact.email} is on your do-not-contact list.", code="DO_NOT_CONTACT"
            )
        now = datetime.now(UTC)
        rules, cooldown_days = await _rules(self.session, self.user_id, self.settings)
        if cooldown_days:
            last = await self.emails.last_sent_to(email.to_address, exclude=email.id)
            if last is not None and last > now - timedelta(days=cooldown_days):
                raise ConflictError(
                    f"You emailed {email.to_address} on {last:%d %b %Y}. Wait {cooldown_days} days "
                    "between emails to one person.",
                    code="RECIPIENT_COOLDOWN",
                )
        try:
            slot = next_slot(
                now,
                await self.emails.taken_slots(_day_start(now, rules.tz)),
                rules,
                random.randint(0, self.settings.send_jitter_seconds),
            )
        except SendingDisabledError as exc:
            raise ConflictError(
                "Sending is turned off: set a daily send limit above 0 in Settings.",
                code="SENDING_DISABLED",
            ) from exc
        email.status = EmailStatus.QUEUED
        email.approved_at = now
        email.scheduled_for = slot
        email.error = None
        self.apps.apply(
            application,
            ApplicationStatus.APPROVED,
            note=f"Email to {email.to_address} approved",
            outbox=True,
        )
        await self.session.commit()
        if slot <= now + IMMEDIATE:
            await TaskService(self.session, self.user_id, self.dispatcher).create(
                "email_send",
                {"email_id": str(email.id)},
                entity_type=EMAIL_ENTITY,
                entity_id=email.id,
            )
        await self.session.refresh(email)
        return email

    async def approve_batch(self, email_ids: Sequence[uuid.UUID]) -> BatchResult:
        approved: list[uuid.UUID] = []
        errors: dict[str, str] = {}
        for email_id in dict.fromkeys(email_ids):  # each once, in the given order
            try:
                await self.approve(email_id)
                approved.append(email_id)
            except AppError as exc:
                await self.session.rollback()
                errors[str(email_id)] = exc.message
        return BatchResult(approved, errors)

    async def reject(self, email_id: uuid.UUID) -> Email:
        email = await self._email(email_id, for_update=True)
        if email.status is EmailStatus.REJECTED:
            return email
        if email.status is not EmailStatus.DRAFT:
            raise ConflictError("Only drafts can be rejected.", code="EMAIL_LOCKED")
        email.status = EmailStatus.REJECTED
        application = await self._application(email.application_id)
        if application.status is ApplicationStatus.WAITING_FOR_APPROVAL:
            self.apps.apply(
                application, ApplicationStatus.REJECTED_BY_USER, note="Email rejected", outbox=True
            )
        await self.session.commit()
        await self.session.refresh(email)
        return email

    async def cancel(self, email_id: uuid.UUID) -> Email:
        """Take an approved email out of the queue (back to draft) before it is sent."""
        email = await self._email(email_id, for_update=True)
        if email.status is not EmailStatus.QUEUED:
            raise ConflictError("Only scheduled emails can be cancelled.", code="EMAIL_LOCKED")
        email.status = EmailStatus.DRAFT
        email.approved_at = email.scheduled_for = None
        application = await self._application(email.application_id)
        if application.status is ApplicationStatus.APPROVED:
            self.apps.apply(
                application,
                ApplicationStatus.WAITING_FOR_APPROVAL,
                note="Sending cancelled",
                outbox=True,
            )
        await self.session.commit()
        await self.session.refresh(email)
        return email

    async def retry(self, email_id: uuid.UUID) -> Email:
        """A failed email goes back to draft — it must be approved again."""
        email = await self._email(email_id, for_update=True)
        if email.status is not EmailStatus.FAILED:
            raise ConflictError("Only failed emails can be retried.", code="EMAIL_LOCKED")
        email.status = EmailStatus.DRAFT
        email.approved_at = email.scheduled_for = None
        email.message_id_header = None
        application = await self._application(email.application_id)
        if application.status is ApplicationStatus.FAILED:
            self.apps.apply(
                application,
                ApplicationStatus.WAITING_FOR_APPROVAL,
                note="Back to draft after a failed send",
                outbox=True,
            )
        await self.session.commit()
        await self.session.refresh(email)
        return email

    # ---------- outbox ----------

    async def outbox(
        self, statuses: tuple[EmailStatus, ...], *, page: int, page_size: int
    ) -> tuple[list[EmailView], int]:
        rows, total = await self.emails.outbox(
            OutboxFilters(statuses=statuses), limit=page_size, offset=(page - 1) * page_size
        )
        attachments = await self.attachments.for_emails([e.id for e, _, _ in rows])
        contacts = {
            c.id: c
            for c in [await self.contacts.get(e.contact_id) for e, _, _ in rows if e.contact_id]
            if c is not None
        }
        return [
            EmailView(
                e,
                a,
                j,
                contacts.get(e.contact_id) if e.contact_id else None,
                attachments.get(e.id, []),
            )
            for e, a, j in rows
        ], total

    async def summary(self) -> OutboxSummary:
        now = datetime.now(UTC)
        rules, _ = await _rules(self.session, self.user_id, self.settings)
        start = _day_start(now, rules.tz)
        try:
            slot: datetime | None = next_slot(now, await self.emails.taken_slots(start), rules)
        except SendingDisabledError:
            slot = None
        status = await GmailAccountService(self.session, self.user_id, self.settings).status()
        return OutboxSummary(
            counts=await self.emails.status_counts(),
            sent_today=await self.emails.sent_today_count(start),
            daily_cap=rules.daily_cap,
            interval_seconds=rules.interval_seconds,
            next_slot=slot,
            gmail_connected=status.connected,
            gmail_email=status.account_email,
        )

    async def detail(self, email_id: uuid.UUID) -> EmailView:
        return await self.view(await self._email(email_id))

"""Reply tracking (Module 09): read new mail in our threads, classify, update statuses.

Runs every 5 minutes (Beat). Gmail's history API returns only what changed since the last
poll, so a quiet mailbox costs one call. Rules:
- bounce → email bounced, contact invalid, application failed;
- AI category with confidence ≥ 0.80 → status change (source = email_reply);
  below → the user is asked to confirm in the application timeline;
- "do not contact me" → the sender goes on the do-not-contact list;
- any reply cancels a pending follow-up.
Also here: follow-up drafts after `follow_up_days`, `no_response` after `no_response_days`.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, LimitExceededError, NotFoundError
from app.domain.outreach import (
    CONFIDENCE_AUTO,
    IDEMPOTENCY_HEADER,
    asks_not_to_be_contacted,
    idempotency_key,
    is_bounce,
    reply_subject,
)
from app.domain.state_machine import TransitionError, check
from app.integrations.ai import AiClient
from app.integrations.gmail import (
    READ_SCOPE,
    GmailApi,
    GmailMessage,
    HistoryExpiredError,
    MessageRef,
)
from app.models.applications import Application
from app.models.enums import (
    ApplicationChannel,
    ApplicationStatus,
    ContactApproval,
    ContactVerification,
    DncSource,
    EmailDirection,
    EmailStatus,
    EmailType,
    NotificationSeverity,
    OAuthStatus,
    ReplyCategory,
    StatusChangeSource,
)
from app.models.jobs import Job
from app.models.outreach import DoNotContact, Email, OAuthAccount, ReplyClassification
from app.prompts import replies as prompts
from app.prompts.replies import FollowUpDraft, ReplyReading
from app.prompts.resumes import ParsedResume
from app.repositories.applications import ApplicationRepository
from app.repositories.outreach import (
    ContactRepository,
    DoNotContactRepository,
    EmailRepository,
)
from app.repositories.profiles import UserSettingsRepository
from app.repositories.resumes import ResumeVersionRepository
from app.services.ai import AiService
from app.services.applications import ApplicationService
from app.services.contacts import known_company
from app.services.gmail_account import GmailAccountService
from app.services.notifications import notify

logger = structlog.get_logger("app.replies")

TRACK_DAYS = 120  # threads older than this are no longer watched
FOLLOW_UPS_PER_POLL = 5

TARGETS: dict[ReplyCategory, ApplicationStatus | None] = {
    ReplyCategory.INTERVIEW_INVITE: ApplicationStatus.INTERVIEW,
    ReplyCategory.INFO_REQUEST: ApplicationStatus.RESPONDED,
    ReplyCategory.REJECTION: ApplicationStatus.REJECTED,
    ReplyCategory.OFFER: ApplicationStatus.OFFER,
    ReplyCategory.OTHER: ApplicationStatus.RESPONDED,
    ReplyCategory.AUTO_REPLY: None,
}
LABELS = {
    ReplyCategory.INTERVIEW_INVITE: "an interview invite",
    ReplyCategory.INFO_REQUEST: "a request for information",
    ReplyCategory.REJECTION: "a rejection",
    ReplyCategory.OFFER: "an offer",
    ReplyCategory.OTHER: "a reply",
    ReplyCategory.AUTO_REPLY: "an automatic reply",
}


@dataclass
class PollResult:
    checked: bool = False
    new_messages: int = 0
    replies: int = 0
    bounces: int = 0
    status_changes: int = 0
    to_confirm: int = 0
    follow_ups: int = 0
    no_response: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _allowed(application: Application, target: ApplicationStatus) -> bool:
    try:
        check(
            application.status,
            target,
            channel=application.channel,
            source=StatusChangeSource.EMAIL_REPLY,
        )
    except TransitionError:
        return False
    return True


class ReplyTracker:
    def __init__(
        self, session: AsyncSession, user_id: uuid.UUID, settings: Settings, ai: AiClient
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.settings = settings
        self.ai = ai
        self.emails = EmailRepository(session, owner_id=user_id)
        self.apps = ApplicationService(session, user_id)
        self.applications = ApplicationRepository(session, owner_id=user_id)

    # ---------- reading ----------

    async def _new_refs(
        self, gmail: GmailApi, account: OAuthAccount, tracked: dict[str, Email]
    ) -> list[MessageRef]:
        if account.gmail_history_id:
            try:
                refs, newest = await gmail.history(account.gmail_history_id)
                account.gmail_history_id = newest
                return refs
            except HistoryExpiredError:
                logger.info("replies.history_expired", user_id=str(self.user_id))
        # First poll, or Gmail forgot our point: read the tracked threads once.
        _, newest = await gmail.profile()
        refs = []
        for thread_id in tracked:
            refs += await gmail.thread_refs(thread_id)
        account.gmail_history_id = newest
        return refs

    def _is_ours(self, message: GmailMessage, account: OAuthAccount) -> bool:
        """Mail we sent (application, follow-up) or the user's own reply to someone else."""
        if IDEMPOTENCY_HEADER.lower() in message.headers:
            return True
        own = message.from_address == account.account_email.lower()
        # From the user to the user = a self-test reply: treat it like a recruiter's answer.
        return own and message.to_address != account.account_email.lower()

    async def poll(self) -> PollResult:
        result = PollResult()
        account = await GmailAccountService(self.session, self.user_id, self.settings).connected()
        if READ_SCOPE not in account.scopes:
            result.errors.append("Gmail read access was not granted — reconnect Gmail.")
            return result
        gmail, account = await GmailAccountService(self.session, self.user_id, self.settings).api()
        tracked = await self.emails.tracked_threads(datetime.now(UTC) - timedelta(days=TRACK_DAYS))
        refs = await self._new_refs(gmail, account, tracked)
        account.last_synced_at = datetime.now(UTC)
        await self.session.commit()
        result.checked = True
        for ref in refs:
            original = tracked.get(ref.thread_id)
            if original is None or "DRAFT" in ref.label_ids:
                continue
            if await self.emails.by_gmail_id(ref.message_id):
                continue  # already stored (or one of ours)
            message = await gmail.message(ref.message_id)
            if self._is_ours(message, account):
                continue
            result.new_messages += 1
            try:
                await self.handle(original, message, result)
            except AppError as exc:
                await self.session.rollback()
                result.errors.append(exc.message)
                logger.warning("replies.handle_failed", error=exc.message)
        await self.follow_ups(result)
        await self.no_response(result)
        return result

    # ---------- one inbound message ----------

    async def handle(self, original: Email, message: GmailMessage, result: PollResult) -> Email:
        application = await self.applications.get(original.application_id)
        if application is None:
            raise NotFoundError("Application not found.")
        job = await self.session.get(Job, application.job_id)
        bounce = is_bounce(message.from_address, message.subject)
        inbound = await self.emails.add(
            Email(
                application_id=application.id,
                contact_id=original.contact_id,
                direction=EmailDirection.INBOUND,
                email_type=EmailType.REPLY,
                in_reply_to_id=original.id,
                from_address=message.from_address or "unknown@unknown",
                to_address=message.to_address or original.from_address,
                subject=message.subject or "(no subject)",
                body_text=message.text or "(empty)",
                status=EmailStatus.BOUNCED if bounce else EmailStatus.RECEIVED,
                received_at=message.received_at or datetime.now(UTC),
                gmail_message_id=message.message_id,
                gmail_thread_id=message.thread_id,
                rfc822_message_id=message.rfc822_message_id,
            )
        )
        await self._cancel_follow_ups(application, "They replied — follow-up not needed.")
        title = job.title if job else "your application"
        if bounce:
            result.bounces += 1
            await self._bounce(original, application, title)
            await self.session.commit()
            return inbound

        result.replies += 1
        if asks_not_to_be_contacted(message.text):
            await self._do_not_contact(message.from_address)
        try:
            reading = await AiService(self.session, self.ai).complete_json(
                user_id=self.user_id,
                task_type="reply_classify",
                prompt_version=prompts.CLASSIFY_VERSION,
                messages=prompts.classify_messages(
                    job_title=title,
                    company=known_company(job.company) if job else "",
                    sent_text=original.body_text,
                    reply_from=message.from_name or message.from_address,
                    reply_text=message.text,
                ),
                output=ReplyReading,
            )
        except LimitExceededError as exc:
            notify(
                self.session,
                self.user_id,
                type="reply_received",
                title=f"New reply: {title}",
                body=f"Not classified ({exc.message}). Open the application to read it.",
                link=f"/applications/{application.id}",
                severity=NotificationSeverity.WARNING,
            )
            await self.session.commit()
            return inbound
        data: ReplyReading = reading.data
        category = ReplyCategory(data.category)
        confidence = Decimal(str(round(min(1.0, max(0.0, data.confidence)), 2)))
        classification = ReplyClassification(
            user_id=self.user_id,
            email_id=inbound.id,
            category=category,
            confidence=confidence,
            summary=data.summary.strip()[:500] or "Reply received.",
            suggested_action=data.suggested_action.strip()[:300] or None,
            model=reading.model,
            prompt_version=prompts.CLASSIFY_VERSION,
        )
        self.session.add(classification)
        target = TARGETS[category]
        label = LABELS[category]
        if target is None or not _allowed(application, target):
            notify(
                self.session,
                self.user_id,
                type="reply_received",
                title=f"{label.capitalize()} — {title}",
                body=classification.summary,
                link=f"/applications/{application.id}",
            )
        elif float(confidence) >= CONFIDENCE_AUTO:
            self.apps.apply(
                application,
                target,
                note=classification.summary,
                source=StatusChangeSource.EMAIL_REPLY,
                evidence={
                    "email_id": str(inbound.id),
                    "category": category.value,
                    "confidence": float(confidence),
                },
            )
            if classification.suggested_action:
                application.next_action = classification.suggested_action
            classification.applied_transition = True
            result.status_changes += 1
            notify(
                self.session,
                self.user_id,
                type="reply_status",
                title=f"{label.capitalize()} — {title}",
                body=f"Status set to {target.value.replace('_', ' ')}. {classification.summary}",
                link=f"/applications/{application.id}",
                severity=NotificationSeverity.SUCCESS,
            )
        else:
            result.to_confirm += 1
            notify(
                self.session,
                self.user_id,
                type="reply_confirm",
                title=f"Confirm: is this {label}? — {title}",
                body=classification.summary,
                link=f"/applications/{application.id}",
                severity=NotificationSeverity.WARNING,
            )
        await self.session.commit()
        return inbound

    async def _bounce(self, original: Email, application: Application, title: str) -> None:
        original.status = EmailStatus.BOUNCED
        original.error = "The email bounced (address not reachable)."
        if original.contact_id:
            contact = await ContactRepository(self.session, owner_id=self.user_id).get(
                original.contact_id
            )
            if contact is not None:
                contact.verification = ContactVerification.INVALID
                contact.verified_at = datetime.now(UTC)
                if contact.approval is ContactApproval.APPROVED:
                    contact.approval = ContactApproval.PENDING  # invalid can't stay approved
                    contact.approved_at = None
        if _allowed_system(application, ApplicationStatus.FAILED):
            self.apps.apply(
                application,
                ApplicationStatus.FAILED,
                note=f"Email to {original.to_address} bounced",
                source=StatusChangeSource.SYSTEM,
            )
        notify(
            self.session,
            self.user_id,
            type="email_bounced",
            title=f"Email bounced — {title}",
            body=f"{original.to_address} cannot receive email. Choose another contact.",
            link=f"/applications/{application.id}",
            severity=NotificationSeverity.ERROR,
        )

    async def _do_not_contact(self, address: str) -> None:
        repo = DoNotContactRepository(self.session, owner_id=self.user_id)
        if await repo.find(email=address.lower(), domain=None) is None:
            await repo.add(
                DoNotContact(
                    email=address.lower(),
                    reason="Asked not to be contacted",
                    source=DncSource.REPLY,
                )
            )
            notify(
                self.session,
                self.user_id,
                type="do_not_contact",
                title=f"{address} asked not to be contacted",
                body="Added to your do-not-contact list.",
                link="/contacts",
            )

    async def _cancel_follow_ups(self, application: Application, reason: str) -> None:
        rows = await self.session.scalars(
            select(Email).where(
                Email.user_id == self.user_id,
                Email.application_id == application.id,
                Email.direction == EmailDirection.OUTBOUND,
                Email.email_type != EmailType.APPLICATION,
                Email.status.in_((EmailStatus.DRAFT, EmailStatus.QUEUED)),
            )
        )
        for email in rows.all():
            email.status = EmailStatus.REJECTED
            email.error = reason

    # ---------- user confirmation ----------

    async def confirm(self, classification_id: uuid.UUID, accept: bool) -> ReplyClassification:
        classification = await self.session.scalar(
            select(ReplyClassification).where(
                ReplyClassification.id == classification_id,
                ReplyClassification.user_id == self.user_id,
            )
        )
        if classification is None:
            raise NotFoundError("Reply not found.")
        if classification.applied_transition or classification.user_confirmed is not None:
            return classification
        inbound = await self.emails.get(classification.email_id)
        assert inbound is not None
        application = await self.applications.get(inbound.application_id)
        assert application is not None
        target = TARGETS[classification.category]
        if accept:
            if target is None or not _allowed(application, target):
                raise ConflictError(
                    "The application has moved on — this status no longer applies.",
                    code="INVALID_TRANSITION",
                )
            self.apps.apply(
                application,
                target,
                note=f"Confirmed by you: {classification.summary}",
                source=StatusChangeSource.EMAIL_REPLY,
                evidence={"email_id": str(inbound.id), "category": classification.category.value},
            )
            if classification.suggested_action:
                application.next_action = classification.suggested_action
            classification.applied_transition = True
        classification.user_confirmed = accept
        await self.session.commit()
        return classification

    # ---------- follow-ups and no-response ----------

    async def _applied_email_applications(self) -> Sequence[tuple[Application, Email]]:
        rows = await self.session.execute(
            select(Application, Email)
            .join(Email, Email.application_id == Application.id)
            .where(
                Application.user_id == self.user_id,
                Application.channel == ApplicationChannel.EMAIL,
                Application.status == ApplicationStatus.APPLIED,
                Email.direction == EmailDirection.OUTBOUND,
                Email.email_type == EmailType.APPLICATION,
                Email.status == EmailStatus.SENT,
            )
        )
        return [(a, e) for a, e in rows.all()]

    async def follow_ups(self, result: PollResult) -> None:
        user_settings = await UserSettingsRepository(
            self.session, owner_id=self.user_id
        ).get_or_create()
        days = user_settings.follow_up_days
        if days <= 0:
            return
        due = datetime.now(UTC) - timedelta(days=days)
        made = 0
        for application, original in await self._applied_email_applications():
            if made >= FOLLOW_UPS_PER_POLL:
                break
            if original.sent_at is None or original.sent_at > due:
                continue
            if await self.emails.outbound_for(application.id, EmailType.FOLLOW_UP_1):
                continue  # one follow-up at most
            if await self.emails.has_reply(application.id):
                continue
            try:
                await self.draft_follow_up(application, original, days)
            except AppError as exc:
                await self.session.rollback()
                result.errors.append(exc.message)
                if isinstance(exc, LimitExceededError):
                    break
                continue
            made += 1
        result.follow_ups = made

    async def draft_follow_up(self, application: Application, original: Email, days: int) -> Email:
        job = await self.session.get(Job, application.job_id)
        assert job is not None
        reading = await AiService(self.session, self.ai).complete_json(
            user_id=self.user_id,
            task_type="follow_up",
            prompt_version=prompts.FOLLOW_UP_VERSION,
            messages=prompts.follow_up_messages(
                job_title=job.title,
                company=known_company(job.company),
                sent_text=original.body_text,
                days=days,
            ),
            output=FollowUpDraft,
        )
        name = None
        if application.resume_version_id:
            version = await ResumeVersionRepository(self.session, owner_id=self.user_id).get(
                application.resume_version_id
            )
            if version and version.parsed:
                name = ParsedResume.model_validate(version.parsed).name
        greeting = original.body_text.split("\n", 1)[0].strip()  # same greeting as before
        body = "\n\n".join(
            [
                greeting if greeting.lower().startswith("dear") else "Dear Hiring Team,",
                *[" ".join(p.split()) for p in reading.data.paragraphs if p.strip()],
                "\n".join(line for line in ["Best regards,", name or ""] if line),
            ]
        )
        email = await self.emails.add(
            Email(
                application_id=application.id,
                contact_id=original.contact_id,
                direction=EmailDirection.OUTBOUND,
                email_type=EmailType.FOLLOW_UP_1,
                idempotency_key=idempotency_key(
                    self.user_id, application.id, EmailType.FOLLOW_UP_1
                ),
                in_reply_to_id=original.id,
                from_address=original.from_address,
                to_address=original.to_address,
                subject=reply_subject(original.subject),
                body_text=body,
                status=EmailStatus.DRAFT,
                model=reading.model,
                prompt_version=prompts.FOLLOW_UP_VERSION,
            )
        )
        notify(
            self.session,
            self.user_id,
            type="follow_up_drafted",
            title=f"Follow-up ready for approval — {job.title}",
            body=f"No answer from {original.to_address} after {days} days.",
            link="/outbox",
        )
        await self.session.commit()
        return email

    async def no_response(self, result: PollResult) -> None:
        user_settings = await UserSettingsRepository(
            self.session, owner_id=self.user_id
        ).get_or_create()
        due = datetime.now(UTC) - timedelta(days=user_settings.no_response_days)
        for application, original in await self._applied_email_applications():
            last_sent = original.sent_at
            follow_up = await self.emails.outbound_for(application.id, EmailType.FOLLOW_UP_1)
            if follow_up is not None and follow_up.sent_at:
                last_sent = max(last_sent or follow_up.sent_at, follow_up.sent_at)
            if last_sent is None or last_sent > due or await self.emails.has_reply(application.id):
                continue
            self.apps.apply(
                application,
                ApplicationStatus.NO_RESPONSE,
                note=f"No answer after {user_settings.no_response_days} days",
                source=StatusChangeSource.SYSTEM,
            )
            result.no_response += 1
        await self.session.commit()


def _allowed_system(application: Application, target: ApplicationStatus) -> bool:
    try:
        check(
            application.status,
            target,
            channel=application.channel,
            source=StatusChangeSource.SYSTEM,
        )
    except TransitionError:
        return False
    return True


async def poll_all(session: AsyncSession, settings: Settings, ai: AiClient) -> dict[str, Any]:
    """Beat, every 5 minutes: every connected Gmail with read access."""
    accounts = (
        await session.scalars(
            select(OAuthAccount).where(OAuthAccount.status == OAuthStatus.CONNECTED)
        )
    ).all()
    summary: dict[str, Any] = {"accounts": 0, "replies": 0, "bounces": 0, "errors": 0}
    for user_id in [a.user_id for a in accounts]:
        try:
            result = await ReplyTracker(session, user_id, settings, ai).poll()
        except AppError as exc:
            await session.rollback()
            logger.warning("replies.poll_failed", user_id=str(user_id), error=exc.message)
            summary["errors"] += 1
            continue
        summary["accounts"] += 1
        summary["replies"] += result.replies
        summary["bounces"] += result.bounces
        summary["errors"] += len(result.errors)
    return summary

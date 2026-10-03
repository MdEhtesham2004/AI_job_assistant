"""Applications (Phase 11, Module 10): create, move through the state machine, export.

Every status change goes through `domain.state_machine.check` and writes one history row
in the same transaction; history rows are never changed afterwards.
"""

import csv
import io
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.domain.state_machine import TransitionError, check, user_options
from app.models.analysis import JobAnalysis
from app.models.applications import Application, ApplicationStatusHistory
from app.models.documents import CoverLetter
from app.models.enums import (
    ApplicationChannel,
    ApplicationStatus,
    ParseStatus,
    StatusChangeSource,
)
from app.models.jobs import Job
from app.models.outreach import Contact
from app.models.resumes import ResumeVersion
from app.repositories.analyses import JobAnalysisRepository
from app.repositories.applications import (
    ApplicationFilters,
    ApplicationHistoryRepository,
    ApplicationRepository,
)
from app.repositories.documents import CoverLetterRepository
from app.repositories.jobs import JobRepository, UserJobRepository
from app.repositories.outreach import ContactRepository
from app.repositories.resumes import ResumeVersionRepository
from app.services.analysis import active_version
from app.services.job_export import BOM, safe_cell

EXPORT_LIMIT = 5000
# Changes to the documents/channel are allowed until the application goes out.
EDITABLE = frozenset(
    {
        ApplicationStatus.READY_TO_APPLY,
        ApplicationStatus.WAITING_FOR_APPROVAL,
        ApplicationStatus.REJECTED_BY_USER,
        ApplicationStatus.FAILED,
    }
)


@dataclass(frozen=True)
class ApplicationView:
    application: Application
    job: Job
    resume: ResumeVersion | None = None
    cover_letter: CoverLetter | None = None
    analysis: JobAnalysis | None = None
    history: Sequence[ApplicationStatusHistory] = ()
    contact: Contact | None = None

    @property
    def options(self) -> list[ApplicationStatus]:
        return user_options(self.application.status, self.application.channel)


class ApplicationService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.applications = ApplicationRepository(session, owner_id=user_id)
        self.history = ApplicationHistoryRepository(session, owner_id=user_id)
        self.versions = ResumeVersionRepository(session, owner_id=user_id)
        self.letters = CoverLetterRepository(session, owner_id=user_id)
        self.contacts = ContactRepository(session, owner_id=user_id)

    # ---------- helpers ----------

    async def _get(self, application_id: uuid.UUID) -> Application:
        application = await self.applications.get(application_id)
        if application is None:
            raise NotFoundError("Application not found.")
        return application

    async def _resume(self, version_id: uuid.UUID, job_id: uuid.UUID) -> ResumeVersion:
        version = await self.versions.get(version_id)
        if version is None or version.parse_status is not ParseStatus.PARSED:
            raise ValidationAppError(
                "Choose one of your parsed resume versions.", code="BAD_RESUME"
            )
        if version.job_id is not None and version.job_id != job_id:
            raise ValidationAppError(
                "That tailored resume was made for another job.", code="BAD_RESUME"
            )
        return version

    async def _letter(self, letter_id: uuid.UUID, job_id: uuid.UUID) -> CoverLetter:
        letter = await self.letters.get(letter_id)
        if letter is None or letter.job_id != job_id:
            raise ValidationAppError("Choose a cover letter of this job.", code="BAD_COVER_LETTER")
        return letter

    async def _contact(self, contact_id: uuid.UUID) -> Contact:
        contact = await self.contacts.get(contact_id)
        if contact is None:
            raise ValidationAppError("Choose one of your contacts.", code="BAD_CONTACT")
        return contact

    def _record(
        self,
        application: Application,
        from_status: ApplicationStatus | None,
        source: StatusChangeSource,
        note: str | None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            ApplicationStatusHistory(
                user_id=self.user_id,
                application_id=application.id,
                from_status=from_status,
                to_status=application.status,
                source=source,
                note=(note or "").strip() or None,
                evidence=evidence,
            )
        )

    async def view(self, application: Application, *, with_history: bool = True) -> ApplicationView:
        job = await self.session.get(Job, application.job_id)
        assert job is not None
        analysis = None
        if application.resume_version_id:
            version = await self.versions.get(application.resume_version_id)
            source_id = (version.derived_from_id or version.id) if version else None
            if source_id:
                analysis = await JobAnalysisRepository(
                    self.session, owner_id=self.user_id
                ).for_pair(job.id, source_id)
        return ApplicationView(
            application=application,
            job=job,
            resume=await self.versions.get(application.resume_version_id)
            if application.resume_version_id
            else None,
            cover_letter=await self.letters.get(application.cover_letter_id)
            if application.cover_letter_id
            else None,
            analysis=analysis,
            history=await self.history.for_application(application.id) if with_history else (),
            contact=await self.contacts.get(application.contact_id)
            if application.contact_id
            else None,
        )

    # ---------- commands ----------

    async def create(
        self,
        job_id: uuid.UUID,
        *,
        channel: ApplicationChannel,
        resume_version_id: uuid.UUID | None,
        cover_letter_id: uuid.UUID | None,
        next_action: str | None,
        contact_id: uuid.UUID | None = None,
    ) -> Application:
        job = await JobRepository(self.session).visible(job_id, self.user_id)
        if job is None:
            raise NotFoundError("Job not found.")
        existing = await self.applications.for_job(job.id)
        if existing is not None:
            raise ConflictError(
                "You already have an application for this job.",
                code="APPLICATION_EXISTS",
                details={"application_id": str(existing.id)},
            )
        if resume_version_id:
            resume: ResumeVersion | None = await self._resume(resume_version_id, job.id)
        else:  # default: this job's tailored resume, else the active one
            resume = await self.versions.latest_tailored(job.id) or await active_version(
                self.session, self.user_id
            )
        letter = await self._letter(cover_letter_id, job.id) if cover_letter_id else None
        contact = await self._contact(contact_id) if contact_id else None
        await UserJobRepository(self.session, owner_id=self.user_id).link(job.id)
        application = await self.applications.add(
            Application(
                job_id=job.id,
                channel=channel,
                status=ApplicationStatus.READY_TO_APPLY,
                resume_version_id=resume.id if resume else None,
                cover_letter_id=letter.id if letter else None,
                contact_id=contact.id if contact else None,
                next_action=(next_action or "").strip() or None,
                last_status_at=datetime.now(UTC),
            )
        )
        self._record(application, None, StatusChangeSource.USER, "Application prepared")
        await self.session.commit()
        return application

    async def transition(
        self,
        application_id: uuid.UUID,
        target: ApplicationStatus,
        *,
        note: str | None = None,
        source: StatusChangeSource = StatusChangeSource.USER,
        evidence: dict[str, Any] | None = None,
    ) -> Application:
        application = await self._get(application_id)
        self.apply(application, target, note=note, source=source, evidence=evidence)
        await self.session.commit()
        return application

    def apply(
        self,
        application: Application,
        target: ApplicationStatus,
        *,
        note: str | None = None,
        source: StatusChangeSource = StatusChangeSource.USER,
        evidence: dict[str, Any] | None = None,
        outbox: bool = False,
    ) -> None:
        """Change the status and add the history row — the caller commits (Phase 12 uses
        this inside the email transaction, so email and application never disagree)."""
        current = application.status
        try:
            check(current, target, channel=application.channel, source=source, outbox=outbox)
        except TransitionError as exc:
            raise ConflictError(str(exc), code="INVALID_TRANSITION") from exc
        now = datetime.now(UTC)
        application.status = target
        application.last_status_at = now
        if target is ApplicationStatus.APPLIED and application.applied_at is None:
            application.applied_at = now
        self._record(application, current, source, note, evidence)

    async def mark_applied(self, application_id: uuid.UUID, note: str | None) -> Application:
        """Portal/referral: the user applied on the company's site (or via a referral)."""
        application = await self._get(application_id)
        if application.channel is ApplicationChannel.EMAIL:
            raise ConflictError(
                "Email applications are marked applied when the email is sent.",
                code="INVALID_TRANSITION",
            )
        return await self.transition(
            application_id, ApplicationStatus.APPLIED, note=note or "Marked as applied"
        )

    async def update(self, application_id: uuid.UUID, changes: dict[str, Any]) -> Application:
        application = await self._get(application_id)
        if "next_action" in changes:
            application.next_action = (changes["next_action"] or "").strip() or None
        document_fields = {
            "channel",
            "resume_version_id",
            "cover_letter_id",
            "contact_id",
        } & changes.keys()
        if document_fields and application.status not in EDITABLE:
            raise ConflictError(
                "Resume, cover letter and channel cannot change after the application went out.",
                code="APPLICATION_LOCKED",
            )
        if "channel" in changes and changes["channel"] is not None:
            channel = ApplicationChannel(changes["channel"])
            if channel is not ApplicationChannel.EMAIL and application.status is not (
                ApplicationStatus.READY_TO_APPLY
            ):
                raise ConflictError(
                    "Switch to portal/referral only while the application is ready to apply.",
                    code="APPLICATION_LOCKED",
                )
            application.channel = channel
        if "resume_version_id" in changes:
            version_id = changes["resume_version_id"]
            application.resume_version_id = (
                (await self._resume(version_id, application.job_id)).id if version_id else None
            )
        if "cover_letter_id" in changes:
            letter_id = changes["cover_letter_id"]
            application.cover_letter_id = (
                (await self._letter(letter_id, application.job_id)).id if letter_id else None
            )
        if "contact_id" in changes:
            contact_id = changes["contact_id"]
            application.contact_id = (await self._contact(contact_id)).id if contact_id else None
        await self.session.commit()
        await self.session.refresh(application)
        return application

    # ---------- queries ----------

    async def list(
        self, filters: ApplicationFilters, *, page: int, page_size: int
    ) -> tuple[Sequence[ApplicationView], int]:
        rows, total = await self.applications.page(
            filters, limit=page_size, offset=(page - 1) * page_size
        )
        scores = await self._scores([job.id for _, job in rows])
        return [
            ApplicationView(application=a, job=j, analysis=scores.get(j.id)) for a, j in rows
        ], total

    async def _scores(self, job_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, JobAnalysis]:
        version = await active_version(self.session, self.user_id)
        return await JobAnalysisRepository(self.session, owner_id=self.user_id).best_for_jobs(
            job_ids, version.id if version else None
        )

    async def counts(self) -> dict[str, int]:
        return await self.applications.status_counts()

    async def detail(self, application_id: uuid.UUID) -> ApplicationView:
        return await self.view(await self._get(application_id))

    async def for_job(self, job_id: uuid.UUID) -> ApplicationView | None:
        application = await self.applications.for_job(job_id)
        return await self.view(application, with_history=False) if application else None

    async def export_csv(self, filters: ApplicationFilters) -> str:
        rows, _ = await self.applications.page(filters, limit=EXPORT_LIMIT, offset=0)
        scores = await self._scores([job.id for _, job in rows])
        versions = {
            v.id: v
            for v in [
                await self.versions.get(a.resume_version_id) for a, _ in rows if a.resume_version_id
            ]
            if v is not None
        }
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\r\n")
        writer.writerow(
            [
                "Job",
                "Company",
                "Location",
                "Channel",
                "Status",
                "Applied",
                "Last change",
                "Next action",
                "Resume",
                "Cover letter",
                "Match score",
                "Apply link",
                "Created",
            ]
        )
        for application, job in rows:
            version = (
                versions.get(application.resume_version_id)
                if application.resume_version_id
                else None
            )
            score = scores.get(job.id)
            writer.writerow(
                [
                    safe_cell(value)
                    for value in [
                        job.title,
                        job.company,
                        job.location,
                        application.channel.value,
                        application.status.value,
                        application.applied_at,
                        application.last_status_at,
                        application.next_action,
                        f"v{version.version_no} ({version.kind.value})" if version else None,
                        "yes" if application.cover_letter_id else "no",
                        score.match_score if score else None,
                        job.apply_url,
                        application.created_at,
                    ]
                ]
            )
        return BOM + out.getvalue()

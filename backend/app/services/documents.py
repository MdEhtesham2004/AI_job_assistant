"""Tailored resumes and cover letters (Phase 10, Modules 05 + 06).

The AI only writes content. Code checks it (no invented facts; letters name the company
and role, no placeholders), renders our own HTML template and makes the PDF with Gotenberg.
User edits are saved even when the checker objects — the warnings are shown instead.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.domain.scoring import grounded
from app.integrations.ai import AiClient
from app.integrations.gotenberg import GotenbergClient
from app.integrations.storage import Storage, make_key
from app.models.documents import CoverLetter
from app.models.enums import DocumentStatus, ParseStatus, ResumeKind
from app.models.jobs import Job, UserJob
from app.models.resumes import ResumeVersion
from app.models.system import Task
from app.prompts import documents as prompts
from app.prompts.documents import CoverLetterDraft
from app.prompts.resumes import ParsedResume
from app.repositories.analyses import JobAnalysisRepository
from app.repositories.documents import CoverLetterRepository
from app.repositories.jobs import JobRepository, UserJobRepository
from app.repositories.resumes import ResumeRepository, ResumeVersionRepository
from app.repositories.tasks import TaskRepository
from app.services.ai import AiService
from app.services.analysis import active_version, can_score, effective_description
from app.services.cover_letters import body_of, compose, problems
from app.services.cover_letters import render_html as letter_html
from app.services.resume_files import PDF_MIME
from app.services.resume_improve import render_html as resume_html
from app.services.resume_improve import resume_text, ungrounded_facts
from app.services.tasks import TaskDispatcher, TaskService

JOB_ENTITY = "job"
MAX_DESCRIPTION_CHARS = 12_000


class DocumentRejectedError(AppError):
    """The AI kept producing content that fails the checks (nothing is saved)."""

    status_code = 409
    code = "DOCUMENT_REJECTED"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "job"


def _job_input(job: Job, user_job: UserJob | None) -> dict[str, Any]:
    return {
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "description": effective_description(job, user_job)[:MAX_DESCRIPTION_CHARS],
    }


def contact_line(resume: ParsedResume) -> str:
    return " · ".join(v for v in [resume.email, resume.phone, resume.location, *resume.links] if v)


def _source_text(version: ResumeVersion) -> str:
    return (version.text_content or "") + " " + str(version.parsed or "")


async def _pdf(
    gotenberg: GotenbergClient, storage: Storage, user_id: uuid.UUID, html: str, name: str
) -> tuple[str, int]:
    pdf = await gotenberg.html_to_pdf(html)
    stored = await storage.save(make_key(f"users/{user_id}/documents", name), pdf, PDF_MIME)
    return stored.key, stored.size


@dataclass(frozen=True)
class Hints:
    emphasize: list[str]
    do_not_claim: list[str]


async def _hints(
    session: AsyncSession, user_id: uuid.UUID, job: Job, version: ResumeVersion
) -> Hints:
    """Use the match analysis, when there is one, to steer what to stress and avoid.

    A tailored version has no analysis of its own — use the one of the version it was
    made from (found live: the letter check had no "lacking" skills to enforce).
    """
    analyses = JobAnalysisRepository(session, owner_id=user_id)
    analysis = await analyses.for_pair(job.id, version.id)
    if analysis is None and version.derived_from_id:
        analysis = await analyses.for_pair(job.id, version.derived_from_id)
    if analysis is None:
        return Hints([], [])
    return Hints(list(analysis.matched_skills), list(analysis.missing_skills))


def tailored_problems(candidate: ParsedResume, source: ResumeVersion) -> list[str]:
    original = ParsedResume.model_validate(source.parsed)
    return ungrounded_facts(candidate, original, source.text_content or "")


def with_identity(candidate: ParsedResume, original: ParsedResume) -> ParsedResume:
    """Name, headline and contact details always come from the original."""
    return candidate.model_copy(
        update={
            "name": original.name,
            "headline": original.headline,
            "email": original.email,
            "phone": original.phone,
            "location": original.location,
            "links": original.links,
        }
    )


# ---------- generation (worker) ----------


async def generate_tailored(
    session: AsyncSession,
    *,
    ai: AiClient,
    gotenberg: GotenbergClient,
    storage: Storage,
    user_id: uuid.UUID,
    job: Job,
    user_job: UserJob | None,
    source: ResumeVersion,
) -> ResumeVersion:
    original = ParsedResume.model_validate(source.parsed)
    hints = await _hints(session, user_id, job, source)
    messages = prompts.tailor_messages(
        original.model_dump(), _job_input(job, user_job), hints.emphasize, hints.do_not_claim
    )
    tailored: ParsedResume | None = None
    found: list[str] = []
    for _ in range(2):  # one retry with the problems listed
        result = await AiService(session, ai).complete_json(
            user_id=user_id,
            task_type="resume_tailor",
            prompt_version=prompts.TAILOR_VERSION,
            messages=messages,
            output=ParsedResume,
        )
        candidate = with_identity(result.data, original)
        # Skills the job wants but the candidate lacks must not appear as skills.
        lacking = {s.lower() for s in hints.do_not_claim}
        candidate = candidate.model_copy(
            update={"skills": [s for s in candidate.skills if s.lower() not in lacking]}
        )
        found = tailored_problems(candidate, source)
        if not found:
            tailored = candidate
            break
        messages = [
            *messages,
            {"role": "assistant", "content": result.data.model_dump_json()},
            prompts.retry_message([f"invented {p}" for p in found]),
        ]
    if tailored is None:
        raise DocumentRejectedError(
            "The AI kept adding facts that are not in your resume ("
            + ", ".join(found[:5])
            + "). Nothing was saved — please try again."
        )

    html = resume_html(tailored)
    name = f"{PurePath(source.file_name).stem}-{_slug(job.company)}.pdf"
    key, size = await _pdf(gotenberg, storage, user_id, html, name)
    await ResumeRepository(session, owner_id=user_id).get_for_update()
    versions = ResumeVersionRepository(session, owner_id=user_id)
    return await versions.add(
        ResumeVersion(
            resume_id=source.resume_id,
            version_no=await versions.next_version_no(source.resume_id),
            kind=ResumeKind.TAILORED,
            job_id=job.id,
            derived_from_id=source.id,
            file_key=key,
            file_name=name,
            mime_type=PDF_MIME,
            file_size=size,
            text_content=resume_text(tailored),
            parsed=tailored.model_dump(),
            parse_status=ParseStatus.PARSED,
            content_html=html,
        )
    )


async def generate_cover_letter(
    session: AsyncSession,
    *,
    ai: AiClient,
    gotenberg: GotenbergClient,
    storage: Storage,
    user_id: uuid.UUID,
    job: Job,
    user_job: UserJob | None,
    version: ResumeVersion,
    contact_name: str | None,
) -> CoverLetter:
    resume = ParsedResume.model_validate(version.parsed)
    hints = await _hints(session, user_id, job, version)
    job_input = _job_input(job, user_job)
    messages = prompts.cover_messages(resume.model_dump(), job_input, hints.do_not_claim)
    content: str | None = None
    found: list[str] = []
    model = ""
    for _ in range(2):
        result = await AiService(session, ai).complete_json(
            user_id=user_id,
            task_type="cover_letter",
            prompt_version=prompts.COVER_VERSION,
            messages=messages,
            output=CoverLetterDraft,
        )
        model = result.model
        draft = compose(
            result.data.paragraphs, contact_name=contact_name, candidate_name=resume.name
        )
        found = problems(
            draft,
            resume_text=_source_text(version),
            job_text=job_input["description"],
            company=job.company,
            title=job.title,
            lacking=hints.do_not_claim,
        )
        if not found:
            content = draft
            break
        messages = [
            *messages,
            {"role": "assistant", "content": result.data.model_dump_json()},
            prompts.retry_message(found),
        ]
    if content is None:
        raise DocumentRejectedError(
            "The cover letter did not pass the checks (" + "; ".join(found[:3]) + ")."
        )

    html = letter_html(content, name=resume.name, contact_line=contact_line(resume))
    key, _ = await _pdf(gotenberg, storage, user_id, html, f"cover-letter-{_slug(job.company)}.pdf")
    letter = await CoverLetterRepository(session, owner_id=user_id).add(
        CoverLetter(
            job_id=job.id,
            resume_version_id=version.id,
            content_md=content,
            file_key=key,
            model=model,
            prompt_version=prompts.COVER_VERSION,
        )
    )
    return letter


# ---------- API side ----------


@dataclass(frozen=True)
class JobDocuments:
    job: Job
    source: ResumeVersion | None  # what a new tailored resume / letter would be based on
    tailored: ResumeVersion | None
    tailored_from: ResumeVersion | None
    tailored_warnings: list[str]
    cover_letter: CoverLetter | None
    cover_warnings: list[str]
    active_tasks: Sequence[Task]


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        settings: Settings,
        storage: Storage,
        gotenberg: GotenbergClient,
        dispatcher: TaskDispatcher,
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.settings = settings
        self.storage = storage
        self.gotenberg = gotenberg
        self.versions = ResumeVersionRepository(session, owner_id=user_id)
        self.letters = CoverLetterRepository(session, owner_id=user_id)
        self.user_jobs = UserJobRepository(session, owner_id=user_id)
        self.tasks = TaskService(session, user_id, dispatcher)

    async def _job(self, job_id: uuid.UUID) -> tuple[Job, UserJob | None]:
        job = await JobRepository(self.session).visible(job_id, self.user_id)
        if job is None:
            raise NotFoundError("Job not found.")
        return job, await self.user_jobs.for_job(job.id)

    async def _source(self) -> ResumeVersion:
        version = await active_version(self.session, self.user_id)
        if version is None or version.parse_status is not ParseStatus.PARSED:
            raise ConflictError(
                "Upload a resume and wait until it is parsed first.", code="RESUME_REQUIRED"
            )
        # A tailored version is for one job; new documents start from what it was made from.
        if version.kind is ResumeKind.TAILORED and version.derived_from_id:
            parent = await self.versions.get(version.derived_from_id)
            if parent is not None:
                return parent
        return version

    async def _start(self, job_id: uuid.UUID, task_type: str, payload: dict[str, Any]) -> Task:
        job, user_job = await self._job(job_id)
        if not can_score(job, user_job):
            raise ConflictError(
                "This job has no usable description. Paste it first.", code="DESCRIPTION_MISSING"
            )
        running = await TaskRepository(self.session, owner_id=self.user_id).active_for(
            JOB_ENTITY, job.id
        )
        for task in running:
            if task.type == task_type:
                return task
        return await self.tasks.create(
            task_type, {"job_id": str(job.id), **payload}, entity_type=JOB_ENTITY, entity_id=job.id
        )

    async def start_tailor(self, job_id: uuid.UUID) -> Task:
        source = await self._source()
        return await self._start(job_id, "resume_tailor", {"version_id": str(source.id)})

    async def start_cover_letter(self, job_id: uuid.UUID, contact_name: str | None) -> Task:
        source = await self._source()
        tailored = await self.versions.latest_tailored(job_id)  # match the tailored resume
        version = tailored or source
        return await self._start(
            job_id,
            "cover_letter",
            {"version_id": str(version.id), "contact_name": (contact_name or "").strip() or None},
        )

    async def documents(self, job_id: uuid.UUID) -> JobDocuments:
        job, user_job = await self._job(job_id)
        tailored = await self.versions.latest_tailored(job.id)
        tailored_from = (
            await self.versions.get(tailored.derived_from_id)
            if tailored and tailored.derived_from_id
            else None
        )
        letter = await self.letters.latest_for_job(job.id)
        letter_version = await self.versions.get(letter.resume_version_id) if letter else None
        lacking = (
            (await _hints(self.session, self.user_id, job, letter_version)).do_not_claim
            if letter_version
            else []
        )
        try:
            source: ResumeVersion | None = await self._source()
        except ConflictError:
            source = None
        tasks = await TaskRepository(self.session, owner_id=self.user_id).active_for(
            JOB_ENTITY, job.id
        )
        return JobDocuments(
            job=job,
            source=source,
            tailored=tailored,
            tailored_from=tailored_from,
            tailored_warnings=(
                tailored_problems(ParsedResume.model_validate(tailored.parsed), tailored_from)
                if tailored and tailored.parsed and tailored_from and tailored_from.parsed
                else []
            ),
            cover_letter=letter,
            cover_warnings=(
                problems(
                    letter.content_md,
                    resume_text=_source_text(letter_version) if letter_version else "",
                    job_text=effective_description(job, user_job),
                    company=job.company,
                    title=job.title,
                    lacking=lacking,
                )
                if letter
                else []
            ),
            active_tasks=[t for t in tasks if t.type in ("resume_tailor", "cover_letter")],
        )

    async def update_tailored(self, version_id: uuid.UUID, content: ParsedResume) -> uuid.UUID:
        """Save the user's edits and re-render the PDF. Returns the job id."""
        version = await self.versions.get(version_id)
        if version is None or version.kind is not ResumeKind.TAILORED or version.job_id is None:
            raise NotFoundError("Tailored resume not found.")
        source = (
            await self.versions.get(version.derived_from_id) if version.derived_from_id else None
        )
        if source is not None and source.parsed:
            content = with_identity(content, ParsedResume.model_validate(source.parsed))
        html = resume_html(content)
        old_key = version.file_key
        key, size = await _pdf(self.gotenberg, self.storage, self.user_id, html, version.file_name)
        version.parsed = content.model_dump()
        version.text_content = resume_text(content)
        version.content_html = html
        version.file_key, version.file_size = key, size
        await self.session.commit()
        await self.storage.delete(old_key)
        return version.job_id

    async def update_cover_letter(
        self, letter_id: uuid.UUID, *, content: str | None, status: DocumentStatus | None
    ) -> uuid.UUID:
        letter = await self.letters.get(letter_id)
        if letter is None:
            raise NotFoundError("Cover letter not found.")
        if content is not None and content.strip() != letter.content_md:
            version = await self.versions.get(letter.resume_version_id)
            resume = ParsedResume.model_validate(version.parsed if version else {})
            text = content.replace("\r\n", "\n").strip()
            html = letter_html(text, name=resume.name, contact_line=contact_line(resume))
            old_key = letter.file_key
            name = f"cover-letter-{_slug((await self._job(letter.job_id))[0].company)}.pdf"
            letter.file_key, _ = await _pdf(self.gotenberg, self.storage, self.user_id, html, name)
            letter.content_md = text
            if old_key:
                await self.storage.delete(old_key)
        if status is not None:
            letter.status = status
        await self.session.commit()
        return letter.job_id


def word_count(content: str) -> int:
    return len(body_of(content).split())


def emphasized(tailored: ParsedResume, job_text: str) -> list[str]:
    """Skills of the tailored resume that the job mentions (shown as 'emphasized')."""
    return grounded(tailored.skills, job_text, 20)

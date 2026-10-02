import uuid

from fastapi import APIRouter, Request, status

from app.api.deps import ApprovedUser, DbSession
from app.core.config import Settings
from app.models.resumes import ResumeVersion
from app.prompts.resumes import ParsedResume
from app.schemas.documents import (
    CoverLetterRead,
    CoverLetterRequest,
    CoverLetterUpdate,
    JobDocumentsRead,
    SourceResume,
    TailoredRead,
    VersionRef,
)
from app.schemas.jobs import ActiveJobTask
from app.schemas.tasks import TaskCreated
from app.services.analysis import effective_description
from app.services.documents import DocumentService, JobDocuments, emphasized, word_count
from app.services.tasks import download_url

router = APIRouter(tags=["documents"])


def service(request: Request, db: DbSession, user: ApprovedUser) -> DocumentService:
    state = request.app.state
    return DocumentService(
        db,
        user.id,
        settings=state.settings,
        storage=state.storage,
        gotenberg=state.gotenberg,
        dispatcher=state.dispatcher,
    )


def _ref(version: ResumeVersion) -> VersionRef:
    return VersionRef(
        id=version.id, version_no=version.version_no, kind=version.kind, file_name=version.file_name
    )


def to_read(docs: JobDocuments, settings: Settings) -> JobDocumentsRead:
    tailored = docs.tailored
    letter = docs.cover_letter
    job_text = effective_description(docs.job, None) or ""
    return JobDocumentsRead(
        job_id=docs.job.id,
        job_title=docs.job.title,
        company=docs.job.company,
        source=_ref(docs.source) if docs.source else None,
        tailored=(
            TailoredRead(
                **_ref(tailored).model_dump(),
                parsed=tailored.parsed or {},
                download_url=download_url(
                    settings,
                    tailored.user_id,
                    key=tailored.file_key,
                    filename=tailored.file_name,
                    content_type=tailored.mime_type,
                ),
                created_at=tailored.created_at,
                updated_at=tailored.updated_at,
                warnings=docs.tailored_warnings,
                emphasized_skills=emphasized(ParsedResume.model_validate(tailored.parsed), job_text)
                if tailored.parsed
                else [],
            )
            if tailored
            else None
        ),
        tailored_from=(
            SourceResume(**_ref(docs.tailored_from).model_dump(), parsed=docs.tailored_from.parsed)
            if docs.tailored_from
            else None
        ),
        cover_letter=(
            CoverLetterRead(
                id=letter.id,
                resume_version_id=letter.resume_version_id,
                content_md=letter.content_md,
                status=letter.status,
                download_url=download_url(
                    settings,
                    letter.user_id,
                    key=letter.file_key,
                    filename=f"Cover letter - {docs.job.company}.pdf",
                    content_type="application/pdf",
                )
                if letter.file_key
                else None,
                word_count=word_count(letter.content_md),
                warnings=docs.cover_warnings,
                created_at=letter.created_at,
                updated_at=letter.updated_at,
            )
            if letter
            else None
        ),
        active_tasks=[
            ActiveJobTask(id=t.id, type=t.type, status=t.status, progress=t.progress)
            for t in docs.active_tasks
        ],
    )


@router.get(
    "/jobs/{job_id}/documents",
    response_model=JobDocumentsRead,
    summary="Tailored resume and cover letter for one job",
)
async def documents(
    job_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> JobDocumentsRead:
    return to_read(await service(request, db, user).documents(job_id), request.app.state.settings)


@router.post(
    "/jobs/{job_id}/tailored-resume",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate a tailored resume PDF for this job (new resume version)",
)
async def tailor(
    job_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> TaskCreated:
    task = await service(request, db, user).start_tailor(job_id)
    return TaskCreated(task_id=task.id)


@router.post(
    "/jobs/{job_id}/cover-letter",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate a cover letter PDF for this job",
)
async def cover_letter(
    job_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: ApprovedUser,
    body: CoverLetterRequest | None = None,
) -> TaskCreated:
    task = await service(request, db, user).start_cover_letter(
        job_id, body.contact_name if body else None
    )
    return TaskCreated(task_id=task.id)


@router.put(
    "/resumes/versions/{version_id}/content",
    response_model=JobDocumentsRead,
    summary="Edit a tailored resume (re-renders the PDF; checker warnings are returned)",
)
async def edit_tailored(
    version_id: uuid.UUID,
    body: ParsedResume,
    request: Request,
    db: DbSession,
    user: ApprovedUser,
) -> JobDocumentsRead:
    svc = service(request, db, user)
    job_id = await svc.update_tailored(version_id, body)
    return to_read(await svc.documents(job_id), request.app.state.settings)


@router.patch(
    "/cover-letters/{letter_id}",
    response_model=JobDocumentsRead,
    summary="Edit a cover letter (re-renders the PDF) or mark it final",
)
async def edit_cover_letter(
    letter_id: uuid.UUID,
    body: CoverLetterUpdate,
    request: Request,
    db: DbSession,
    user: ApprovedUser,
) -> JobDocumentsRead:
    svc = service(request, db, user)
    job_id = await svc.update_cover_letter(letter_id, content=body.content_md, status=body.status)
    return to_read(await svc.documents(job_id), request.app.state.settings)

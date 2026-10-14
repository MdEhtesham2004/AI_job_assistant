import uuid

from fastapi import APIRouter, Request, UploadFile, status

from app.api.deps import ApprovedUser, DbSession, SettingsDep
from app.core.config import Settings
from app.models.resumes import ResumeVersion
from app.schemas.resumes import (
    ActiveTask,
    AtsReportRead,
    ResumeOverview,
    ResumeUploaded,
    ResumeVersionDetail,
    ResumeVersionSummary,
)
from app.schemas.tasks import TaskCreated
from app.services.resumes import ResumeService, VersionView
from app.services.tasks import download_url

router = APIRouter(prefix="/resumes", tags=["resumes"])


def service(request: Request, db: DbSession, user: ApprovedUser) -> ResumeService:
    state = request.app.state
    return ResumeService(
        db, user.id, settings=state.settings, storage=state.storage, dispatcher=state.dispatcher
    )


def to_summary(view: VersionView) -> ResumeVersionSummary:
    v = view.version
    return ResumeVersionSummary(
        id=v.id,
        version_no=v.version_no,
        kind=v.kind,
        file_name=v.file_name,
        mime_type=v.mime_type,
        file_size=v.file_size,
        parse_status=v.parse_status,
        parse_error=v.parse_error,
        derived_from_id=v.derived_from_id,
        is_active=view.is_active,
        ats_score=view.ats_score,
        created_at=v.created_at,
    )


def file_url(version: ResumeVersion, settings: Settings) -> str:
    return download_url(
        settings,
        version.user_id,
        key=version.file_key,
        filename=version.file_name,
        content_type=version.mime_type,
    )


@router.get("", response_model=ResumeOverview, summary="Your resume and all its versions")
async def overview(request: Request, db: DbSession, user: ApprovedUser) -> ResumeOverview:
    resume, views = await service(request, db, user).overview()
    return ResumeOverview(
        resume_id=resume.id if resume else None,
        title=resume.title if resume else None,
        active_version_id=resume.active_version_id if resume else None,
        versions=[to_summary(v) for v in views],
    )


@router.post(
    "/upload",
    response_model=ResumeUploaded,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a resume (PDF or DOCX, max 5 MB) as a new version",
)
async def upload(
    file: UploadFile, request: Request, db: DbSession, user: ApprovedUser, settings: SettingsDep
) -> ResumeUploaded:
    # Read one byte past the limit: enough to reject large files without loading them whole.
    data = await file.read(settings.resume_max_bytes + 1)
    view, task = await service(request, db, user).upload(file.filename or "resume", data)
    return ResumeUploaded(version=to_summary(view), task_id=task.id)


@router.get(
    "/versions/{version_id}",
    response_model=ResumeVersionDetail,
    summary="One version: parsed content, latest ATS report, running tasks",
)
async def version_detail(
    version_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: ApprovedUser,
    settings: SettingsDep,
) -> ResumeVersionDetail:
    view, report, active = await service(request, db, user).detail(version_id)
    return ResumeVersionDetail(
        **to_summary(view).model_dump(),
        parsed=view.version.parsed,
        download_url=file_url(view.version, settings),
        ats_report=AtsReportRead.model_validate(report) if report else None,
        active_tasks=[
            ActiveTask(id=t.id, type=t.type, status=t.status, progress=t.progress) for t in active
        ],
    )


@router.post(
    "/versions/{version_id}/activate",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Make this version the active resume",
)
async def activate(
    version_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
) -> None:
    await service(request, db, user).activate(version_id)


def _action(path: str, task_type: str, summary: str) -> None:
    async def start(
        version_id: uuid.UUID, request: Request, db: DbSession, user: ApprovedUser
    ) -> TaskCreated:
        task = await service(request, db, user).start(version_id, task_type)
        return TaskCreated(task_id=task.id)

    router.add_api_route(
        f"/versions/{{version_id}}/{path}",
        start,
        methods=["POST"],
        response_model=TaskCreated,
        status_code=status.HTTP_202_ACCEPTED,
        summary=summary,
        name=task_type,
    )


_action("parse", "resume_parse", "Parse the resume again (after a failure)")
_action("ats", "resume_ats", "Run the ATS analysis")
_action("improve", "resume_improve", "Generate an improved resume PDF (new version)")
_action("linkedin-summary", "resume_linkedin", "Generate a LinkedIn headline and About")

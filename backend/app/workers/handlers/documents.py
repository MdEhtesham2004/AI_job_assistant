"""Phase 10 tasks: tailored resume PDF and cover letter PDF for one job."""

import uuid
from typing import Any

from app.core.errors import AppError
from app.models.enums import ParseStatus
from app.models.resumes import ResumeVersion
from app.repositories.jobs import JobRepository, UserJobRepository
from app.repositories.resumes import ResumeVersionRepository
from app.services.documents import generate_cover_letter, generate_tailored
from app.workers.runner import TaskContext, handler


class DocumentTaskError(AppError):
    status_code = 409
    code = "DOCUMENT_TASK_FAILED"


async def _inputs(ctx: TaskContext) -> tuple[uuid.UUID, Any, Any, ResumeVersion]:
    if ctx.user_id is None:
        raise DocumentTaskError("Document tasks need an owner.")
    owner = ctx.user_id
    job = await JobRepository(ctx.session).visible(
        uuid.UUID(str(ctx.task.payload["job_id"])), owner
    )
    version = await ResumeVersionRepository(ctx.session, owner_id=owner).get(
        uuid.UUID(str(ctx.task.payload["version_id"]))
    )
    if job is None:
        raise DocumentTaskError("The job no longer exists.")
    if version is None or version.parse_status is not ParseStatus.PARSED or not version.parsed:
        raise DocumentTaskError("The resume version is no longer available.")
    user_job = await UserJobRepository(ctx.session, owner_id=owner).for_job(job.id)
    return owner, job, user_job, version


@handler("resume_tailor", "Tailored resume", link="/jobs")
async def resume_tailor(ctx: TaskContext) -> dict[str, Any]:
    owner, job, user_job, source = await _inputs(ctx)
    await ctx.progress(10)
    version = await generate_tailored(
        ctx.session,
        ai=ctx.services.ai,
        gotenberg=ctx.services.gotenberg,
        storage=ctx.services.storage,
        user_id=owner,
        job=job,
        user_job=user_job,
        source=source,
    )
    return {
        "job_id": str(job.id),
        "version_id": str(version.id),
        "version_no": version.version_no,
        "file": {
            "key": version.file_key,
            "name": version.file_name,
            "size": version.file_size,
            "content_type": version.mime_type,
        },
    }


@handler("cover_letter", "Cover letter", link="/jobs")
async def cover_letter(ctx: TaskContext) -> dict[str, Any]:
    owner, job, user_job, version = await _inputs(ctx)
    await ctx.progress(10)
    letter = await generate_cover_letter(
        ctx.session,
        ai=ctx.services.ai,
        gotenberg=ctx.services.gotenberg,
        storage=ctx.services.storage,
        user_id=owner,
        job=job,
        user_job=user_job,
        version=version,
        contact_name=ctx.task.payload.get("contact_name"),
    )
    return {"job_id": str(job.id), "cover_letter_id": str(letter.id)}

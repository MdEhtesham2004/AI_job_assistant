"""Phase 16 — daily digest, skill gaps + learning plan, screening answers."""

import uuid

from fastapi import APIRouter, Request, status

from app.api.deps import ApprovedUser, DbSession
from app.core.errors import ConflictError
from app.models.hunt import Digest, ScreeningAnswers
from app.repositories.profiles import ProfileRepository
from app.repositories.tasks import TaskRepository
from app.schemas.hunt import (
    AnswerEdit,
    AnswerRead,
    AnswersRead,
    AnswersRequest,
    DigestRead,
    DigestState,
    SkillGapRead,
    SkillPlanRead,
    SkillsRead,
)
from app.schemas.tasks import TaskCreated
from app.services.hunt import (
    DIGEST_ENTITY,
    answers_for,
    edit_answer,
    latest_digest,
    latest_skill_plan,
    skill_gaps,
    start_answers,
    start_digest_now,
    today_for,
)
from app.services.tasks import TaskService

router = APIRouter(tags=["job hunt"])


async def _running(db: DbSession, user_id: uuid.UUID, entity: str, eid: uuid.UUID, kind: str):
    for task in await TaskRepository(db, owner_id=user_id).active_for(entity, eid):
        if task.type == kind:
            return task.id
    return None


def _digest(digest: Digest, today: object) -> DigestRead:
    return DigestRead(
        digest_date=digest.digest_date,
        created_at=digest.created_at,
        jobs=digest.jobs,
        new_jobs=digest.new_jobs,
        scored=digest.scored,
        emailed=digest.emailed,
        email_error=digest.email_error,
        is_today=digest.digest_date == today,
    )


@router.get("/digest", response_model=DigestState, summary="Your latest daily digest")
async def get_digest(db: DbSession, user: ApprovedUser) -> DigestState:
    digest = await latest_digest(db, user.id)
    profile = await ProfileRepository(db, owner_id=user.id).get(user.id)
    today = today_for(profile.timezone if profile else None)
    return DigestState(
        digest=_digest(digest, today) if digest else None,
        running_task_id=await _running(db, user.id, DIGEST_ENTITY, user.id, "daily_digest"),
    )


@router.post(
    "/digest/run",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Make today's digest now (scores new jobs, within the daily cap)",
)
async def run_digest(request: Request, db: DbSession, user: ApprovedUser) -> TaskCreated:
    task = await start_digest_now(db, user.id, request.app.state.dispatcher)
    return TaskCreated(task_id=task.id)


@router.get("/skills", response_model=SkillsRead, summary="Skill gaps across your scored jobs")
async def get_skills(db: DbSession, user: ApprovedUser) -> SkillsRead:
    found = await skill_gaps(db, user.id)
    plan = await latest_skill_plan(db, user.id)
    return SkillsRead(
        jobs_analyzed=found.jobs_analyzed,
        gaps=[SkillGapRead(**g.__dict__) for g in found.gaps],
        strengths=[SkillGapRead(**s.__dict__) for s in found.strengths],
        plan=SkillPlanRead(id=plan.id, created_at=plan.created_at, gaps=plan.gaps, plan=plan.plan)
        if plan
        else None,
        running_task_id=await _running(db, user.id, "skills", user.id, "skill_plan"),
    )


@router.post(
    "/skills/plan",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Write a 2-week learning plan for the top skill gaps (one AI call)",
)
async def make_skill_plan(request: Request, db: DbSession, user: ApprovedUser) -> TaskCreated:
    running = await _running(db, user.id, "skills", user.id, "skill_plan")
    if running:
        return TaskCreated(task_id=running)
    found = await skill_gaps(db, user.id)
    if not found.gaps:
        raise ConflictError("No skill gaps yet: score a few jobs first.", code="NO_SKILL_GAPS")
    task = await TaskService(db, user.id, request.app.state.dispatcher).create(
        "skill_plan", {}, entity_type="skills", entity_id=user.id
    )
    return TaskCreated(task_id=task.id)


def _answers(job_id: uuid.UUID, record: ScreeningAnswers | None, running) -> AnswersRead:  # type: ignore[no-untyped-def]
    return AnswersRead(
        job_id=job_id,
        answers=[AnswerRead(**a) for a in (record.answers if record else [])],
        updated_at=record.updated_at if record else None,
        running_task_id=running,
    )


@router.get("/jobs/{job_id}/answers", response_model=AnswersRead, summary="Screening answers")
async def get_answers(job_id: uuid.UUID, db: DbSession, user: ApprovedUser) -> AnswersRead:
    record = await answers_for(db, user.id, job_id)
    return _answers(job_id, record, await _running(db, user.id, "job", job_id, "screening_answers"))


@router.post(
    "/jobs/{job_id}/answers",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Write (or rewrite) screening answers for this job; your edits are kept",
)
async def make_answers(
    job_id: uuid.UUID, body: AnswersRequest, request: Request, db: DbSession, user: ApprovedUser
) -> TaskCreated:
    task = await start_answers(
        db, user.id, job_id, [q[:300] for q in body.custom_questions], request.app.state.dispatcher
    )
    return TaskCreated(task_id=task.id)


@router.patch("/jobs/{job_id}/answers/{key}", response_model=AnswersRead, summary="Edit one answer")
async def update_answer(
    job_id: uuid.UUID, key: str, body: AnswerEdit, db: DbSession, user: ApprovedUser
) -> AnswersRead:
    record = await edit_answer(db, user.id, job_id, key, body.answer)
    return _answers(job_id, record, None)

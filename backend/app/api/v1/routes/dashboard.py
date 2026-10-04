from fastapi import APIRouter

from app.api.deps import ApprovedUser, DbSession
from app.schemas.dashboard import ActivityRead, DashboardRead, RateRead
from app.services.dashboard import build

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardRead, summary="Your numbers for the home page")
async def dashboard(db: DbSession, user: ApprovedUser) -> DashboardRead:
    data = await build(db, user.id)
    return DashboardRead(
        jobs_found=data.jobs_found,
        jobs_new_this_week=data.jobs_new_this_week,
        stages=data.stages,
        statuses=data.statuses,
        waiting_for_approval=data.waiting_for_approval,
        applied_total=data.applied_total,
        responses=data.responses,
        response_rate=data.response_rate,
        interviews=data.interviews,
        offers=data.offers,
        rejected=data.rejected,
        emails_sent=data.emails_sent,
        emails_sent_today=data.emails_sent_today,
        tasks_running=data.tasks_running,
        ai_cost_month_usd=data.ai_cost_month_usd,
        by_source=[
            RateRead(key=r.key, applied=r.applied, responded=r.responded, rate=r.rate)
            for r in data.by_source
        ],
        by_resume=[
            RateRead(key=r.key, applied=r.applied, responded=r.responded, rate=r.rate)
            for r in data.by_resume
        ],
        activity=[ActivityRead(**a.__dict__) for a in data.activity],
    )

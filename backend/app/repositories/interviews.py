import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select

from app.models.enums import InterviewStatus
from app.models.interviews import Interview, InterviewReport, InterviewTurn
from app.repositories.base import OwnedRepository


class InterviewRepository(OwnedRepository[Interview]):
    model = Interview

    async def recent(self, job_id: uuid.UUID | None = None, limit: int = 50) -> Sequence[Interview]:
        query = self.scoped().order_by(Interview.created_at.desc()).limit(limit)
        if job_id is not None:
            query = query.where(Interview.job_id == job_id)
        return (await self.session.scalars(query)).all()

    async def counted_since(self, since: datetime) -> int:
        """Interviews that count against the monthly limit (failed plans do not)."""
        value = await self.session.scalar(
            select(func.count()).where(
                self._owned(),
                Interview.created_at >= since,
                Interview.status != InterviewStatus.FAILED,
            )
        )
        return int(value or 0)

    async def asked_questions(self, job_id: uuid.UUID, limit: int = 12) -> list[str]:
        """Questions already practised for this job (newest first), to ask new ones."""
        rows = await self.session.scalars(
            self.scoped()
            .where(Interview.job_id == job_id, Interview.plan.is_not(None))
            .order_by(Interview.created_at.desc())
            .limit(6)
        )
        questions: list[str] = []
        for interview in rows.all():
            for q in (interview.plan or {}).get("questions", []):
                questions.append(str(q.get("question", "")))
        return [q for q in questions if q][:limit]


class InterviewTurnRepository(OwnedRepository[InterviewTurn]):
    model = InterviewTurn

    async def for_interview(self, interview_id: uuid.UUID) -> Sequence[InterviewTurn]:
        rows = await self.session.scalars(
            self.scoped()
            .where(InterviewTurn.interview_id == interview_id)
            .order_by(InterviewTurn.seq)
        )
        return rows.all()

    async def by_seq(self, interview_id: uuid.UUID, seq: int) -> InterviewTurn | None:
        result: InterviewTurn | None = await self.session.scalar(
            self.scoped().where(
                InterviewTurn.interview_id == interview_id, InterviewTurn.seq == seq
            )
        )
        return result


class InterviewReportRepository(OwnedRepository[InterviewReport]):
    model = InterviewReport

    async def for_interview(self, interview_id: uuid.UUID) -> InterviewReport | None:
        result: InterviewReport | None = await self.session.scalar(
            self.scoped().where(InterviewReport.interview_id == interview_id)
        )
        return result

    async def for_interviews(
        self, interview_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, InterviewReport]:
        if not interview_ids:
            return {}
        rows = await self.session.scalars(
            self.scoped().where(InterviewReport.interview_id.in_(interview_ids))
        )
        return {report.interview_id: report for report in rows.all()}

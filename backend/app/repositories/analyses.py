import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import distinct_on, insert

from app.models.analysis import JobAnalysis
from app.repositories.base import OwnedRepository


class JobAnalysisRepository(OwnedRepository[JobAnalysis]):
    model = JobAnalysis

    async def for_pair(self, job_id: uuid.UUID, version_id: uuid.UUID) -> JobAnalysis | None:
        result: JobAnalysis | None = await self.session.scalar(
            self.scoped().where(
                JobAnalysis.job_id == job_id, JobAnalysis.resume_version_id == version_id
            )
        )
        return result

    async def save(self, values: dict[str, Any]) -> JobAnalysis:
        """Insert, or replace the analysis of the same job + resume version (re-analyse)."""
        values = {**values, "user_id": self.owner_id}
        changes = {k: v for k, v in values.items() if k not in ("job_id", "resume_version_id")}
        analysis_id = await self.session.scalar(
            insert(JobAnalysis)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["job_id", "resume_version_id"],
                set_={**changes, "updated_at": func.now()},
            )
            .returning(JobAnalysis.id)
        )
        analysis = await self.session.get(JobAnalysis, analysis_id, populate_existing=True)
        assert analysis is not None
        return analysis

    async def best_for_jobs(
        self, job_ids: Sequence[uuid.UUID], active_version_id: uuid.UUID | None
    ) -> dict[uuid.UUID, JobAnalysis]:
        """Per job: the analysis for the active resume if any, else the newest older one."""
        if not job_ids:
            return {}
        is_current = JobAnalysis.resume_version_id == active_version_id
        rows = await self.session.scalars(
            self.scoped()
            .where(JobAnalysis.job_id.in_(job_ids))
            .ext(distinct_on(JobAnalysis.job_id))
            .order_by(JobAnalysis.job_id, is_current.desc(), JobAnalysis.updated_at.desc())
        )
        return {analysis.job_id: analysis for analysis in rows.all()}

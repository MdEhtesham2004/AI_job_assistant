import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on

from app.models.resumes import Resume, ResumeAtsReport, ResumeVersion
from app.repositories.base import OwnedRepository


class ResumeRepository(OwnedRepository[Resume]):
    """The user's resume (one master resume per user; versions hold the files)."""

    model = Resume

    async def get_for_update(self) -> Resume | None:
        """The user's resume, row-locked so concurrent uploads get distinct version numbers."""
        result: Resume | None = await self.session.scalar(
            self.scoped().order_by(Resume.created_at).limit(1).with_for_update()
        )
        return result

    async def first(self) -> Resume | None:
        result: Resume | None = await self.session.scalar(
            self.scoped().order_by(Resume.created_at).limit(1)
        )
        return result


class ResumeVersionRepository(OwnedRepository[ResumeVersion]):
    model = ResumeVersion

    async def for_resume(self, resume_id: uuid.UUID) -> Sequence[ResumeVersion]:
        rows = await self.session.scalars(
            self.scoped()
            .where(ResumeVersion.resume_id == resume_id)
            .order_by(ResumeVersion.version_no.desc())
        )
        return rows.all()

    async def next_version_no(self, resume_id: uuid.UUID) -> int:
        current = await self.session.scalar(
            select(func.max(ResumeVersion.version_no)).where(
                self._owned(), ResumeVersion.resume_id == resume_id
            )
        )
        return (current or 0) + 1


class ResumeAtsReportRepository(OwnedRepository[ResumeAtsReport]):
    model = ResumeAtsReport

    async def latest_for(self, version_id: uuid.UUID) -> ResumeAtsReport | None:
        result: ResumeAtsReport | None = await self.session.scalar(
            self.scoped()
            .where(ResumeAtsReport.resume_version_id == version_id)
            .order_by(ResumeAtsReport.created_at.desc())
            .limit(1)
        )
        return result

    async def latest_scores(self, version_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Latest ATS score per version (for the version list)."""
        if not version_ids:
            return {}
        rows = await self.session.execute(
            select(ResumeAtsReport.resume_version_id, ResumeAtsReport.ats_score)
            .where(self._owned(), ResumeAtsReport.resume_version_id.in_(version_ids))
            .ext(distinct_on(ResumeAtsReport.resume_version_id))
            .order_by(ResumeAtsReport.resume_version_id, ResumeAtsReport.created_at.desc())
        )
        return {version_id: score for version_id, score in rows.all()}

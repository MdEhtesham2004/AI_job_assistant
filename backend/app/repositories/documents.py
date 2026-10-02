import uuid

from app.models.documents import CoverLetter
from app.repositories.base import OwnedRepository


class CoverLetterRepository(OwnedRepository[CoverLetter]):
    model = CoverLetter

    async def latest_for_job(self, job_id: uuid.UUID) -> CoverLetter | None:
        result: CoverLetter | None = await self.session.scalar(
            self.scoped()
            .where(CoverLetter.job_id == job_id)
            .order_by(CoverLetter.created_at.desc())
            .limit(1)
        )
        return result

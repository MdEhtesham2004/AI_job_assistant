"""Resumes (Phase 7): upload → validate → store → extract text → parse in the background.

A new upload is always a new version; nothing is deleted. AI work (parse, ATS analysis,
improved resume, LinkedIn summary) runs as background tasks on one resume version.
"""

import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePath

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.integrations.storage import Storage, make_key
from app.models.enums import ParseStatus, ResumeKind
from app.models.resumes import Resume, ResumeAtsReport, ResumeVersion
from app.models.system import Task
from app.repositories.resumes import (
    ResumeAtsReportRepository,
    ResumeRepository,
    ResumeVersionRepository,
)
from app.repositories.tasks import TaskRepository
from app.services.resume_files import FileTooLargeError, detect, extract_text
from app.services.tasks import TaskDispatcher, TaskService

ENTITY = "resume_version"
ACTIONS = ("resume_parse", "resume_ats", "resume_improve", "resume_linkedin")


@dataclass(frozen=True)
class VersionView:
    version: ResumeVersion
    is_active: bool
    ats_score: int | None


class ResumeService:
    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        settings: Settings,
        storage: Storage,
        dispatcher: TaskDispatcher,
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.settings = settings
        self.storage = storage
        self.resumes = ResumeRepository(session, owner_id=user_id)
        self.versions = ResumeVersionRepository(session, owner_id=user_id)
        self.reports = ResumeAtsReportRepository(session, owner_id=user_id)
        self.tasks = TaskService(session, user_id, dispatcher)

    # ---------- reading ----------

    async def overview(self) -> tuple[Resume | None, list[VersionView]]:
        resume = await self.resumes.first()
        if resume is None:
            return None, []
        versions = await self.versions.for_resume(resume.id)
        scores = await self.reports.latest_scores([v.id for v in versions])
        return resume, [
            VersionView(v, v.id == resume.active_version_id, scores.get(v.id)) for v in versions
        ]

    async def get_version(self, version_id: uuid.UUID) -> ResumeVersion:
        version = await self.versions.get(version_id)
        if version is None:
            raise NotFoundError("Resume version not found.")
        return version

    async def detail(
        self, version_id: uuid.UUID
    ) -> tuple[VersionView, ResumeAtsReport | None, Sequence[Task]]:
        version = await self.get_version(version_id)
        resume = await self.resumes.get(version.resume_id)
        report = await self.reports.latest_for(version.id)
        active = await TaskRepository(self.session, owner_id=self.user_id).active_for(
            ENTITY, version.id
        )
        is_active = resume is not None and resume.active_version_id == version.id
        view = VersionView(version, is_active, report.ats_score if report else None)
        return view, report, active

    # ---------- writing ----------

    async def upload(self, filename: str, data: bytes) -> tuple[VersionView, Task]:
        if len(data) > self.settings.resume_max_bytes:
            limit_mb = self.settings.resume_max_bytes // (1024 * 1024)
            raise FileTooLargeError(f"The file is larger than {limit_mb} MB.")
        if not data:
            raise ValidationAppError("The file is empty.", code="FILE_EMPTY")
        display_name = (PurePath(filename.replace("\\", "/")).name or "resume")[:200]
        info = detect(display_name, data)
        text = await asyncio.to_thread(extract_text, data, info.kind)

        resume = await self.resumes.get_for_update()
        if resume is None:
            resume = await self.resumes.add(Resume())
        stored = await self.storage.save(
            make_key(f"users/{self.user_id}/resumes", display_name), data, info.mime_type
        )
        version = await self.versions.add(
            ResumeVersion(
                resume_id=resume.id,
                version_no=await self.versions.next_version_no(resume.id),
                kind=ResumeKind.MASTER,
                file_key=stored.key,
                file_name=display_name,
                mime_type=info.mime_type,
                file_size=stored.size,
                text_content=text,
                parse_status=ParseStatus.PENDING,
            )
        )
        if resume.active_version_id is None:  # the first upload becomes the active version
            resume.active_version_id = version.id
            await self.session.flush()
        task = await self.tasks.create(
            "resume_parse",
            {"version_id": str(version.id)},
            entity_type=ENTITY,
            entity_id=version.id,
        )  # commits
        return VersionView(version, resume.active_version_id == version.id, None), task

    async def activate(self, version_id: uuid.UUID) -> ResumeVersion:
        version = await self.get_version(version_id)
        resume = await self.resumes.get(version.resume_id)
        if resume is None:  # pragma: no cover - versions always belong to the owner's resume
            raise NotFoundError("Resume version not found.")
        resume.active_version_id = version.id
        await self.session.commit()
        return version

    async def start(self, version_id: uuid.UUID, task_type: str) -> Task:
        """Start an AI action on a version. Re-clicking while it runs returns the same task."""
        if task_type not in ACTIONS:
            raise ValueError(task_type)
        version = await self.get_version(version_id)
        running = await TaskRepository(self.session, owner_id=self.user_id).active_for(
            ENTITY, version.id
        )
        for task in running:
            if task.type == task_type:
                return task

        if task_type == "resume_parse" and version.parse_status is ParseStatus.PARSED:
            raise ConflictError("This version is already parsed.", code="ALREADY_PARSED")
        if task_type in ("resume_improve", "resume_linkedin"):
            if version.parse_status is not ParseStatus.PARSED:
                raise ConflictError("Wait until the resume is parsed.", code="RESUME_NOT_PARSED")
            if await self.reports.latest_for(version.id) is None:
                raise ConflictError("Run the ATS analysis first.", code="ATS_REPORT_REQUIRED")

        return await self.tasks.create(
            task_type, {"version_id": str(version.id)}, entity_type=ENTITY, entity_id=version.id
        )

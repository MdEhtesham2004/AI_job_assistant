import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.models.enums import UserRole
from app.schemas.auth import UserRead


class AdminUserRead(UserRead):
    model_config = ConfigDict(from_attributes=True)

    approved_at: datetime | None
    approved_by: uuid.UUID | None
    rejection_reason: str | None
    updated_at: datetime
    # Phase 19: may schedule recruiter-email (LinkedIn) saved searches — admin-controlled.
    linkedin_schedule_allowed: bool = False


class PermissionsUpdate(BaseModel):
    linkedin_schedule_allowed: bool


class UserStatusCounts(BaseModel):
    all: int
    pending: int
    approved: int
    rejected: int
    deactivated: int


class RejectRequest(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class RoleUpdate(BaseModel):
    role: UserRole

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models.enums import ApprovalStatus, UserRole

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

Password = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: FullName
    password: Password


class LoginRequest(BaseModel):
    email: EmailStr
    # Not length-checked: a wrong password must look the same as any other wrong password.
    password: Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)]


class ChangePasswordRequest(BaseModel):
    current_password: Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)]
    new_password: Password


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: Annotated[str, Field(min_length=10, max_length=2048)]
    new_password: Password


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    approval_status: ApprovalStatus
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class SessionResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserRead


class MessageResponse(BaseModel):
    message: str

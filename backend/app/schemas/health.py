from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthCheck(BaseModel):
    status: Literal["ok", "error"]
    details: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    timestamp: datetime
    checks: dict[str, HealthCheck]

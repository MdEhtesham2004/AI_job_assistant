from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.schemas.health import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Service health")
async def health(settings: SettingsDep) -> HealthResponse:
    # Dependency checks (database, Redis, storage …) are added in later phases.
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        timestamp=datetime.now(UTC),
        checks={"api": "ok"},
    )

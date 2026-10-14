from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.deps import EngineDep, SettingsDep
from app.schemas.health import HealthCheck, HealthResponse
from app.services.health import HealthService

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Service health")
async def health(settings: SettingsDep, engine: EngineDep) -> HealthResponse:
    checks = {
        "api": HealthCheck(status="ok"),
        "database": await HealthService(engine).check_database(),
    }
    return HealthResponse(
        status="ok" if all(c.status == "ok" for c in checks.values()) else "degraded",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        timestamp=datetime.now(UTC),
        checks=checks,
    )

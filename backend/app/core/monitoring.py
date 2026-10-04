"""Optional error monitoring (Phase 14): Sentry, active only when SENTRY_DSN is set."""

import sentry_sdk
import structlog

from app.core.config import Settings

logger = structlog.get_logger("app.monitoring")

# Never send these to Sentry (tokens, passwords, emails, CVs).
_SENSITIVE = ("authorization", "cookie", "password", "token", "secret", "x-api-key")


def _scrub(event: dict, _hint: dict) -> dict:  # type: ignore[type-arg]
    request = event.get("request") or {}
    for part in ("headers", "cookies"):
        values = request.get(part)
        if isinstance(values, dict):
            for key in list(values):
                if any(s in key.lower() for s in _SENSITIVE):
                    values[key] = "[removed]"
    request.pop("data", None)  # request bodies may hold resumes or emails
    return event


def init_sentry(settings: Settings, *, component: str) -> bool:
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=settings.app_version,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        before_send=_scrub,  # type: ignore[arg-type]
    )
    sentry_sdk.set_tag("component", component)
    logger.info("sentry.enabled", component=component)
    return True

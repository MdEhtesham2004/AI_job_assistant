from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.redis import create_redis
from app.db.session import create_engine, create_session_factory
from app.integrations.gotenberg import GotenbergClient
from app.integrations.mail_dns import DnsDomainChecker
from app.integrations.storage import create_storage
from app.services.tasks import RecordingDispatcher, TaskDispatcher


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await app.state.engine.dispose()
    await app.state.redis.aclose()


def create_dispatcher(settings: Settings) -> TaskDispatcher:
    if not settings.celery_enabled:
        return RecordingDispatcher()
    from app.workers.dispatch import CeleryDispatcher

    return CeleryDispatcher()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    prefix = settings.api_prefix
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url=f"{prefix}/docs",
        redoc_url=None,
        openapi_url=f"{prefix}/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    # The engine connects lazily; creating it here does not require a running database.
    app.state.engine = create_engine(settings)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.state.rate_limiter = SlidingWindowRateLimiter()
    # Phase 6 infrastructure (all connect lazily).
    app.state.redis = create_redis(settings)
    app.state.storage = create_storage(settings)
    app.state.gotenberg = GotenbergClient.from_settings(settings)
    app.state.dispatcher = create_dispatcher(settings)
    # Phase 12: MX check for contacts the user adds (tests replace it).
    app.state.domain_checker = DnsDomainChecker()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    # Added last so it is the outermost user middleware and sees every request.
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=prefix)
    return app


app = create_app()

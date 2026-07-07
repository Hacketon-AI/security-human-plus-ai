"""FastAPI application factory for the SecureScope control plane.

The factory only wires the app: settings, metadata, and the place where domain
routers are mounted as modules are built. Scanners never execute in this
process — see ``.claude/rules/security-boundaries.md``.

Run with the factory entrypoint, e.g.::

    uvicorn app.main:create_app --factory
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    Environment,
    Settings,
    ValidationDispatcherBackend,
    get_settings,
)
from app.modules.ai_proof_of_risk.router import router as ai_proof_of_risk_router
from app.modules.asset_verifications.router import router as asset_verifications_router
from app.modules.assets.router import router as assets_router
from app.modules.authorizations.router import router as authorizations_router
from app.modules.engagements.router import router as engagements_router
from app.modules.organizations.router import router as organizations_router
from app.modules.projects.router import router as projects_router
from app.modules.validation_executions.router import (
    router as validation_executions_router,
)
from app.modules.domain_safe_scan.router import router as domain_safe_scan_router
from app.platform import health
from app.platform.database import create_engine, create_session_factory
from app.platform.error_handlers import install_error_handlers
from app.platform.observability import instrument_app


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the database engine for the app's lifetime.

    The engine connects lazily, so startup does not require a reachable
    database; the connection is disposed on shutdown.
    """
    settings: Settings = app.state.settings
    engine = create_engine(settings)
    app.state.db_engine = engine
    app.state.session_factory = create_session_factory(engine)
    # The dispatch-backend slots default to ``None`` so the dispatcher
    # resolves fail-closed when nothing has been wired. Backend-specific
    # imports stay inside their branches so an unselected backend never
    # appears in the import graph of an environment that does not use it
    # (in particular, ``celery`` is loaded only when the celery backend is
    # selected).
    app.state.validation_dispatch_queue = None
    app.state.validation_dispatch_publisher = None
    backend = settings.validation_dispatcher_backend
    if backend is ValidationDispatcherBackend.in_memory:
        from app.modules.validation_executions.in_memory_queue import (
            InMemoryDispatchQueue,
        )

        app.state.validation_dispatch_queue = InMemoryDispatchQueue()
    elif backend is ValidationDispatcherBackend.celery:
        # Settings already requires celery_broker_url for this backend.
        # Construction failures fail closed at startup — we never silently
        # fall through to ``unconfigured`` for a misconfigured production
        # broker (see ``.claude/rules/security-boundaries.md``).
        from app.modules.validation_executions.celery_publisher import (
            CeleryDispatchSettings,
            CeleryValidationDispatchPublisher,
        )
        from app.modules.validation_executions.celery_runtime import (
            create_validation_celery_app,
            make_celery_sender,
        )
        from app.platform.clock import SystemClock

        # The Settings validator guarantees a broker URL for the celery backend;
        # assert it here so the type is narrowed and a future regression fails
        # loudly at startup rather than passing ``None`` to the app builder.
        broker_url = settings.celery_broker_url
        if broker_url is None:  # pragma: no cover - enforced by Settings validator
            raise RuntimeError(
                "celery_broker_url must be configured for the celery backend"
            )
        celery_app = create_validation_celery_app(broker_url)
        sender = make_celery_sender(celery_app)
        app.state.validation_dispatch_publisher = CeleryValidationDispatchPublisher(
            sender,
            CeleryDispatchSettings(
                task_name=settings.validation_dispatch_task_name,
                routing_key=settings.validation_dispatch_routing_key,
                queue_name=settings.validation_dispatch_queue_name,
                exchange=settings.validation_dispatch_exchange,
                schema_version=settings.validation_dispatch_schema_version,
            ),
            SystemClock(),
        )
    try:
        yield
    finally:
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a configured FastAPI app. Accepts settings for test injection."""
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.0.0",
        lifespan=_lifespan,
        # Interactive docs are a development convenience only; the control
        # plane is not a public API surface.
        docs_url="/docs" if settings.environment is Environment.development else None,
        redoc_url=None,
        openapi_url=(
            "/openapi.json" if settings.environment is Environment.development else None
        ),
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    instrument_app(app, settings)
    install_error_handlers(app)

    app.include_router(health.router)
    app.include_router(organizations_router)
    app.include_router(projects_router)
    app.include_router(assets_router)
    app.include_router(asset_verifications_router)
    app.include_router(authorizations_router)
    app.include_router(engagements_router)
    app.include_router(validation_executions_router)
    app.include_router(ai_proof_of_risk_router)
    app.include_router(domain_safe_scan_router)
    return app

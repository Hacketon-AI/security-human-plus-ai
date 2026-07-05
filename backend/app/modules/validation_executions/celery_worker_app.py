"""Composition root for the isolated validation-worker Celery process.

This is the operational wiring that assembles the worker: it builds the Celery
*consumer* app, declares the queue bound to the dispatch exchange/routing key so
published envelopes are actually delivered, and registers the run-validation task
with every production dependency injected —

* the per-execution credential side-channel
  (:class:`EnvironmentWorkerCredentialSource`, container-env),
* the authenticated hook-delivery client factory
  (:func:`build_worker_client_factory` over :class:`HttpxWorkerResultTransport`),
* the scanner transport policy (:func:`build_safe_http_transport`),
* the mid-run kill switch factory
  (:func:`build_control_plane_kill_switch_factory`).

None of these run scanner logic in this module; they are wired and handed to the
tested task body. Config comes from :class:`WorkerSettings` (worker-only env, no
database DSN — ``security-boundaries.md``).

Import purity: this module imports the worker runtime, the Celery app builder,
and Celery/kombu — but no FastAPI, SQLAlchemy, repositories, services, routers,
dispatcher, or ``app.main``. The deployment entrypoint that constructs the
module-level app lives in the sibling ``worker`` module so this factory stays
importable (and testable) without worker env present.
"""

from celery import Celery
from kombu import Exchange, Queue

from app.modules.validation_executions.celery_runtime import (
    create_validation_celery_app,
)
from app.modules.validation_executions.celery_worker_bootstrap import (
    build_run_validation_task_with_handoff_source,
)
from app.modules.validation_executions.kill_switch_control_plane import (
    build_control_plane_kill_switch_factory,
)
from app.modules.validation_executions.worker_credential_env_source import (
    EnvironmentWorkerCredentialSource,
)
from app.modules.validation_executions.worker_result_transport import (
    build_worker_client_factory,
)
from app.modules.validation_executions.worker_runner import build_safe_http_transport
from app.modules.validation_executions.worker_settings import WorkerSettings
from app.platform.clock import SystemClock

__all__ = ["build_worker_celery_app"]

_WORKER_CELERY_APP_NAME = "securescope.validation.worker"


def build_worker_celery_app(settings: WorkerSettings | None = None) -> Celery:
    """Build the fully-wired validation-worker Celery consumer app.

    Loads :class:`WorkerSettings` from the environment when not supplied (tests
    pass an explicit instance). Declares the dispatch queue bound to the exchange
    and routing key so a ``celery worker -Q <queue_name>`` consumes exactly the
    envelopes the API publishes, and registers the run-validation task with the
    production side-channel, client factory, scanner transport, and kill-switch
    factory injected. No scanner logic runs here — the task body does, in the
    worker process, per delivered envelope.
    """
    settings = settings or WorkerSettings()

    celery_app = create_validation_celery_app(
        settings.celery_broker_url, app_name=_WORKER_CELERY_APP_NAME
    )
    # Declare the queue bound to the dispatch exchange/routing key. Without this
    # binding a fresh broker would drop published envelopes on the floor: the
    # consumer would listen on a queue that nothing routes to.
    exchange = Exchange(settings.exchange, type="direct", durable=True)
    celery_app.conf.task_queues = (
        Queue(
            settings.queue_name,
            exchange=exchange,
            routing_key=settings.routing_key,
            durable=True,
        ),
    )
    celery_app.conf.task_default_queue = settings.queue_name

    build_run_validation_task_with_handoff_source(
        celery_app,
        source=EnvironmentWorkerCredentialSource(SystemClock()),
        client_factory=build_worker_client_factory(
            settings.control_plane_base_url,
            timeout_seconds=settings.delivery_timeout_seconds,
        ),
        kill_switch_factory=build_control_plane_kill_switch_factory(
            settings.control_plane_base_url,
            timeout_seconds=settings.kill_switch_poll_timeout_seconds,
        ),
        transport_factory=build_safe_http_transport,
        shared_token_fallback=settings.shared_token_fallback_token,
        task_name=settings.task_name,
    )
    return celery_app

"""Deployment entrypoint for the isolated validation-worker process.

Run in the worker container as::

    celery -A app.modules.validation_executions.worker:celery_app worker \\
        -Q validation_executions --concurrency=1

The module-level ``celery_app`` is built from :class:`WorkerSettings` at import
time (Celery's ``-A`` needs a concrete app instance), so this module requires the
worker's environment to be present. It is deliberately kept to a single line over
the tested :func:`build_worker_celery_app` factory and is never imported by the
API or the test suite — tests exercise the factory directly with injected
settings, so importing this module never forces worker env into an unrelated
process.
"""

from app.modules.validation_executions.celery_worker_app import (
    build_worker_celery_app,
)

celery_app = build_worker_celery_app()

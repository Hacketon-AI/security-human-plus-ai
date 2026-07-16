"""Celery runtime wiring for the validation dispatch publisher.

This is the *only* module in the project that imports ``celery``. It builds
a :class:`celery.Celery` app from settings and wraps ``send_task`` in a
:class:`CelerySendTask` implementation that maps broker exceptions to safe
categories. The module is imported only when
``Settings.validation_dispatcher_backend`` is ``celery`` (see
:mod:`app.main`), so non-Celery environments do not pay the Celery import
cost and do not surface Celery in their dependency graph.

The runtime is publisher-side only — there is **no** worker consumer, no
task function definition, no scheduler/beat, and no eager execution. The
worker consumer is a separate, isolated process and is not implemented yet
(see ``docs/validation-dispatch-broker-design.md`` → rollout plan).

This module imports no worker runtime (``worker_runner`` /
``worker_process`` / ``worker_client`` / ``http_transport``), no FastAPI,
no SQLAlchemy session/repository/service/router. The broker URL is read
from a :class:`SecretStr` and is passed only to Celery's internal config —
never to a log, repr, or exception this module emits.
"""

import logging
from collections.abc import Mapping
from typing import Any

from celery import Celery
from pydantic import SecretStr

from app.modules.validation_executions.celery_publisher import (
    CelerySendError,
    CelerySendTask,
)

__all__ = [
    "create_validation_celery_app",
    "make_celery_sender",
]

_logger = logging.getLogger("securescope.validation.celery_runtime")

# Stable Celery app name. Not a credential — used only for Celery's internal
# routing/logging namespace.
_CELERY_APP_NAME = "securescope.validation"


def create_validation_celery_app(
    broker_url: SecretStr, *, app_name: str = _CELERY_APP_NAME
) -> Celery:
    """Construct a Celery app bound to ``broker_url``.

    Shared by both sides of the pipeline: the API-side publisher (see
    :mod:`app.main`) and the worker-side consumer (see
    :mod:`celery_worker_app`) build their Celery app here so the hardened
    configuration is identical. Configuration choices follow the broker contract
    in ``docs/validation-dispatch-broker-design.md``:

    * **No result backend.** The worker reports back via the
      ``worker-finished`` HTTP hook, not via a Celery result; a Redis (or
      any) result backend is intentionally *not* a dependency. The publisher
      always sends with ``ignore_result=True``.
    * **No eager mode.** ``task_always_eager=False`` is set explicitly so a
      stray environment variable cannot turn the API process into an
      in-process worker.
    * **JSON only.** ``pickle``/``yaml``/``msgpack`` serializers are
      refused so an envelope cannot smuggle code or non-JSON values.
    * **No automatic startup retry.** Connection retries are disabled so
      the caller fails fast and surfaces a misconfiguration at startup
      rather than blocking on a missing broker.

    The broker URL leaves :class:`SecretStr` only to be passed to Celery's
    internal config; no log, repr, or exception in this module includes it.
    """
    if broker_url is None:
        raise RuntimeError(
            "celery_broker_url must be configured before constructing the "
            "validation Celery app"
        )
    app = Celery(app_name)
    app.conf.update(
        broker_url=broker_url.get_secret_value(),
        # No result backend: worker reports via the worker-finished hook.
        result_backend=None,
        task_ignore_result=True,
        # Producer never runs tasks in-process. This must stay False so a
        # rogue env var cannot turn the API into a worker.
        task_always_eager=False,
        # Producer is JSON-only; refuse anything that could carry code.
        accept_content=["json"],
        task_serializer="json",
        # No fast/quiet startup retries: a misconfigured broker should
        # surface as a clear startup failure, not a silent slow loop.
        broker_connection_retry_on_startup=False,
    )
    return app


def make_celery_sender(celery_app: Celery) -> CelerySendTask:
    """Wrap ``celery_app.send_task`` in a :class:`CelerySendTask`.

    The wrapper:

    * forwards exactly the broker-addressing keyword arguments the
      publisher passes (``task_name``, ``kwargs``, ``routing_key``,
      ``queue``, ``exchange``, ``ignore_result``);
    * never waits for a Celery result (``send_task`` is fire-and-forget,
      no ``.get()``, no ``apply_async(...).get()``);
    * never invokes Celery's eager path;
    * returns the broker-assigned task id as a string;
    * catches **any** exception raised by Celery/Kombu/the socket layer and
      re-raises :class:`CelerySendError` with a fixed, content-free
      category — Kombu's operational errors carry the broker URL in their
      message and must never propagate. ``raise ... from None`` suppresses
      the chain so the original exception is never echoed in a traceback.

    Logs include only a coarse, non-sensitive event marker — never the
    kwargs, broker URL, exception detail, or task id.
    """

    def send(
        *,
        task_name: str,
        kwargs: Mapping[str, Any],
        routing_key: str,
        queue: str,
        exchange: str,
        ignore_result: bool,
    ) -> str:
        try:
            result = celery_app.send_task(
                task_name,
                kwargs=dict(kwargs),
                routing_key=routing_key,
                queue=queue,
                exchange=exchange,
                ignore_result=ignore_result,
            )
        except Exception:
            # Suppress the chain so the original exception (which may carry
            # the broker URL via kombu) never reaches a log or traceback.
            _logger.warning("celery send_task failed for task %s", task_name)
            raise CelerySendError("broker_send_failed") from None
        return str(result.id)

    return send

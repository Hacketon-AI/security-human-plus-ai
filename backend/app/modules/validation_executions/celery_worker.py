"""Celery production worker consumer skeleton for validation dispatch.

This is *worker-side* code. It runs in an isolated worker process — never in
the FastAPI control plane — and turns one broker-delivered
:class:`ValidationDispatchEnvelope` into the proven worker lifecycle
(worker-started -> runner -> worker-finished) using the existing
:class:`WorkerClient` hooks. It is the broker-fed counterpart of the dev-only
:mod:`in_memory_consumer`: the lifecycle, the recovery-into-``failed_safely``
behaviour, and the at-most-once / no-retry posture are identical, but this
module reads its work from a broker envelope rather than the in-process queue
and returns the minimal :class:`BrokerConsumerResult` from the broker contract.

It is deliberately import-clean: it imports the FastAPI-free contract and
serialization modules, the worker runner, and the worker client — and nothing
from the control plane (no FastAPI, ``app.main``, dispatcher, service, router,
repositories, or SQLAlchemy session). It is never imported by app startup or
any request handler, so it can never become an inline execution path. It also
does not import the dev-only :mod:`in_memory_consumer`: the small
``failed_safely`` builder is mirrored here so the production worker carries no
dependency on a development convenience.

What this skeleton does **not** do (by design — see
``docs/validation-dispatch-broker-design.md`` -> rollout plan):

* It does not query the database or fetch the execution payload from the API.
  Everything it needs is in the frozen envelope payload.
* It does not ack/nack, requeue, or otherwise mutate broker state — that is the
  broker driver's job around :func:`run_validation_envelope`.
* It does not retry. A delivery failure is reported, never re-attempted; a scan
  must never re-run automatically (scans have side effects on real targets).
* It does not deduplicate. Broker delivery is at-least-once; duplicate-safety
  lives in the idempotent ``worker-started`` / ``worker-finished`` API hooks,
  not here.
* It does not construct the control-plane delivery transport or the worker
  credential. Those are provided by the worker bootstrap (the remaining gap —
  per-execution credentials and a concrete ``WorkerResultTransport``).
"""

import asyncio
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from app.modules.validation_executions.broker_contracts import (
    DISPATCH_ENVELOPE_SCHEMA_VERSION,
    BrokerConsumerOutcome,
    BrokerConsumerResult,
    BrokerEnvelopeError,
    ValidationDispatchEnvelope,
)
from app.modules.validation_executions.dispatch_serialization import (
    WorkerDispatchSerializationError,
    deserialize_worker_dispatch_payload,
    to_worker_input,
)
from app.modules.validation_executions.enums import ExecutionOutcome, StepStatus
from app.modules.validation_executions.executor import KillSwitch
from app.modules.validation_executions.kill_switch_control_plane import (
    KillSwitchFactory,
)
from app.modules.validation_executions.schemas import (
    WorkerFinishedRequest,
    WorkerStepResult,
)
from app.modules.validation_executions.worker_client import WorkerClient
from app.modules.validation_executions.worker_runner import (
    MalformedWorkerInput,
    TransportFactory,
    run_http_security_header_validation,
)

if TYPE_CHECKING:
    # Type-only import so the worker-consumer core can be imported without the
    # ``celery`` package present. The task factory below uses the app object
    # passed in by the worker bootstrap; only that bootstrap needs celery.
    from celery import Celery

__all__ = [
    "DEFAULT_VALIDATION_TASK_NAME",
    "envelope_execution_id",
    "make_run_validation_task",
    "run_validation_envelope",
]

_logger = logging.getLogger("securescope.validation.celery_worker")

# Safe, static codes attached to a recovery-built finished request. Short,
# non-sensitive identifiers — never a raw exception type or message — kept well
# within ``WorkerFinishedRequest.error_code``'s length bound. Mirrors the
# dev consumer's codes so a recovered run looks identical on both paths.
_PAYLOAD_REJECTED_ERROR_CODE = "worker_payload_rejected"
_RUNTIME_FAILED_ERROR_CODE = "worker_runtime_failed"

# Content-free summary recording that the run produced no verdict. It names
# nothing about the target, payload, or failure mode beyond ``error_code``.
_FAILED_SAFELY_SUMMARY = "worker run did not produce a result"

# Default Celery task name for the validation worker. Mirrors the producer's
# ``Settings.validation_dispatch_task_name`` default; the worker bootstrap may
# override it to match the deployed routing.
DEFAULT_VALIDATION_TASK_NAME = "validation_executions.run_validation"


def _build_failed_safely_request(error_code: str) -> WorkerFinishedRequest:
    """Build a sanitized ``failed_safely`` :class:`WorkerFinishedRequest`.

    Used to close out a run when the runner failed *after* ``worker-started``
    succeeded — without this the execution would linger in ``executing``. The
    shape mirrors what :mod:`in_memory_consumer` emits for the same case:
    ``succeeded=False``, ``outcome=failed_safely``, a short safe ``error_code``,
    ``error_message=None`` (no raw message ever crosses the wire — see
    ``.claude/rules/data-handling.md``), a generic summary, and one synthetic
    step. The executor is *not* re-entered: recovery never re-runs scanner logic.
    """
    return WorkerFinishedRequest(
        succeeded=False,
        outcome=ExecutionOutcome.failed_safely,
        result_summary=_FAILED_SAFELY_SUMMARY,
        error_code=error_code,
        error_message=None,
        steps=[
            WorkerStepResult(
                step_name="worker",
                status=StepStatus.failed,
                evidence=None,
            )
        ],
    )


def _safe_message_id(envelope: Mapping[str, Any]) -> str | None:
    """Best-effort, non-sensitive broker message id for logging and the result.

    ``message_id`` is an opaque broker identifier (never payload content), so it
    is safe to surface even when the rest of the envelope is rejected. Anything
    that is not a non-empty string is reported as ``None`` rather than coerced.
    """
    if isinstance(envelope, Mapping):
        candidate = envelope.get("message_id")
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _load_envelope(envelope: Mapping[str, Any]) -> ValidationDispatchEnvelope:
    """Validate an untrusted broker envelope against the contract.

    Rebuilds a :class:`ValidationDispatchEnvelope` from the raw mapping, which
    enforces the wire contract on construction: exactly the envelope fields
    (extra or missing fields raise), a JSON-safe payload carrying exactly the
    five contract fields, ``content_type == "application/json"``, a positive
    ``attempt``, and a ``payload_sha256`` that matches the payload. The
    schema version is then checked against the version this consumer
    understands. Every failure is normalised to a content-free
    :class:`BrokerEnvelopeError`: a malformed or hostile envelope can never
    leak its values through an error.
    """
    if not isinstance(envelope, Mapping):
        raise BrokerEnvelopeError("envelope must be a mapping of contract fields")
    try:
        loaded = ValidationDispatchEnvelope(**dict(envelope))
    except BrokerEnvelopeError:
        # Contract violation from __post_init__ (bad hash, non-JSON-safe
        # payload, wrong field set, bad content_type/attempt). Re-raise as-is —
        # the message is already content-free.
        raise
    except TypeError:
        # Missing or unexpected envelope fields, or non-string keys: the
        # constructor signature rejected them. Never echo the offending keys.
        raise BrokerEnvelopeError(
            "envelope does not match the contract fields"
        ) from None

    if loaded.schema_version != DISPATCH_ENVELOPE_SCHEMA_VERSION:
        # The producer's schema is one this consumer does not understand. Fail
        # closed rather than process a message under an assumed shape.
        raise BrokerEnvelopeError("envelope schema_version is not supported")
    return loaded


def envelope_execution_id(envelope: Mapping[str, Any]) -> str | None:
    """Return the validated ``execution_id`` from a broker envelope, or ``None``.

    The worker bootstrap needs the execution id *before* it can resolve the
    per-execution credential from the side-channel — but must not trust an
    unvalidated envelope. This runs the full envelope + payload contract
    (schema version, field set, JSON-safety, payload hash, non-empty
    execution id) and returns the id only when every check passes;
    otherwise ``None``. It reads nothing credential-related: the execution
    id is a non-sensitive identifier, and no token ever lives in the
    envelope.
    """
    try:
        loaded = _load_envelope(envelope)
        payload = deserialize_worker_dispatch_payload(loaded.payload)
        return to_worker_input(payload).execution_id
    except (
        BrokerEnvelopeError,
        WorkerDispatchSerializationError,
        MalformedWorkerInput,
    ):
        return None


async def run_validation_envelope(
    envelope: Mapping[str, Any],
    client: WorkerClient,
    *,
    kill_switch: KillSwitch | None = None,
    kill_switch_factory: KillSwitchFactory | None = None,
    transport_factory: TransportFactory | None = None,
) -> BrokerConsumerResult:
    """Process one broker-delivered envelope through the worker lifecycle.

    The fixed sequence — identical to the dev consumer, so both paths behave
    the same under the same inputs:

    1. **Validate the envelope.** Bad schema version, bad ``payload_sha256``,
       missing fields, extra fields, a non-mapping top level, or a non-JSON-safe
       payload all resolve to :attr:`BrokerConsumerOutcome.malformed`. *No*
       ``worker-started``, *no* runner, *no* target request, *no*
       ``worker-finished`` is performed for a malformed envelope.
    2. **Deserialize the payload** to a :class:`WorkerInput`. A payload that
       passes the envelope contract but fails the worker-input contract
       (e.g. an empty ``execution_id``) is likewise ``malformed`` and posts
       nothing.
    3. **Post ``worker-started``.** If it does not deliver (transport error or
       non-2xx), short-circuit with
       :attr:`BrokerConsumerOutcome.started_delivery_failed`: the runner is
       *not* invoked and ``worker-finished`` is *not* posted, so no target
       request is made when the control plane is not ready for the transition.
    4. **Run the runner** under ``kill_switch``. An active kill switch is *not*
       an error: the runner returns a sanitized ``blocked_by_control`` result
       that is delivered normally. A runner exception is *recovered* into a
       sanitized ``failed_safely`` :class:`WorkerFinishedRequest`
       (:class:`MalformedWorkerInput` -> ``worker_payload_rejected``; any other
       exception -> ``worker_runtime_failed``) so the execution never lingers in
       ``executing``. No raw exception is logged, returned, or sent.
    5. **Post ``worker-finished``.** Delivery success ->
       :attr:`BrokerConsumerOutcome.delivered`; delivery failure ->
       :attr:`BrokerConsumerOutcome.finished_delivery_failed`. There is **no**
       retry — re-running a scan is an operator decision, never an automatic
       loop.

    Duplicate broker delivery is safe without any dedup here: the
    ``worker-started`` / ``worker-finished`` API hooks are idempotent, so a
    redelivered envelope cannot re-run a scan or overwrite a recorded verdict.

    Logs carry only the opaque ``message_id`` and the coarse outcome — never the
    envelope, payload, target, snapshot, kill-switch token, evidence, worker
    credential, broker URL, or a raw exception message.
    """
    message_id = _safe_message_id(envelope)

    # Step 1: envelope contract (schema_version + payload_sha256 + field set +
    # JSON safety). A malformed envelope is rejected before any hook or runner.
    try:
        loaded = _load_envelope(envelope)
    except BrokerEnvelopeError:
        _logger.warning("celery worker rejected malformed envelope %s", message_id)
        return BrokerConsumerResult(
            message_id=message_id, outcome=BrokerConsumerOutcome.malformed
        )
    message_id = loaded.message_id

    # Step 2: worker-input contract. Adds the non-empty execution_id / template
    # and mapping-snapshot checks the envelope layer does not make.
    try:
        payload = deserialize_worker_dispatch_payload(loaded.payload)
        worker_input = to_worker_input(payload)
    except WorkerDispatchSerializationError:
        _logger.warning("celery worker rejected malformed payload %s", message_id)
        return BrokerConsumerResult(
            message_id=message_id, outcome=BrokerConsumerOutcome.malformed
        )

    # Step 3: worker-started — gate the runner on this transition succeeding.
    try:
        started = await client.start(worker_input.execution_id)
    except Exception:
        # Includes WorkerAuthNotConfigured (missing credential fails closed) and
        # any unexpected client error. Never echo the raw exception.
        _logger.warning(
            "celery worker worker-started signal failed for message %s", message_id
        )
        return BrokerConsumerResult(
            message_id=message_id,
            outcome=BrokerConsumerOutcome.started_delivery_failed,
        )
    if not started.delivered:
        _logger.warning(
            "celery worker worker-started rejected for message %s", message_id
        )
        return BrokerConsumerResult(
            message_id=message_id,
            outcome=BrokerConsumerOutcome.started_delivery_failed,
        )

    # A per-execution kill switch is built from the frozen ``kill_switch_token``
    # (in the validated spec) so the executor can poll the control plane and
    # abort mid-run. The factory takes precedence over any fixed ``kill_switch``;
    # when neither is supplied the run proceeds without a switch (dev/test only).
    effective_kill_switch = kill_switch
    if kill_switch_factory is not None:
        token = worker_input.execution_specification.get("kill_switch_token")
        effective_kill_switch = kill_switch_factory(
            worker_input.execution_id, token if isinstance(token, str) else ""
        )

    # Step 4: runner. A failure here is recovered into a sanitized
    # ``failed_safely`` request — never re-raised, never echoed — so the
    # execution is closed out instead of lingering in ``executing``.
    try:
        finished = await run_http_security_header_validation(
            worker_input,
            kill_switch=effective_kill_switch,
            transport_factory=transport_factory,
        )
    except MalformedWorkerInput:
        _logger.warning(
            "celery worker runner rejected payload for message %s; "
            "closing out as failed_safely",
            message_id,
        )
        finished = _build_failed_safely_request(_PAYLOAD_REJECTED_ERROR_CODE)
    except Exception:
        # Never echo a raw exception (could carry target/transport detail).
        _logger.warning(
            "celery worker run failed for message %s; closing out as failed_safely",
            message_id,
        )
        finished = _build_failed_safely_request(_RUNTIME_FAILED_ERROR_CODE)

    # Step 5: worker-finished. ``deliver`` already swallows transport errors
    # into a safe result; we still guard other failure modes (e.g.
    # WorkerAuthNotConfigured) and report them without retrying.
    try:
        finished_delivery = await client.deliver(worker_input.execution_id, finished)
    except Exception:
        _logger.warning(
            "celery worker worker-finished delivery failed for message %s",
            message_id,
        )
        return BrokerConsumerResult(
            message_id=message_id,
            outcome=BrokerConsumerOutcome.finished_delivery_failed,
        )

    outcome = (
        BrokerConsumerOutcome.delivered
        if finished_delivery.delivered
        else BrokerConsumerOutcome.finished_delivery_failed
    )
    _logger.info("celery worker processed message %s: %s", message_id, outcome.value)
    return BrokerConsumerResult(message_id=message_id, outcome=outcome)


def make_run_validation_task(
    celery_app: "Celery",
    *,
    client: WorkerClient,
    kill_switch: KillSwitch,
    transport_factory: TransportFactory | None = None,
    task_name: str = DEFAULT_VALIDATION_TASK_NAME,
) -> Any:
    """Register and return a thin Celery task wrapping :func:`run_validation_envelope`.

    The task is intentionally minimal: it receives the envelope dict only,
    delegates to the tested :func:`run_validation_envelope`, and discards the
    result (``ignore_result=True`` — there is no Celery result backend; the
    worker reports back via the ``worker-finished`` hook). The worker-side
    dependencies (``client``, ``kill_switch``, optional ``transport_factory``)
    are injected by the worker bootstrap, which builds them from settings and
    environment. They are *not* constructed here, and this module is never bound
    to ``app.main`` or imported by the dispatcher/service/router.

    ``run_validation_envelope`` is exception-safe (every failure mode is mapped
    to a :class:`BrokerConsumerResult`), so the task body never raises and the
    broker driver decides ack/requeue around it. No retry is configured.

    .. note::
       Constructing ``client`` (a concrete control-plane
       :class:`WorkerResultTransport`) and the per-execution worker credential
       from the environment is the remaining worker-bootstrap step — see
       ``docs/validation-dispatch-broker-design.md`` -> rollout plan. This
       factory takes those dependencies as parameters so the consumer skeleton
       is fully testable now without inventing a delivery transport or a
       long-lived shared credential.
    """

    # Celery's @task decorator is untyped under mypy strict; we silence the
    # untyped-decorator error rather than annotate the framework.
    @celery_app.task(name=task_name, ignore_result=True)  # type: ignore[untyped-decorator]
    def run_validation(envelope: Mapping[str, Any]) -> None:
        # Thin: one async call, no business logic, no result returned.
        asyncio.run(
            run_validation_envelope(
                envelope,
                client,
                kill_switch=kill_switch,
                transport_factory=transport_factory,
            )
        )

    return run_validation

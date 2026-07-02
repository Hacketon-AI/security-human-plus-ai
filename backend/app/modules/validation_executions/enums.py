"""Validation-execution domain enumerations."""

from enum import StrEnum


class ExecutionStatus(StrEnum):
    """Lifecycle of a validation execution request.

    The control plane only ever records and transitions this state; the actual
    scanner runs in an isolated worker. ``succeeded``, ``failed``,
    ``cancelled``, and ``blocked`` are terminal.
    """

    draft = "draft"
    queued = "queued"
    dispatching = "dispatching"
    executing = "executing"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    blocked = "blocked"


class ExecutionOutcome(StrEnum):
    """Outcome of a completed validation, independent of run success.

    A run can succeed operationally yet report ``not_reproduced``; it can also
    be stopped by a target control (``blocked_by_control``) or terminate
    deliberately without harm (``failed_safely``).
    """

    not_run = "not_run"
    validated = "validated"
    not_reproduced = "not_reproduced"
    inconclusive = "inconclusive"
    blocked_by_control = "blocked_by_control"
    failed_safely = "failed_safely"


class StepStatus(StrEnum):
    """Lifecycle of a single validation step within an execution."""

    pending = "pending"
    running = "running"
    passed = "passed"
    failed = "failed"
    skipped = "skipped"
    inconclusive = "inconclusive"

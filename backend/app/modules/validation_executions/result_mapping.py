"""Map a worker-side :class:`ExecutorResult` onto the worker-finished contract.

The executor produces a sanitized in-memory result; the control plane accepts a
:class:`WorkerFinishedRequest`. This pure function bridges the two without
executing anything: a future isolated worker would call the executor, then this
mapper, then post the resulting request to the worker-finished endpoint. It runs
no I/O, touches no database, and imports no dispatch or session machinery.

It is deliberately lossy in the safe direction: the executor never exposes a
response body or a raw exception message, so neither can appear here. Only the
sanitized evidence the executor already produced is carried through.
"""

from typing import Any

from app.modules.validation_executions.enums import ExecutionOutcome, StepStatus
from app.modules.validation_executions.executor import (
    ExecutorResult,
    ExecutorStepResult,
)
from app.modules.validation_executions.schemas import (
    WorkerFinishedRequest,
    WorkerStepResult,
)

# Outcomes that represent a definitive validation verdict the run reached on its
# own. They map to operational success; everything else (a control stopped the
# run, it could not conclude, or it failed safely) maps to operational failure,
# while the precise reason is preserved in ``outcome``.
_DEFINITIVE_OUTCOMES: frozenset[ExecutionOutcome] = frozenset(
    {ExecutionOutcome.validated, ExecutionOutcome.not_reproduced}
)

# Field limits enforced by ``WorkerFinishedRequest``; trim here so the mapper
# never produces a payload the schema would reject.
_MAX_SUMMARY = 4000
_MAX_ERROR_CODE = 100


def to_worker_finished_request(result: ExecutorResult) -> WorkerFinishedRequest:
    """Convert an :class:`ExecutorResult` into a :class:`WorkerFinishedRequest`.

    ``succeeded`` reflects whether the run reached a definitive verdict;
    ``outcome`` carries the exact result. ``error_message`` is always ``None``:
    the executor only ever emits a non-sensitive ``error_code`` (an exception
    type name), never a raw message that could echo a URL or response detail.
    """
    return WorkerFinishedRequest(
        succeeded=result.outcome in _DEFINITIVE_OUTCOMES,
        outcome=result.outcome,
        result_summary=result.summary[:_MAX_SUMMARY] if result.summary else None,
        error_code=result.error_code[:_MAX_ERROR_CODE] if result.error_code else None,
        error_message=None,
        steps=_map_steps(result),
    )


def _map_steps(result: ExecutorResult) -> list[WorkerStepResult]:
    """Map executor steps to worker step payloads, carrying aggregate evidence.

    The worker-finished contract has no top-level evidence slot, so the
    executor's sanitized aggregate evidence (missing/weak headers, final URL,
    status, counts) is attached to the terminal step — the step the outcome was
    derived from. When the run was blocked before any step ran, a single
    synthetic step carries that evidence so nothing sanitized is dropped.
    """
    steps = [
        WorkerStepResult(
            step_name=step.step_name,
            status=step.status,
            evidence=_step_evidence(step),
        )
        for step in result.steps
    ]
    if not steps:
        return [
            WorkerStepResult(
                step_name="executor",
                status=_terminal_step_status(result.outcome),
                evidence=dict(result.evidence) or None,
            )
        ]

    terminal = steps[-1]
    merged: dict[str, Any] = dict(result.evidence)
    if terminal.evidence:
        merged.update(terminal.evidence)
    steps[-1] = terminal.model_copy(update={"evidence": merged})
    return steps


def _step_evidence(step: ExecutorStepResult) -> dict[str, Any] | None:
    """A step's own evidence is just its sanitized detail line, if any."""
    if step.detail is None:
        return None
    return {"detail": step.detail}


def _terminal_step_status(outcome: ExecutionOutcome) -> StepStatus:
    """Status for the synthetic step used when no executor step ran.

    Chosen to match the outcome of a run that stopped before recording a step.
    """
    if outcome in _DEFINITIVE_OUTCOMES:
        return StepStatus.passed
    if outcome is ExecutionOutcome.inconclusive:
        return StepStatus.inconclusive
    if outcome is ExecutionOutcome.blocked_by_control:
        return StepStatus.skipped
    return StepStatus.failed

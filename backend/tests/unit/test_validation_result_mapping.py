"""Unit tests for the ExecutorResult → WorkerFinishedRequest mapper.

The mapper is pure: it is exercised with hand-built executor results, asserting
the worker-finished contract is produced without leaking a body, raw message,
or unsanitized value.
"""

import ast

import pytest
from app.modules.validation_executions.enums import ExecutionOutcome, StepStatus
from app.modules.validation_executions.executor import (
    ExecutorResult,
    ExecutorStepResult,
)
from app.modules.validation_executions.result_mapping import (
    to_worker_finished_request,
)


def _result(outcome: ExecutionOutcome, **overrides: object) -> ExecutorResult:
    base: dict[str, object] = {
        "outcome": outcome,
        "summary": "2 missing and 0 weak security headers on https://app.example.com/login",
        "steps": (
            ExecutorStepResult("head_request", StepStatus.passed, "response received"),
            ExecutorStepResult(
                "evaluate_security_headers", StepStatus.passed, "2 missing, 0 weak"
            ),
        ),
        "evidence": {
            "final_url": "https://app.example.com/login",
            "status_code": 200,
            "method": "HEAD",
            "response_headers": {"x-frame-options": "DENY"},
            "missing_headers": ["Strict-Transport-Security", "Referrer-Policy"],
            "weak_headers": [],
            "request_count": 1,
            "redirect_count": 0,
        },
        "error_code": None,
    }
    base.update(overrides)
    return ExecutorResult(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("outcome", "expected_success"),
    [
        (ExecutionOutcome.validated, True),
        (ExecutionOutcome.not_reproduced, True),
        (ExecutionOutcome.inconclusive, False),
        (ExecutionOutcome.blocked_by_control, False),
        (ExecutionOutcome.failed_safely, False),
    ],
)
def test_outcome_maps_to_succeeded(
    outcome: ExecutionOutcome, expected_success: bool
) -> None:
    request = to_worker_finished_request(_result(outcome))

    assert request.outcome is outcome
    assert request.succeeded is expected_success


def test_summary_carried_and_error_message_never_set() -> None:
    request = to_worker_finished_request(
        _result(ExecutionOutcome.failed_safely, error_code="runtimeerror")
    )

    assert request.result_summary is not None
    assert request.error_code == "runtimeerror"
    # The executor never produces a raw message; the mapper must not invent one.
    assert request.error_message is None


def test_aggregate_evidence_attached_to_terminal_step() -> None:
    request = to_worker_finished_request(_result(ExecutionOutcome.validated))

    terminal = request.steps[-1]
    assert terminal.step_name == "evaluate_security_headers"
    assert terminal.evidence is not None
    # Findings preserved on the terminal step.
    assert terminal.evidence["missing_headers"] == [
        "Strict-Transport-Security",
        "Referrer-Policy",
    ]
    # The step's own detail is preserved alongside the aggregate evidence.
    assert terminal.evidence["detail"] == "2 missing, 0 weak"


def test_step_statuses_preserved() -> None:
    result = _result(
        ExecutionOutcome.validated,
        steps=(
            ExecutorStepResult("head_request", StepStatus.skipped, "HEAD unsupported"),
            ExecutorStepResult("get_request", StepStatus.passed, "response received"),
            ExecutorStepResult("evaluate_security_headers", StepStatus.passed, "ok"),
        ),
    )

    request = to_worker_finished_request(result)

    statuses = [(s.step_name, s.status) for s in request.steps]
    assert statuses == [
        ("head_request", StepStatus.skipped),
        ("get_request", StepStatus.passed),
        ("evaluate_security_headers", StepStatus.passed),
    ]


def test_blocked_before_any_step_synthesizes_carrier_step() -> None:
    result = _result(
        ExecutionOutcome.blocked_by_control,
        steps=(),
        evidence={"request_count": 0, "redirect_count": 0},
        summary="aborted by kill switch before dispatch",
    )

    request = to_worker_finished_request(result)

    assert len(request.steps) == 1
    synthetic = request.steps[0]
    assert synthetic.status is StepStatus.skipped
    assert synthetic.evidence == {"request_count": 0, "redirect_count": 0}


def test_no_response_body_can_be_mapped() -> None:
    # Even if a (forbidden) body key were smuggled into evidence, the contract
    # has no body field, so it can only ride inside step evidence — never as a
    # first-class response body. Here we assert the mapper surfaces no such key
    # at the request level and that the executor result type has no body field.
    request = to_worker_finished_request(_result(ExecutionOutcome.validated))

    assert not hasattr(request, "body")
    assert not hasattr(request, "response_body")
    for step in request.steps:
        if step.evidence is not None:
            assert "body" not in step.evidence
            assert "response_body" not in step.evidence


def test_sanitized_evidence_stays_sanitized() -> None:
    # The mapper must not re-introduce sensitive headers; it only forwards what
    # the executor already sanitized.
    result = _result(
        ExecutionOutcome.validated,
        evidence={
            "final_url": "https://app.example.com/login",
            "status_code": 200,
            "method": "HEAD",
            "response_headers": {"x-frame-options": "DENY"},
            "missing_headers": [],
            "weak_headers": [],
            "request_count": 1,
            "redirect_count": 0,
        },
    )

    request = to_worker_finished_request(result)
    terminal_evidence = request.steps[-1].evidence
    assert terminal_evidence is not None
    headers = terminal_evidence["response_headers"]
    assert "authorization" not in headers
    assert "cookie" not in headers
    assert "set-cookie" not in headers


def test_mapper_module_imports_no_persistence_or_dispatch() -> None:
    import app.modules.validation_executions.result_mapping as mapper_module

    source = mapper_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())

    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)

    forbidden = (
        "dispatcher",
        "repository",
        "service",
        "models",
        "database",
        "sqlalchemy",
    )
    for module_name in imported:
        assert not any(token in module_name for token in forbidden), (
            f"mapper must not import {module_name}"
        )

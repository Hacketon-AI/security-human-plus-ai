"""Unit tests for ``build_scope_snapshot`` port normalization and override.

The builder is pure, so it is exercised with lightweight stand-ins carrying only
the attributes it reads. These pin the ``allowed_ports`` contract: the frozen
snapshot always carries ``list[int]`` (never free text), engagement ports
override authorization ports, and a malformed stored representation blocks the
execution with a domain error before any dispatch.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.modules.validation_executions.errors import InvalidExecutionScope
from app.modules.validation_executions.specification import build_scope_snapshot


def _asset() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        target="https://api.example.com",
        asset_type=SimpleNamespace(value="api"),
        environment=SimpleNamespace(value="staging"),
    )


def _auth_scope(allowed_ports: object) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        allowed_ports=allowed_ports,
        allowed_paths=None,
        excluded_paths=None,
    )


def _eng_scope(allowed_ports: object) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        allowed_ports=allowed_ports,
        allowed_paths=None,
        excluded_paths=None,
    )


def _snapshot(
    authorization_ports: object, engagement_ports: object
) -> dict[str, object]:
    return build_scope_snapshot(
        _asset(),  # type: ignore[arg-type]
        _auth_scope(authorization_ports),  # type: ignore[arg-type]
        _eng_scope(engagement_ports),  # type: ignore[arg-type]
    )


def test_snapshot_ports_are_list_of_int() -> None:
    snapshot = _snapshot(authorization_ports=None, engagement_ports=[8443, 443])
    ports = snapshot["allowed_ports"]
    assert ports == [443, 8443]
    assert all(isinstance(p, int) for p in ports)  # type: ignore[union-attr]


def test_engagement_ports_override_authorization_ports() -> None:
    snapshot = _snapshot(authorization_ports=[443], engagement_ports=[8443])
    assert snapshot["allowed_ports"] == [8443]


def test_authorization_ports_used_when_engagement_absent() -> None:
    snapshot = _snapshot(authorization_ports=[443, 8443], engagement_ports=None)
    assert snapshot["allowed_ports"] == [443, 8443]


def test_empty_engagement_ports_override_and_do_not_inherit() -> None:
    # An explicit empty list is an override, not "absent": it means no allowed
    # ports, so the authorization ports are NOT inherited. Only None inherits.
    snapshot = _snapshot(authorization_ports=[443], engagement_ports=[])
    assert snapshot["allowed_ports"] == []


def test_absent_on_both_scopes_yields_none() -> None:
    snapshot = _snapshot(authorization_ports=None, engagement_ports=None)
    assert snapshot["allowed_ports"] is None


def test_invalid_authorization_ports_block_before_dispatch() -> None:
    # A malformed stored representation (free text) on the authorization scope
    # must raise a domain error from the snapshot builder — which runs before the
    # execution row is created or any dispatch happens — never reaching a worker.
    with pytest.raises(InvalidExecutionScope):
        _snapshot(authorization_ports="443,8443", engagement_ports=None)


def test_invalid_engagement_ports_block_before_dispatch() -> None:
    with pytest.raises(InvalidExecutionScope):
        _snapshot(authorization_ports=None, engagement_ports=["8443"])

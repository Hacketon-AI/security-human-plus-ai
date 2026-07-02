"""Unit tests for the per-execution worker credential contracts.

These pin the safe shape of the new credential model so the upcoming DB
persistence / verifier / bootstrap steps cannot regress its invariants:

* The grant carries only the digest — never the raw token.
* The raw token is returned exactly once via :class:`IssuedWorkerCredential`
  and is wrapped in :class:`SecretStr` so it cannot leak via repr/log.
* Digest is stable for the same input and unique across inputs.
* The pure :func:`evaluate_worker_credential` enforces digest match,
  organization, execution scope, action allow-list, revocation, and expiry.
* The broker envelope and the worker dispatch payload still carry no
  raw-token / credential-id surface.
* The contracts module imports nothing from FastAPI / SQLAlchemy / Celery /
  worker runtime / control-plane routers/services/repositories.
"""

import ast
import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.validation_executions import (
    worker_credential_contracts as worker_credential_contracts_module,
)
from app.modules.validation_executions.broker_contracts import (
    ValidationDispatchEnvelope,
    build_dispatch_envelope,
)
from app.modules.validation_executions.dispatch_contracts import WorkerDispatchPayload
from app.modules.validation_executions.templates import HTTP_SECURITY_HEADER_VALIDATION
from app.modules.validation_executions.worker_credential_contracts import (
    IssuedWorkerCredential,
    WorkerCredentialGrant,
    WorkerCredentialIssueOutcome,
    WorkerCredentialIssueResult,
    WorkerCredentialVerificationOutcome,
    WorkerCredentialVerificationResult,
    WorkerHookAction,
    compare_worker_token_digests,
    compute_worker_token_digest,
    evaluate_worker_credential,
    generate_worker_token,
)
from pydantic import SecretStr

# Distinctive sentinel: if any code path leaks the raw token via repr/log/test
# asserts, this string makes the failure visible.
_SENSITIVE_RAW_TOKEN = "super-secret-raw-worker-token-do-not-log"

_ORG = "11111111-1111-1111-1111-111111111111"
_EXEC = "22222222-2222-2222-2222-222222222222"
_OTHER_EXEC = "33333333-3333-3333-3333-333333333333"
_OTHER_ORG = "44444444-4444-4444-4444-444444444444"
_NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


def _grant(
    *,
    token: str = _SENSITIVE_RAW_TOKEN,
    organization_id: str = _ORG,
    execution_id: str = _EXEC,
    actions: frozenset[WorkerHookAction] | None = None,
    expires_in: timedelta = timedelta(hours=1),
    revoked_at: datetime | None = None,
) -> WorkerCredentialGrant:
    return WorkerCredentialGrant(
        credential_id="cred-abc",
        organization_id=organization_id,
        execution_id=execution_id,
        token_digest=compute_worker_token_digest(token),
        allowed_actions=actions
        or frozenset(
            {WorkerHookAction.worker_started, WorkerHookAction.worker_finished}
        ),
        issued_at=_NOW - timedelta(minutes=1),
        expires_at=_NOW + expires_in,
        revoked_at=revoked_at,
    )


# --- Issued credential exposes raw token only on the issue result -----------


def test_issued_credential_exposes_raw_token_via_secretstr_only() -> None:
    grant = _grant()
    issued = IssuedWorkerCredential(
        grant=grant, raw_token=SecretStr(_SENSITIVE_RAW_TOKEN)
    )

    # The raw token is reachable only through the SecretStr accessor.
    assert isinstance(issued.raw_token, SecretStr)
    assert issued.raw_token.get_secret_value() == _SENSITIVE_RAW_TOKEN
    # ``repr`` of the dataclass must not surface the raw token in any form —
    # SecretStr masks itself, so neither the value nor a substring leaks.
    assert _SENSITIVE_RAW_TOKEN not in repr(issued)
    assert _SENSITIVE_RAW_TOKEN not in repr(issued.raw_token)
    # The grant component carries no raw-token attribute and its repr also
    # never echoes the token.
    assert _SENSITIVE_RAW_TOKEN not in repr(issued.grant)


def test_grant_dataclass_carries_digest_not_raw_token() -> None:
    fields = {f.name for f in dataclasses.fields(WorkerCredentialGrant)}
    assert "token_digest" in fields
    # No raw-token surface — by name or alias — exists on the persisted grant.
    for forbidden in ("raw_token", "token", "secret", "plaintext_token"):
        assert forbidden not in fields, (
            f"WorkerCredentialGrant must not declare {forbidden!r}: {fields}"
        )


def test_issue_result_carries_issued_credential_only_on_success() -> None:
    grant = _grant()
    issued = IssuedWorkerCredential(
        grant=grant, raw_token=SecretStr(_SENSITIVE_RAW_TOKEN)
    )
    ok = WorkerCredentialIssueResult(
        outcome=WorkerCredentialIssueOutcome.issued, issued=issued
    )
    rejected = WorkerCredentialIssueResult(
        outcome=WorkerCredentialIssueOutcome.rejected, failure="execution_not_found"
    )

    assert ok.outcome is WorkerCredentialIssueOutcome.issued
    assert ok.issued is issued
    assert ok.failure is None

    assert rejected.outcome is WorkerCredentialIssueOutcome.rejected
    assert rejected.issued is None
    assert rejected.failure == "execution_not_found"


# --- Credential scope + actions are explicit --------------------------------


def test_grant_scope_includes_execution_and_organization_and_actions() -> None:
    grant = _grant(actions=frozenset({WorkerHookAction.worker_started}))
    assert grant.execution_id == _EXEC
    assert grant.organization_id == _ORG
    assert grant.allowed_actions == frozenset({WorkerHookAction.worker_started})


def test_allowed_actions_is_a_frozenset_of_worker_hook_action() -> None:
    grant = _grant(
        actions=frozenset(
            {WorkerHookAction.worker_started, WorkerHookAction.worker_finished}
        )
    )
    assert isinstance(grant.allowed_actions, frozenset)
    for action in grant.allowed_actions:
        assert isinstance(action, WorkerHookAction)


def test_worker_hook_action_enum_names_match_routes() -> None:
    # The hook actions exactly mirror the two route paths that mutate state.
    assert set(WorkerHookAction) == {
        WorkerHookAction.worker_started,
        WorkerHookAction.worker_finished,
    }
    assert WorkerHookAction.worker_started.value == "worker_started"
    assert WorkerHookAction.worker_finished.value == "worker_finished"


# --- Token generation + digest stability ----------------------------------


def test_generate_worker_token_returns_secretstr_with_entropy() -> None:
    token_a = generate_worker_token()
    token_b = generate_worker_token()

    assert isinstance(token_a, SecretStr)
    # Two fresh tokens are overwhelmingly unlikely to collide.
    assert token_a.get_secret_value() != token_b.get_secret_value()
    # url-safe base64 of 32 bytes yields 43 chars.
    assert len(token_a.get_secret_value()) >= 32


def test_compute_worker_token_digest_is_stable_for_same_input() -> None:
    assert compute_worker_token_digest("same") == compute_worker_token_digest("same")


def test_compute_worker_token_digest_differs_for_different_input() -> None:
    assert compute_worker_token_digest("a") != compute_worker_token_digest("b")


def test_compute_worker_token_digest_rejects_empty() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        compute_worker_token_digest("")


def test_compute_worker_token_digest_returns_sha256_hex() -> None:
    digest = compute_worker_token_digest("anything")
    # SHA-256 hex is always 64 chars over [0-9a-f].
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_compare_worker_token_digests_returns_true_for_equal_strings() -> None:
    digest = compute_worker_token_digest("equal")
    assert compare_worker_token_digests(digest, digest) is True


def test_compare_worker_token_digests_returns_false_for_distinct_strings() -> None:
    assert (
        compare_worker_token_digests(
            compute_worker_token_digest("a"), compute_worker_token_digest("b")
        )
        is False
    )


def test_compare_worker_token_digests_is_constant_time_friendly() -> None:
    """The comparison must be the documented constant-time idiom.

    We pin that the implementation uses ``hmac.compare_digest`` by exercising
    a length-mismatched comparison: the standard library function returns
    ``False`` for unequal-length inputs without raising or short-circuiting
    visibly, which a plain ``==`` would also do — so the more interesting
    pin is the *source code* containing the call. Static check covers it
    via the AST-based import-purity test below; here we keep the behavioural
    surface.
    """
    assert compare_worker_token_digests("abc", "abcd") is False


# --- evaluate_worker_credential: accepted path ----------------------------


def test_valid_credential_is_accepted() -> None:
    grant = _grant()
    result = evaluate_worker_credential(
        grant,
        presented_token=SecretStr(_SENSITIVE_RAW_TOKEN),
        expected_execution_id=_EXEC,
        expected_organization_id=_ORG,
        action=WorkerHookAction.worker_started,
        now=_NOW,
    )
    assert result.outcome is WorkerCredentialVerificationOutcome.accepted
    assert result.credential_id == grant.credential_id
    assert result.failure is None


# --- evaluate_worker_credential: rejection branches -----------------------


def test_wrong_token_is_rejected() -> None:
    grant = _grant()
    result = evaluate_worker_credential(
        grant,
        presented_token=SecretStr("a-different-token"),
        expected_execution_id=_EXEC,
        expected_organization_id=_ORG,
        action=WorkerHookAction.worker_started,
        now=_NOW,
    )
    assert result.outcome is WorkerCredentialVerificationOutcome.rejected_token
    # No credential id is leaked on rejection.
    assert result.credential_id is None


def test_wrong_execution_id_is_rejected() -> None:
    grant = _grant()
    result = evaluate_worker_credential(
        grant,
        presented_token=SecretStr(_SENSITIVE_RAW_TOKEN),
        expected_execution_id=_OTHER_EXEC,
        expected_organization_id=_ORG,
        action=WorkerHookAction.worker_started,
        now=_NOW,
    )
    assert result.outcome is WorkerCredentialVerificationOutcome.rejected_execution
    assert result.credential_id is None


def test_wrong_organization_is_rejected() -> None:
    grant = _grant()
    result = evaluate_worker_credential(
        grant,
        presented_token=SecretStr(_SENSITIVE_RAW_TOKEN),
        expected_execution_id=_EXEC,
        expected_organization_id=_OTHER_ORG,
        action=WorkerHookAction.worker_started,
        now=_NOW,
    )
    assert result.outcome is WorkerCredentialVerificationOutcome.rejected_organization
    assert result.credential_id is None


def test_disallowed_action_is_rejected() -> None:
    # Grant only authorises ``worker_finished`` — the caller tries to start.
    grant = _grant(actions=frozenset({WorkerHookAction.worker_finished}))
    result = evaluate_worker_credential(
        grant,
        presented_token=SecretStr(_SENSITIVE_RAW_TOKEN),
        expected_execution_id=_EXEC,
        expected_organization_id=_ORG,
        action=WorkerHookAction.worker_started,
        now=_NOW,
    )
    assert result.outcome is WorkerCredentialVerificationOutcome.rejected_action


def test_revoked_credential_is_rejected() -> None:
    grant = _grant(revoked_at=_NOW - timedelta(seconds=1))
    result = evaluate_worker_credential(
        grant,
        presented_token=SecretStr(_SENSITIVE_RAW_TOKEN),
        expected_execution_id=_EXEC,
        expected_organization_id=_ORG,
        action=WorkerHookAction.worker_started,
        now=_NOW,
    )
    assert result.outcome is WorkerCredentialVerificationOutcome.rejected_revoked


def test_revoked_in_future_is_still_accepted() -> None:
    # ``revoked_at`` in the future should not block — only effective-once-passed.
    grant = _grant(revoked_at=_NOW + timedelta(seconds=10))
    result = evaluate_worker_credential(
        grant,
        presented_token=SecretStr(_SENSITIVE_RAW_TOKEN),
        expected_execution_id=_EXEC,
        expected_organization_id=_ORG,
        action=WorkerHookAction.worker_started,
        now=_NOW,
    )
    assert result.outcome is WorkerCredentialVerificationOutcome.accepted


def test_expired_credential_is_rejected() -> None:
    grant = _grant(expires_in=timedelta(seconds=0))
    result = evaluate_worker_credential(
        grant,
        presented_token=SecretStr(_SENSITIVE_RAW_TOKEN),
        expected_execution_id=_EXEC,
        expected_organization_id=_ORG,
        action=WorkerHookAction.worker_started,
        now=_NOW,
    )
    assert result.outcome is WorkerCredentialVerificationOutcome.rejected_expired


def test_verification_result_is_typed_value_object() -> None:
    result = WorkerCredentialVerificationResult(
        outcome=WorkerCredentialVerificationOutcome.rejected_token,
        failure="rejected_token",
    )
    # Frozen — can't reassign on a successful or failure result.
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.outcome = WorkerCredentialVerificationOutcome.accepted  # type: ignore[misc]


# --- Broker envelope and dispatch payload remain raw-token-free ----------


def test_worker_dispatch_payload_does_not_carry_raw_token() -> None:
    fields = {f.name for f in dataclasses.fields(WorkerDispatchPayload)}
    for forbidden in (
        "worker_token",
        "raw_token",
        "credential",
        "credential_id",
        "credentials",
    ):
        assert forbidden not in fields, (
            f"WorkerDispatchPayload must not declare {forbidden!r}: {fields}"
        )


def test_dispatch_envelope_does_not_carry_raw_token() -> None:
    fields = {f.name for f in dataclasses.fields(ValidationDispatchEnvelope)}
    for forbidden in ("worker_token", "raw_token", "credential", "credentials"):
        assert forbidden not in fields, (
            f"ValidationDispatchEnvelope must not declare {forbidden!r}: {fields}"
        )


def test_dispatch_envelope_payload_remains_contract_fields_only() -> None:
    payload = WorkerDispatchPayload(
        execution_id="11111111-1111-1111-1111-111111111111",
        template_id=HTTP_SECURITY_HEADER_VALIDATION,
        execution_specification={
            "template_id": HTTP_SECURITY_HEADER_VALIDATION,
            "target": "https://app.example.test",
            "kill_switch_token": "opaque-poll-key",
        },
        scope_snapshot={"allowed_ports": [443]},
        safety_snapshot={
            "timeout_seconds": 5.0,
            "redirect_limit": 3,
            "max_requests": 5,
            "max_response_bytes": 65536,
            "kill_switch_active": False,
        },
    )
    envelope = build_dispatch_envelope(
        payload,
        message_id="m-1",
        created_at=_NOW.isoformat(),
    )

    # Envelope payload still carries exactly the five contract fields — no
    # raw token has snuck into the wire surface.
    assert set(envelope.payload.keys()) == {
        "execution_id",
        "template_id",
        "execution_specification",
        "scope_snapshot",
        "safety_snapshot",
    }
    flat = repr(envelope)
    assert "raw_token" not in flat
    assert "credential" not in flat
    assert _SENSITIVE_RAW_TOKEN not in flat


# --- Module import purity -------------------------------------------------


_FORBIDDEN_IMPORT_TOKENS = (
    "fastapi",
    "sqlalchemy",
    "celery",
    "kombu",
    "worker_runner",
    "worker_process",
    "worker_client",
    "http_transport",
    "repository",
    "service",
    "router",
    "platform.database",
    "platform.dependencies",
    "app.main",
)


def _imported_modules(module: object) -> list[str]:
    source = module.__file__  # type: ignore[attr-defined]
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def test_worker_credential_contracts_module_import_purity() -> None:
    for module_name in _imported_modules(worker_credential_contracts_module):
        assert not any(token in module_name for token in _FORBIDDEN_IMPORT_TOKENS), (
            f"worker_credential_contracts.py must not import: {module_name}"
        )


def test_worker_credential_contracts_uses_hmac_compare_digest() -> None:
    """Pin the constant-time idiom in source.

    A future refactor that replaces ``hmac.compare_digest`` with ``==`` would
    silently regress to timing-attack-leaky equality. This source-level check
    catches it.
    """
    source = worker_credential_contracts_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "hmac.compare_digest" in text

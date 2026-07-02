"""Unit tests for the persisted worker credential issuer and verifier.

Exercise the issuer's refusal categories and the verifier's outcome mapping
against fake repositories so the contracts are pinned without a database.
Integration tests against a real PostgreSQL exercise the migration, unique
constraints, and the end-to-end issue→verify cycle.

The fakes are deliberately minimal: an in-memory mapping for credentials,
an in-memory mapping for executions. They expose just enough of the real
repositories' surfaces (``add`` / ``get_by_token_digest`` /
``list_active_for_execution`` / ``revoke_for_execution`` /
``get_in_org``) for the issuer and verifier to drive their full code paths.
"""

import ast
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from app.modules.validation_executions import (
    credential_issuer as credential_issuer_module,
)
from app.modules.validation_executions import (
    credential_repository as credential_repository_module,
)
from app.modules.validation_executions import (
    credential_verifier as credential_verifier_module,
)
from app.modules.validation_executions.credential_issuer import (
    DEFAULT_CREDENTIAL_HARD_TTL,
    PersistedWorkerCredentialIssuer,
)
from app.modules.validation_executions.credential_verifier import (
    PersistedWorkerCredentialVerifier,
)
from app.modules.validation_executions.enums import ExecutionStatus
from app.modules.validation_executions.models import (
    ValidationExecution,
    ValidationWorkerCredential,
)
from app.modules.validation_executions.worker_credential_contracts import (
    IssuedWorkerCredential,
    WorkerCredentialIssueOutcome,
    WorkerCredentialIssueResult,
    WorkerCredentialVerificationOutcome,
    WorkerHookAction,
    compute_worker_token_digest,
)
from pydantic import SecretStr

_SENSITIVE_RAW_TOKEN = "do-not-log-this-raw-token-sentinel"
_NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


@dataclass
class _FakeClock:
    moment: datetime

    def now(self) -> datetime:
        return self.moment


class _FakeCredentialRepository:
    """In-memory stand-in for :class:`WorkerCredentialRepository`."""

    def __init__(self) -> None:
        self.rows: dict[UUID, ValidationWorkerCredential] = {}
        # Tests inspect this counter to assert no double-persist on rejection.
        self.added_count = 0

    async def add(self, credential: ValidationWorkerCredential) -> None:
        # SQLAlchemy server-defaults would normally fill these in; the fake
        # supplies plausible values so the issuer's grant uses them as-is.
        if credential.id is None:
            credential.id = uuid4()
        self.rows[credential.id] = credential
        self.added_count += 1

    async def get_by_token_digest(
        self, token_digest: str
    ) -> ValidationWorkerCredential | None:
        for row in self.rows.values():
            if row.token_digest == token_digest:
                return row
        return None

    async def list_active_for_execution(
        self,
        execution_id: UUID,
        organization_id: UUID,
        *,
        now: datetime,
    ) -> list[ValidationWorkerCredential]:
        return [
            row
            for row in self.rows.values()
            if row.execution_id == execution_id
            and row.organization_id == organization_id
            and row.revoked_at is None
            and row.expires_at > now
        ]

    async def revoke_for_execution(
        self,
        execution_id: UUID,
        organization_id: UUID,
        *,
        revoked_at: datetime,
    ) -> int:
        count = 0
        for row in self.rows.values():
            if (
                row.execution_id == execution_id
                and row.organization_id == organization_id
                and row.revoked_at is None
            ):
                row.revoked_at = revoked_at
                count += 1
        return count


class _FakeExecutionRepository:
    """Minimal stand-in for :class:`ValidationExecutionRepository`."""

    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, UUID], ValidationExecution] = {}

    def seed(
        self,
        *,
        execution_id: UUID,
        organization_id: UUID,
        status: ExecutionStatus = ExecutionStatus.queued,
    ) -> ValidationExecution:
        execution = ValidationExecution()
        execution.id = execution_id
        execution.organization_id = organization_id
        execution.status = status
        self.rows[(execution_id, organization_id)] = execution
        return execution

    async def get_in_org(
        self, execution_id: UUID, organization_id: UUID
    ) -> ValidationExecution | None:
        return self.rows.get((execution_id, organization_id))


def _issuer(
    credentials: _FakeCredentialRepository,
    executions: _FakeExecutionRepository,
    *,
    now: datetime = _NOW,
    hard_ttl: timedelta = DEFAULT_CREDENTIAL_HARD_TTL,
) -> PersistedWorkerCredentialIssuer:
    return PersistedWorkerCredentialIssuer(
        cast("object", credentials),  # type: ignore[arg-type]
        cast("object", executions),  # type: ignore[arg-type]
        _FakeClock(moment=now),
        hard_ttl=hard_ttl,
    )


def _verifier(
    credentials: _FakeCredentialRepository,
    *,
    now: datetime = _NOW,
) -> PersistedWorkerCredentialVerifier:
    return PersistedWorkerCredentialVerifier(
        cast("object", credentials),  # type: ignore[arg-type]
        _FakeClock(moment=now),
    )


# --- Issuer happy path ----------------------------------------------------


async def test_issuer_persists_digest_only_and_returns_raw_token_once() -> None:
    credentials = _FakeCredentialRepository()
    executions = _FakeExecutionRepository()
    exec_id = uuid4()
    org_id = uuid4()
    executions.seed(execution_id=exec_id, organization_id=org_id)

    result = await _issuer(credentials, executions).issue(
        execution_id=str(exec_id),
        organization_id=str(org_id),
        allowed_actions=frozenset(
            {WorkerHookAction.worker_started, WorkerHookAction.worker_finished}
        ),
        expires_at=_NOW + timedelta(minutes=30),
    )

    assert result.outcome is WorkerCredentialIssueOutcome.issued
    assert credentials.added_count == 1
    issued = result.issued
    assert isinstance(issued, IssuedWorkerCredential)

    # Exactly one row, carrying the digest of the returned raw token.
    [row] = list(credentials.rows.values())
    raw = issued.raw_token.get_secret_value()
    assert row.token_digest == compute_worker_token_digest(raw)
    # The raw token does not appear on the persisted row in any column.
    for column in (
        row.token_digest,
        *(row.allowed_actions or []),
        row.organization_id,
        row.execution_id,
    ):
        assert raw not in repr(column)
    # The grant references the digest, not the raw token; SecretStr keeps the
    # raw out of repr.
    assert issued.grant.token_digest == row.token_digest
    assert raw not in repr(issued.grant)
    assert raw not in repr(issued)


# --- Issuer refusal categories --------------------------------------------


async def test_issuer_rejects_empty_allowed_actions() -> None:
    credentials = _FakeCredentialRepository()
    executions = _FakeExecutionRepository()
    exec_id, org_id = uuid4(), uuid4()
    executions.seed(execution_id=exec_id, organization_id=org_id)

    result = await _issuer(credentials, executions).issue(
        execution_id=str(exec_id),
        organization_id=str(org_id),
        allowed_actions=frozenset(),
        expires_at=_NOW + timedelta(minutes=30),
    )

    assert result == WorkerCredentialIssueResult(
        outcome=WorkerCredentialIssueOutcome.rejected, failure="empty_actions"
    )
    # No row was persisted.
    assert credentials.added_count == 0


@pytest.mark.parametrize(
    "expires_in",
    [
        timedelta(seconds=0),  # ``now`` is not in the future.
        timedelta(seconds=-5),
        DEFAULT_CREDENTIAL_HARD_TTL + timedelta(minutes=1),  # past hard cap.
    ],
)
async def test_issuer_rejects_invalid_expiry(expires_in: timedelta) -> None:
    credentials = _FakeCredentialRepository()
    executions = _FakeExecutionRepository()
    exec_id, org_id = uuid4(), uuid4()
    executions.seed(execution_id=exec_id, organization_id=org_id)

    result = await _issuer(credentials, executions).issue(
        execution_id=str(exec_id),
        organization_id=str(org_id),
        allowed_actions=frozenset({WorkerHookAction.worker_started}),
        expires_at=_NOW + expires_in,
    )

    assert result.outcome is WorkerCredentialIssueOutcome.rejected
    assert result.failure == "invalid_expiry"
    assert credentials.added_count == 0


async def test_issuer_rejects_missing_execution() -> None:
    credentials = _FakeCredentialRepository()
    executions = _FakeExecutionRepository()  # not seeded.

    result = await _issuer(credentials, executions).issue(
        execution_id=str(uuid4()),
        organization_id=str(uuid4()),
        allowed_actions=frozenset({WorkerHookAction.worker_started}),
        expires_at=_NOW + timedelta(minutes=30),
    )

    assert result.outcome is WorkerCredentialIssueOutcome.rejected
    assert result.failure == "execution_not_found"
    assert credentials.added_count == 0


async def test_issuer_rejects_malformed_execution_id() -> None:
    credentials = _FakeCredentialRepository()
    executions = _FakeExecutionRepository()

    result = await _issuer(credentials, executions).issue(
        execution_id="not-a-uuid",
        organization_id=str(uuid4()),
        allowed_actions=frozenset({WorkerHookAction.worker_started}),
        expires_at=_NOW + timedelta(minutes=30),
    )

    assert result.outcome is WorkerCredentialIssueOutcome.rejected
    assert result.failure == "execution_not_found"
    assert credentials.added_count == 0


@pytest.mark.parametrize(
    "status",
    [
        ExecutionStatus.succeeded,
        ExecutionStatus.failed,
        ExecutionStatus.cancelled,
        ExecutionStatus.blocked,
        ExecutionStatus.draft,
    ],
)
async def test_issuer_rejects_non_issuable_execution_status(
    status: ExecutionStatus,
) -> None:
    credentials = _FakeCredentialRepository()
    executions = _FakeExecutionRepository()
    exec_id, org_id = uuid4(), uuid4()
    executions.seed(execution_id=exec_id, organization_id=org_id, status=status)

    result = await _issuer(credentials, executions).issue(
        execution_id=str(exec_id),
        organization_id=str(org_id),
        allowed_actions=frozenset({WorkerHookAction.worker_started}),
        expires_at=_NOW + timedelta(minutes=30),
    )

    assert result.outcome is WorkerCredentialIssueOutcome.rejected
    assert result.failure == "execution_not_issuable"
    assert credentials.added_count == 0


# --- Verifier outcomes ----------------------------------------------------


async def _seed_grant(
    credentials: _FakeCredentialRepository,
    *,
    raw_token: str,
    organization_id: UUID,
    execution_id: UUID,
    actions: frozenset[WorkerHookAction],
    expires_at: datetime,
    revoked_at: datetime | None = None,
) -> ValidationWorkerCredential:
    credential = ValidationWorkerCredential()
    credential.id = uuid4()
    credential.organization_id = organization_id
    credential.execution_id = execution_id
    credential.token_digest = compute_worker_token_digest(raw_token)
    credential.allowed_actions = sorted(a.value for a in actions)
    credential.issued_at = _NOW - timedelta(minutes=1)
    credential.expires_at = expires_at
    credential.revoked_at = revoked_at
    await credentials.add(credential)
    return credential


async def test_verifier_accepts_valid_credential() -> None:
    credentials = _FakeCredentialRepository()
    org_id, exec_id = uuid4(), uuid4()
    await _seed_grant(
        credentials,
        raw_token=_SENSITIVE_RAW_TOKEN,
        organization_id=org_id,
        execution_id=exec_id,
        actions=frozenset(
            {WorkerHookAction.worker_started, WorkerHookAction.worker_finished}
        ),
        expires_at=_NOW + timedelta(hours=1),
    )

    result = await _verifier(credentials).verify(
        presented_token=SecretStr(_SENSITIVE_RAW_TOKEN),
        expected_execution_id=str(exec_id),
        expected_organization_id=str(org_id),
        action=WorkerHookAction.worker_started,
    )

    assert result.outcome is WorkerCredentialVerificationOutcome.accepted
    assert result.credential_id is not None


async def test_verifier_rejects_token_not_in_db() -> None:
    credentials = _FakeCredentialRepository()  # empty.

    result = await _verifier(credentials).verify(
        presented_token=SecretStr(_SENSITIVE_RAW_TOKEN),
        expected_execution_id=str(uuid4()),
        expected_organization_id=str(uuid4()),
        action=WorkerHookAction.worker_started,
    )

    assert result.outcome is WorkerCredentialVerificationOutcome.rejected_token
    assert result.credential_id is None


async def test_verifier_rejects_wrong_token_for_existing_execution() -> None:
    credentials = _FakeCredentialRepository()
    org_id, exec_id = uuid4(), uuid4()
    await _seed_grant(
        credentials,
        raw_token=_SENSITIVE_RAW_TOKEN,
        organization_id=org_id,
        execution_id=exec_id,
        actions=frozenset({WorkerHookAction.worker_started}),
        expires_at=_NOW + timedelta(hours=1),
    )

    result = await _verifier(credentials).verify(
        presented_token=SecretStr("not-the-real-token"),
        expected_execution_id=str(exec_id),
        expected_organization_id=str(org_id),
        action=WorkerHookAction.worker_started,
    )

    # Treated the same as "no row" — indistinguishable to the caller.
    assert result.outcome is WorkerCredentialVerificationOutcome.rejected_token


async def test_verifier_rejects_wrong_execution_id() -> None:
    credentials = _FakeCredentialRepository()
    org_id, exec_id = uuid4(), uuid4()
    await _seed_grant(
        credentials,
        raw_token=_SENSITIVE_RAW_TOKEN,
        organization_id=org_id,
        execution_id=exec_id,
        actions=frozenset({WorkerHookAction.worker_started}),
        expires_at=_NOW + timedelta(hours=1),
    )

    result = await _verifier(credentials).verify(
        presented_token=SecretStr(_SENSITIVE_RAW_TOKEN),
        expected_execution_id=str(uuid4()),
        expected_organization_id=str(org_id),
        action=WorkerHookAction.worker_started,
    )

    assert result.outcome is WorkerCredentialVerificationOutcome.rejected_execution


async def test_verifier_rejects_wrong_organization_id() -> None:
    credentials = _FakeCredentialRepository()
    org_id, exec_id = uuid4(), uuid4()
    await _seed_grant(
        credentials,
        raw_token=_SENSITIVE_RAW_TOKEN,
        organization_id=org_id,
        execution_id=exec_id,
        actions=frozenset({WorkerHookAction.worker_started}),
        expires_at=_NOW + timedelta(hours=1),
    )

    result = await _verifier(credentials).verify(
        presented_token=SecretStr(_SENSITIVE_RAW_TOKEN),
        expected_execution_id=str(exec_id),
        expected_organization_id=str(uuid4()),
        action=WorkerHookAction.worker_started,
    )

    assert result.outcome is WorkerCredentialVerificationOutcome.rejected_organization


async def test_verifier_rejects_disallowed_action() -> None:
    credentials = _FakeCredentialRepository()
    org_id, exec_id = uuid4(), uuid4()
    await _seed_grant(
        credentials,
        raw_token=_SENSITIVE_RAW_TOKEN,
        organization_id=org_id,
        execution_id=exec_id,
        actions=frozenset({WorkerHookAction.worker_finished}),
        expires_at=_NOW + timedelta(hours=1),
    )

    result = await _verifier(credentials).verify(
        presented_token=SecretStr(_SENSITIVE_RAW_TOKEN),
        expected_execution_id=str(exec_id),
        expected_organization_id=str(org_id),
        action=WorkerHookAction.worker_started,
    )

    assert result.outcome is WorkerCredentialVerificationOutcome.rejected_action


async def test_verifier_rejects_expired_credential() -> None:
    credentials = _FakeCredentialRepository()
    org_id, exec_id = uuid4(), uuid4()
    await _seed_grant(
        credentials,
        raw_token=_SENSITIVE_RAW_TOKEN,
        organization_id=org_id,
        execution_id=exec_id,
        actions=frozenset({WorkerHookAction.worker_started}),
        expires_at=_NOW - timedelta(seconds=1),
    )

    result = await _verifier(credentials).verify(
        presented_token=SecretStr(_SENSITIVE_RAW_TOKEN),
        expected_execution_id=str(exec_id),
        expected_organization_id=str(org_id),
        action=WorkerHookAction.worker_started,
    )

    assert result.outcome is WorkerCredentialVerificationOutcome.rejected_expired


async def test_verifier_rejects_revoked_credential() -> None:
    credentials = _FakeCredentialRepository()
    org_id, exec_id = uuid4(), uuid4()
    await _seed_grant(
        credentials,
        raw_token=_SENSITIVE_RAW_TOKEN,
        organization_id=org_id,
        execution_id=exec_id,
        actions=frozenset({WorkerHookAction.worker_started}),
        expires_at=_NOW + timedelta(hours=1),
        revoked_at=_NOW - timedelta(seconds=1),
    )

    result = await _verifier(credentials).verify(
        presented_token=SecretStr(_SENSITIVE_RAW_TOKEN),
        expected_execution_id=str(exec_id),
        expected_organization_id=str(org_id),
        action=WorkerHookAction.worker_started,
    )

    assert result.outcome is WorkerCredentialVerificationOutcome.rejected_revoked


async def test_verifier_rejects_empty_presented_token() -> None:
    credentials = _FakeCredentialRepository()

    result = await _verifier(credentials).verify(
        presented_token=SecretStr(""),
        expected_execution_id=str(uuid4()),
        expected_organization_id=str(uuid4()),
        action=WorkerHookAction.worker_started,
    )

    assert result.outcome is WorkerCredentialVerificationOutcome.rejected_token


# --- Log safety -----------------------------------------------------------


async def test_no_raw_token_in_logs_on_issue(
    caplog: pytest.LogCaptureFixture,
) -> None:
    credentials = _FakeCredentialRepository()
    executions = _FakeExecutionRepository()
    exec_id, org_id = uuid4(), uuid4()
    executions.seed(execution_id=exec_id, organization_id=org_id)

    with caplog.at_level(logging.INFO, logger="securescope"):
        result = await _issuer(credentials, executions).issue(
            execution_id=str(exec_id),
            organization_id=str(org_id),
            allowed_actions=frozenset({WorkerHookAction.worker_started}),
            expires_at=_NOW + timedelta(minutes=30),
        )

    raw = result.issued.raw_token.get_secret_value() if result.issued else ""
    assert raw  # sanity
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert raw not in log_text


async def test_no_raw_token_in_logs_on_verify(
    caplog: pytest.LogCaptureFixture,
) -> None:
    credentials = _FakeCredentialRepository()
    org_id, exec_id = uuid4(), uuid4()
    await _seed_grant(
        credentials,
        raw_token=_SENSITIVE_RAW_TOKEN,
        organization_id=org_id,
        execution_id=exec_id,
        actions=frozenset({WorkerHookAction.worker_started}),
        expires_at=_NOW + timedelta(hours=1),
    )

    with caplog.at_level(logging.INFO, logger="securescope"):
        await _verifier(credentials).verify(
            presented_token=SecretStr(_SENSITIVE_RAW_TOKEN),
            expected_execution_id=str(exec_id),
            expected_organization_id=str(org_id),
            action=WorkerHookAction.worker_started,
        )

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _SENSITIVE_RAW_TOKEN not in log_text
    # Digest is not sensitive but we still don't log it.
    digest = compute_worker_token_digest(_SENSITIVE_RAW_TOKEN)
    assert digest not in log_text


# --- Import purity --------------------------------------------------------


_FORBIDDEN_IMPORT_TOKENS = (
    "worker_runner",
    "worker_process",
    "http_transport",
    "celery",
    "kombu",
    "fastapi",
    "router",
    "service",
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


@pytest.mark.parametrize(
    "module",
    [
        credential_repository_module,
        credential_issuer_module,
        credential_verifier_module,
    ],
)
def test_credential_persistence_modules_import_purity(module: object) -> None:
    for name in _imported_modules(module):
        assert not any(token in name for token in _FORBIDDEN_IMPORT_TOKENS), (
            f"{module} must not import: {name}"
        )

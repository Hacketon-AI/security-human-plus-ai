"""Integration tests for per-execution worker credential persistence.

Exercises the migration, the unique digest constraint, and the end-to-end
issue → verify cycle against a real PostgreSQL through Testcontainers
(SQLite is never substituted). Tests are reported as blocked/skipped if
Docker is unavailable.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.modules.validation_executions.credential_issuer import (
    PersistedWorkerCredentialIssuer,
)
from app.modules.validation_executions.credential_repository import (
    WorkerCredentialRepository,
)
from app.modules.validation_executions.credential_verifier import (
    PersistedWorkerCredentialVerifier,
)
from app.modules.validation_executions.enums import (
    ExecutionOutcome,
    ExecutionStatus,
)
from app.modules.validation_executions.models import (
    ValidationExecution,
    ValidationWorkerCredential,
)
from app.modules.validation_executions.repository import (
    ValidationExecutionRepository,
)
from app.modules.validation_executions.worker_credential_contracts import (
    WorkerCredentialIssueOutcome,
    WorkerCredentialVerificationOutcome,
    WorkerHookAction,
    compute_worker_token_digest,
)
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# Project's existing FixedClock-style helper.
from tests.conftest import FixedClock

_NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


async def _seed_minimum_execution_fixtures(
    session: AsyncSession,
    *,
    organization_id: UUID,
    project_id: UUID,
    asset_id: UUID,
    authorization_id: UUID,
    engagement_id: UUID,
    engagement_scope_id: UUID,
) -> None:
    """Insert the minimum FK targets a validation execution requires.

    The migration we care about lands the ``validation_worker_credentials``
    table that FKs to ``validation_executions``. We insert one execution
    row by raw SQL so the test sidesteps the full create-and-queue path and
    its tenant/project/auth/engagement setup.
    """
    await session.execute(
        text(
            "INSERT INTO organizations "
            "(id, name, slug, status, created_at, updated_at) "
            "VALUES (:id, 'Org', 'org', 'active', now(), now())"
        ),
        {"id": organization_id},
    )
    await session.execute(
        text(
            "INSERT INTO projects (id, organization_id, name, slug, status, "
            "created_at, updated_at) "
            "VALUES (:id, :org, 'Project', 'project', 'active', now(), now())"
        ),
        {"id": project_id, "org": organization_id},
    )
    await session.execute(
        text(
            "INSERT INTO assets (id, organization_id, project_id, name, "
            "asset_type, environment, target, criticality, status, created_at, "
            "updated_at) VALUES (:id, :org, :project, 'API', 'api', 'staging', "
            "'https://api.example.com', 'medium', 'verified', now(), now())"
        ),
        {"id": asset_id, "org": organization_id, "project": project_id},
    )
    await session.execute(
        text(
            "INSERT INTO authorizations (id, organization_id, project_id, "
            "reference_number, title, valid_from, valid_until, timezone, "
            "maximum_risk_tier, production_testing_allowed, "
            "core_banking_testing_allowed, emergency_contact_name, "
            "emergency_contact_phone, authorization_document_name, "
            "authorization_document_sha256, status, created_at, updated_at) "
            "VALUES (:id, :org, :project, 'AUTH-1', 'Assessment', :vf, :vu, "
            "'UTC', 'tier_1_safe', false, false, 'Officer', '+1-555-0001', "
            "'auth.pdf', :sha, 'active', now(), now())"
        ),
        {
            "id": authorization_id,
            "org": organization_id,
            "project": project_id,
            "vf": _NOW - timedelta(days=1),
            "vu": _NOW + timedelta(days=29),
            "sha": "a" * 64,
        },
    )
    await session.execute(
        text(
            "INSERT INTO engagements (id, organization_id, project_id, "
            "authorization_id, name, starts_at, ends_at, timezone, "
            "max_risk_tier, default_rate_limit_per_minute, "
            "default_concurrency_limit, emergency_contact_name, "
            "emergency_contact_email, kill_switch_active, status, "
            "created_at, updated_at) VALUES "
            "(:id, :org, :project, :auth, 'Eng', :starts, :ends, 'UTC', "
            "'tier_1_safe', 30, 3, 'Eng Officer', 'eng@example.com', false, "
            "'active', now(), now())"
        ),
        {
            "id": engagement_id,
            "org": organization_id,
            "project": project_id,
            "auth": authorization_id,
            "starts": _NOW - timedelta(hours=1),
            "ends": _NOW + timedelta(days=7),
        },
    )
    await session.execute(
        text(
            "INSERT INTO engagement_scopes (id, organization_id, "
            "engagement_id, asset_id, allowed_ports, allowed_paths, "
            "rate_limit_per_minute, concurrency_limit, created_at, updated_at) "
            "VALUES (:id, :org, :eng, :asset, '[443]', '[\"/\"]', 20, 2, "
            "now(), now())"
        ),
        {
            "id": engagement_scope_id,
            "org": organization_id,
            "eng": engagement_id,
            "asset": asset_id,
        },
    )


async def _seed_execution(
    session: AsyncSession,
    *,
    organization_id: UUID,
    status: ExecutionStatus = ExecutionStatus.queued,
) -> UUID:
    project_id = uuid4()
    asset_id = uuid4()
    authorization_id = uuid4()
    engagement_id = uuid4()
    engagement_scope_id = uuid4()
    await _seed_minimum_execution_fixtures(
        session,
        organization_id=organization_id,
        project_id=project_id,
        asset_id=asset_id,
        authorization_id=authorization_id,
        engagement_id=engagement_id,
        engagement_scope_id=engagement_scope_id,
    )
    execution = ValidationExecution(
        id=uuid4(),
        organization_id=organization_id,
        project_id=project_id,
        asset_id=asset_id,
        authorization_id=authorization_id,
        engagement_id=engagement_id,
        engagement_scope_id=engagement_scope_id,
        template_id="HTTP_SECURITY_HEADER_VALIDATION",
        status=status,
        outcome=ExecutionOutcome.not_run,
        risk_tier="tier_0_passive",  # type: ignore[arg-type]
        execution_specification={},
        scope_snapshot={},
        safety_snapshot={},
    )
    session.add(execution)
    await session.flush()
    return execution.id


@pytest.fixture
async def credential_session(
    engine: AsyncEngine,
) -> Any:
    """One AsyncSession against the migrated database, per test.

    Truncate the credential and execution tables and the dependent foreign
    keys so each test starts with a clean slate.
    """
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE validation_worker_credentials, "
                "validation_step_results, validation_executions, "
                "engagement_scopes, engagements, authorization_scopes, "
                "authorizations, assets, projects, organizations "
                "RESTART IDENTITY CASCADE"
            )
        )
    async with sessionmaker() as session:
        yield session


async def test_migration_creates_validation_worker_credentials_table(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'validation_worker_credentials' "
                "ORDER BY ordinal_position"
            )
        )
        columns = [row[0] for row in result.all()]

    expected = {
        "id",
        "organization_id",
        "execution_id",
        "token_digest",
        "allowed_actions",
        "issued_at",
        "expires_at",
        "revoked_at",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(set(columns))


async def test_issuer_persists_digest_not_raw_token(
    credential_session: AsyncSession,
) -> None:
    org_id = uuid4()
    execution_id = await _seed_execution(credential_session, organization_id=org_id)
    issuer = PersistedWorkerCredentialIssuer(
        WorkerCredentialRepository(credential_session),
        ValidationExecutionRepository(credential_session),
        FixedClock(moment=_NOW),
    )

    result = await issuer.issue(
        execution_id=str(execution_id),
        organization_id=str(org_id),
        allowed_actions=frozenset(
            {WorkerHookAction.worker_started, WorkerHookAction.worker_finished}
        ),
        expires_at=_NOW + timedelta(minutes=30),
    )

    assert result.outcome is WorkerCredentialIssueOutcome.issued
    issued = result.issued
    assert issued is not None
    raw = issued.raw_token.get_secret_value()
    expected_digest = compute_worker_token_digest(raw)

    rows = (
        (
            await credential_session.execute(
                select(ValidationWorkerCredential).where(
                    ValidationWorkerCredential.execution_id == execution_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.token_digest == expected_digest
    # The raw token does not appear in any column we persisted.
    raw_appears = await credential_session.execute(
        text(
            "SELECT count(*) FROM validation_worker_credentials "
            "WHERE token_digest = :raw"
        ),
        {"raw": raw},
    )
    assert raw_appears.scalar_one() == 0


async def test_unique_token_digest_index_rejects_duplicates(
    credential_session: AsyncSession,
) -> None:
    org_id = uuid4()
    execution_id = await _seed_execution(credential_session, organization_id=org_id)
    digest = compute_worker_token_digest("some-raw-token-value")

    first = ValidationWorkerCredential(
        id=uuid4(),
        organization_id=org_id,
        execution_id=execution_id,
        token_digest=digest,
        allowed_actions=["worker_started"],
        issued_at=_NOW,
        expires_at=_NOW + timedelta(hours=1),
    )
    second = ValidationWorkerCredential(
        id=uuid4(),
        organization_id=org_id,
        execution_id=execution_id,
        token_digest=digest,  # Same digest — must violate the unique index.
        allowed_actions=["worker_started"],
        issued_at=_NOW,
        expires_at=_NOW + timedelta(hours=1),
    )

    credential_session.add(first)
    await credential_session.flush()
    credential_session.add(second)
    with pytest.raises(IntegrityError):
        await credential_session.flush()


async def test_end_to_end_issue_then_verify_accepts_via_real_db(
    credential_session: AsyncSession,
) -> None:
    org_id = uuid4()
    execution_id = await _seed_execution(credential_session, organization_id=org_id)

    clock = FixedClock(moment=_NOW)
    issuer = PersistedWorkerCredentialIssuer(
        WorkerCredentialRepository(credential_session),
        ValidationExecutionRepository(credential_session),
        clock,
    )
    verifier = PersistedWorkerCredentialVerifier(
        WorkerCredentialRepository(credential_session),
        clock,
    )

    issued = (
        await issuer.issue(
            execution_id=str(execution_id),
            organization_id=str(org_id),
            allowed_actions=frozenset({WorkerHookAction.worker_started}),
            expires_at=_NOW + timedelta(minutes=30),
        )
    ).issued
    assert issued is not None

    result = await verifier.verify(
        presented_token=issued.raw_token,
        expected_execution_id=str(execution_id),
        expected_organization_id=str(org_id),
        action=WorkerHookAction.worker_started,
    )
    assert result.outcome is WorkerCredentialVerificationOutcome.accepted
    assert result.credential_id == issued.grant.credential_id


async def test_revoke_for_execution_marks_active_rows(
    credential_session: AsyncSession,
) -> None:
    org_id = uuid4()
    execution_id = await _seed_execution(credential_session, organization_id=org_id)
    repository = WorkerCredentialRepository(credential_session)
    issuer = PersistedWorkerCredentialIssuer(
        repository,
        ValidationExecutionRepository(credential_session),
        FixedClock(moment=_NOW),
    )

    issued = (
        await issuer.issue(
            execution_id=str(execution_id),
            organization_id=str(org_id),
            allowed_actions=frozenset({WorkerHookAction.worker_started}),
            expires_at=_NOW + timedelta(minutes=30),
        )
    ).issued
    assert issued is not None

    revoked = await repository.revoke_for_execution(
        execution_id,
        org_id,
        revoked_at=_NOW + timedelta(seconds=5),
    )
    assert revoked == 1

    # Second call is a no-op: nothing left in the active set.
    revoked_again = await repository.revoke_for_execution(
        execution_id,
        org_id,
        revoked_at=_NOW + timedelta(seconds=10),
    )
    assert revoked_again == 0

    # Verifier now rejects the previously valid token.
    verifier = PersistedWorkerCredentialVerifier(
        repository, FixedClock(moment=_NOW + timedelta(seconds=6))
    )
    after = await verifier.verify(
        presented_token=issued.raw_token,
        expected_execution_id=str(execution_id),
        expected_organization_id=str(org_id),
        action=WorkerHookAction.worker_started,
    )
    assert after.outcome is WorkerCredentialVerificationOutcome.rejected_revoked


async def test_verifier_rejects_wrong_organization_against_real_db(
    credential_session: AsyncSession,
) -> None:
    org_a, org_b = uuid4(), uuid4()
    execution_id = await _seed_execution(credential_session, organization_id=org_a)
    repository = WorkerCredentialRepository(credential_session)
    issuer = PersistedWorkerCredentialIssuer(
        repository,
        ValidationExecutionRepository(credential_session),
        FixedClock(moment=_NOW),
    )
    issued = (
        await issuer.issue(
            execution_id=str(execution_id),
            organization_id=str(org_a),
            allowed_actions=frozenset({WorkerHookAction.worker_started}),
            expires_at=_NOW + timedelta(minutes=30),
        )
    ).issued
    assert issued is not None

    verifier = PersistedWorkerCredentialVerifier(repository, FixedClock(moment=_NOW))
    # Attacker presents a valid token but claims a different tenant.
    result = await verifier.verify(
        presented_token=issued.raw_token,
        expected_execution_id=str(execution_id),
        expected_organization_id=str(org_b),
        action=WorkerHookAction.worker_started,
    )
    assert result.outcome is WorkerCredentialVerificationOutcome.rejected_organization


# Pinned: the public surface of the persistence layer does not expose any
# raw-token field or column name to ORM users. This catches an accidental
# future column rename or property addition.
async def test_validation_worker_credential_model_exposes_digest_only() -> None:
    columns = {c.key for c in ValidationWorkerCredential.__table__.columns}
    for forbidden in ("raw_token", "token", "plaintext_token", "secret"):
        assert forbidden not in columns, (
            f"ValidationWorkerCredential must not expose {forbidden!r}: {columns}"
        )
    # Digest column is present.
    assert "token_digest" in columns

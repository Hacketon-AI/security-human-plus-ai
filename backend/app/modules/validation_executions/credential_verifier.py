"""Concrete per-execution worker credential verifier (persisted).

Looks up the persisted :class:`ValidationWorkerCredential` row by the
SHA-256 digest of the presented token, rebuilds the contract
:class:`WorkerCredentialGrant` from it, and runs the pure rules in
:func:`evaluate_worker_credential`. Implementations of
:class:`WorkerCredentialVerifier` (Step 2 of
``docs/validation-worker-credentials-design.md``).

The verifier is the read-side counterpart of
:mod:`credential_issuer`. It never persists, never logs a digest or token,
and always returns a typed :class:`WorkerCredentialVerificationResult` —
the call site (the worker hook) is responsible for mapping any non-
accepted outcome to a single indistinguishable 401.
"""

import logging

from pydantic import SecretStr

from app.modules.validation_executions.credential_repository import (
    WorkerCredentialRepository,
)
from app.modules.validation_executions.worker_credential_contracts import (
    WorkerCredentialGrant,
    WorkerCredentialVerificationOutcome,
    WorkerCredentialVerificationResult,
    WorkerHookAction,
    compute_worker_token_digest,
    evaluate_worker_credential,
)
from app.platform.clock import Clock

_logger = logging.getLogger("securescope.validation.credential_verifier")


class PersistedWorkerCredentialVerifier:
    """Verify a presented worker token against the persisted grant.

    Implements :class:`WorkerCredentialVerifier`. Stateless aside from the
    injected repository and clock; safe to construct per-request.
    """

    def __init__(
        self,
        credentials: WorkerCredentialRepository,
        clock: Clock,
    ) -> None:
        self._credentials = credentials
        self._clock = clock

    async def verify(
        self,
        *,
        presented_token: SecretStr,
        expected_execution_id: str,
        expected_organization_id: str,
        action: WorkerHookAction,
    ) -> WorkerCredentialVerificationResult:
        """Resolve the grant by digest and apply the contract evaluator.

        A token that does not resolve to any row is reported as
        :attr:`WorkerCredentialVerificationOutcome.rejected_token`. From a
        caller's perspective this is indistinguishable from a wrong-token
        rejection of a row that *did* exist — the response is the same 401
        regardless. Once a row is matched, :func:`evaluate_worker_credential`
        applies the organization / execution / action / revocation / expiry
        checks under the *injected* clock so the verifier is testable
        without freezing the system time.
        """
        try:
            presented_digest = compute_worker_token_digest(
                presented_token.get_secret_value()
            )
        except ValueError:
            # Empty token reaches the digest helper. Treat as a missing
            # credential — never echo the (empty) value.
            return WorkerCredentialVerificationResult(
                outcome=WorkerCredentialVerificationOutcome.rejected_token,
                failure="rejected_token",
            )

        row = await self._credentials.get_by_token_digest(presented_digest)
        if row is None:
            return WorkerCredentialVerificationResult(
                outcome=WorkerCredentialVerificationOutcome.rejected_token,
                failure="rejected_token",
            )

        grant = WorkerCredentialGrant(
            credential_id=str(row.id),
            organization_id=str(row.organization_id),
            execution_id=str(row.execution_id),
            token_digest=row.token_digest,
            allowed_actions=frozenset(
                WorkerHookAction(value) for value in row.allowed_actions
            ),
            issued_at=row.issued_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
        )

        result = evaluate_worker_credential(
            grant,
            presented_token=presented_token,
            expected_execution_id=expected_execution_id,
            expected_organization_id=expected_organization_id,
            action=action,
            now=self._clock.now(),
        )

        # Log only the structured outcome — never the digest, the token, or
        # any envelope-derived value. ``credential_id`` is opaque and safe
        # for audit.
        if result.outcome is WorkerCredentialVerificationOutcome.accepted:
            _logger.info(
                "worker credential %s accepted for execution %s action %s",
                result.credential_id,
                expected_execution_id,
                action.value,
            )
        else:
            _logger.warning(
                "worker credential verification %s for execution %s action %s",
                result.outcome.value,
                expected_execution_id,
                action.value,
            )
        return result

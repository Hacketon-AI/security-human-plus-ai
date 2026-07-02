"""Pure contracts for per-execution validation-worker credentials.

The control plane today authenticates the worker hooks (``worker-started`` /
``worker-finished``) with a single shared token (see :mod:`worker_auth`). That
token gates *any* worker action against *any* execution — far broader than the
least-privilege boundary in ``.claude/rules/security-boundaries.md`` (single-
scan, short-lived). This module fixes the *contract* for the per-execution
credential that replaces it; no DB, no FastAPI, no verifier implementation, and
no broker change are introduced here. See
``docs/validation-worker-credentials-design.md`` for the rollout plan and
``docs/validation-dispatch-broker-design.md`` → rollout Step 4 for the wider
context.

What lives here:

* The :class:`WorkerHookAction` enum naming the two hooks the credential may
  authorize.
* :class:`WorkerCredentialGrant` — the *server-side* row shape. It carries
  only the digest, never the raw token.
* :class:`IssuedWorkerCredential` — the value the issuer hands back to the
  worker bootstrap *exactly once*. It pairs the grant with a
  :class:`SecretStr` so the raw token never leaks via repr/log.
* :class:`WorkerCredentialIssueResult` /
  :class:`WorkerCredentialVerificationResult` — typed outcomes.
* :class:`WorkerCredentialIssuer` / :class:`WorkerCredentialVerifier` —
  Protocols for the future concrete implementations.
* :func:`generate_worker_token`, :func:`compute_worker_token_digest`,
  :func:`compare_worker_token_digests` — leaf helpers.
* :func:`evaluate_worker_credential` — the *pure* verification rules over a
  known grant. No I/O, no clock; the caller supplies ``now``.

What does **not** live here, by design (see import-purity tests):

* No FastAPI, no SQLAlchemy, no Celery, no worker_runner, no http_transport,
  no repositories, no services, no router. The contract is consumable by a
  future worker bootstrap that is import-clean of the API runtime.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import SecretStr

__all__ = [
    "IssuedWorkerCredential",
    "WorkerBootstrapSecretSource",
    "WorkerCredentialGrant",
    "WorkerCredentialHandoff",
    "WorkerCredentialIssueOutcome",
    "WorkerCredentialIssueResult",
    "WorkerCredentialIssuer",
    "WorkerCredentialResolution",
    "WorkerCredentialResolutionOutcome",
    "WorkerCredentialVerificationOutcome",
    "WorkerCredentialVerificationResult",
    "WorkerCredentialVerifier",
    "WorkerHookAction",
    "compare_worker_token_digests",
    "compute_worker_token_digest",
    "evaluate_worker_credential",
    "generate_worker_token",
]

# Token entropy: 32 bytes via ``secrets.token_urlsafe`` produces 43 url-safe
# base64 characters, comfortably above the 128-bit floor this contract requires.
# SHA-256 (64 hex chars) is the digest the server stores; longer hashes add
# nothing for a one-use, short-lived secret.
_TOKEN_ENTROPY_BYTES = 32


class WorkerHookAction(StrEnum):
    """A worker-side action a per-execution credential may authorize.

    These mirror the two ``worker-*`` API hooks. A credential may grant both
    (the common case — one worker drives the full lifecycle) or just one
    (defensive: a finalize-only credential cannot replay the start signal).
    The set is explicit so adding a new hook later requires a deliberate
    contract change, not an accidental expansion of authority.
    """

    worker_started = "worker_started"
    worker_finished = "worker_finished"


class WorkerCredentialIssueOutcome(StrEnum):
    """High-level outcome of one :class:`WorkerCredentialIssuer` call.

    ``issued`` — the issuer minted a credential and returned it once.
    ``rejected`` — the issuer refused (e.g. execution not eligible, action
    set empty). No leaky reason is encoded here; ``failure`` on the result
    carries a short safe category for audit.
    """

    issued = "issued"
    rejected = "rejected"


class WorkerCredentialVerificationOutcome(StrEnum):
    """Result of evaluating a presented credential against a known grant.

    The named rejections are useful for **server-side** audit and metrics;
    the worker hook still returns a single indistinguishable ``401`` to the
    caller (see :mod:`worker_auth` for the existing equality-of-failures
    rule). Every non-accepted outcome means the request is refused.
    """

    accepted = "accepted"
    # ruff S105 trips on the ``*_token = "...token..."`` shape; this is an
    # outcome label, not a credential value.
    rejected_token = "rejected_token"  # noqa: S105
    rejected_execution = "rejected_execution"
    rejected_organization = "rejected_organization"
    rejected_action = "rejected_action"
    rejected_revoked = "rejected_revoked"
    rejected_expired = "rejected_expired"


@dataclass(frozen=True, slots=True)
class WorkerCredentialGrant:
    """The server-side record of one per-execution worker credential.

    Carries **only** the SHA-256 ``token_digest``; the raw token is never
    stored. ``credential_id`` is an opaque server identifier (UUID-shaped in
    practice) that audit events reference; it is *not* the digest. The grant
    is bound to ``organization_id`` (tenant isolation), ``execution_id``
    (single-scan scope), and an explicit ``allowed_actions`` set. Lifecycle
    is anchored by ``issued_at`` / ``expires_at`` plus an optional
    ``revoked_at`` for immediate revocation; the credential is invalid the
    moment the wall clock reaches either boundary.
    """

    credential_id: str
    organization_id: str
    execution_id: str
    token_digest: str
    allowed_actions: frozenset[WorkerHookAction]
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class IssuedWorkerCredential:
    """The value an issuer hands the worker bootstrap exactly once.

    Pairs the persisted :class:`WorkerCredentialGrant` with the raw token.
    The raw token is wrapped in :class:`SecretStr` so it never appears in
    ``repr``, structured logs, or tracebacks — the worker bootstrap calls
    ``raw_token.get_secret_value()`` once to hand it to the worker, then
    drops the reference. Re-issuing the same credential is not supported:
    if the bootstrap loses the value, a new credential must be minted (and
    the old one revoked).
    """

    grant: WorkerCredentialGrant
    raw_token: SecretStr


@dataclass(frozen=True, slots=True)
class WorkerCredentialHandoff:
    """Side-channel carrier for a freshly issued per-execution credential.

    The dispatch path mints a credential (see :mod:`credential_issuer`) and
    must get its *raw token* to the worker that will run the execution — but
    **never** through the broker. This value object is that side-channel
    carrier: it pairs the opaque, non-sensitive identifiers with the raw
    token so the dispatcher/publisher boundary can hand it to a worker
    bootstrap out of band.

    Hard invariants (enforced by tests, see
    ``docs/validation-worker-credentials-design.md`` → broker envelope rule):

    * It is **never** serialized into :class:`WorkerDispatchPayload` or
      ``ValidationDispatchEnvelope`` — the broker message stays
      credential-free.
    * It is **never** logged, placed in an audit payload, or returned from
      the API.
    * It lives only in process memory, from issuance to the dispatcher
      boundary.

    ``raw_token`` is wrapped in :class:`SecretStr` so it cannot leak via
    ``repr``, a structured log, or a traceback. A consumer calls
    ``raw_token.get_secret_value()`` exactly once when handing it to the
    worker bootstrap, then drops the reference. ``expires_at`` mirrors the
    grant's expiry so the bootstrap can refuse to launch a worker with an
    already-expired credential without re-reading the row.
    """

    execution_id: str
    credential_id: str
    raw_token: SecretStr
    expires_at: datetime


class WorkerCredentialResolutionOutcome(StrEnum):
    """Result of asking a bootstrap secret source for a raw worker token.

    The worker bootstrap resolves the per-execution credential *outside* the
    broker envelope (see ``docs/validation-worker-credentials-design.md`` →
    Step 4B). Each outcome is a hard, typed reason the bootstrap acts on:

    * ``found`` — the source held a live token for this execution and
      returned it; the raw token is present on the resolution.
    * ``missing`` — no handoff was registered for this execution (or it was
      already consumed under one-time semantics).
    * ``expired`` — a handoff existed but its ``expires_at`` has passed; the
      bootstrap must not launch a worker with an already-dead credential.
    * ``invalid_reference`` — the lookup key was malformed (e.g. empty
      execution id) so no lookup was attempted.
    * ``source_unavailable`` — the underlying store could not be reached
      (transient); the bootstrap fails closed and does not run the scan.
    """

    found = "found"
    missing = "missing"
    expired = "expired"
    invalid_reference = "invalid_reference"
    source_unavailable = "source_unavailable"


@dataclass(frozen=True, slots=True)
class WorkerCredentialResolution:
    """Structured result of a :class:`WorkerBootstrapSecretSource` lookup.

    On :attr:`WorkerCredentialResolutionOutcome.found` the ``raw_token`` is
    present (wrapped in :class:`SecretStr` so it cannot leak via repr/log)
    and ``expires_at`` mirrors the credential's expiry. On every other
    outcome ``raw_token`` is ``None`` — the bootstrap fails closed without a
    token. The raw token is never rendered to a string, serialized, or
    logged.
    """

    outcome: WorkerCredentialResolutionOutcome
    raw_token: SecretStr | None = None
    expires_at: datetime | None = None


class WorkerBootstrapSecretSource(Protocol):
    """Resolves a per-execution raw worker token from a side-channel.

    The worker bootstrap consults this *instead of* reading the token from
    the broker envelope — the envelope stays credential-free. Implementations
    look the credential up by ``execution_id`` (the only identifier the
    worker reliably holds from the validated envelope payload) and return a
    typed :class:`WorkerCredentialResolution`. Implementations must never
    log the token, never serialize it to JSON, and never return it on a
    non-``found`` outcome.
    """

    async def resolve(self, *, execution_id: str) -> WorkerCredentialResolution: ...


@dataclass(frozen=True, slots=True)
class WorkerCredentialIssueResult:
    """Structured outcome of one issuance attempt.

    Successful issuance carries the :class:`IssuedWorkerCredential`;
    rejection carries a short safe ``failure`` category (e.g.
    ``"execution_not_found"``, ``"empty_actions"``) — never a raw exception
    or any token value.
    """

    outcome: WorkerCredentialIssueOutcome
    issued: IssuedWorkerCredential | None = None
    failure: str | None = None


@dataclass(frozen=True, slots=True)
class WorkerCredentialVerificationResult:
    """Structured outcome of one verification call.

    On ``accepted`` the result carries the ``credential_id`` so the hook
    handler can attach it to the audit record. On any rejection no
    identifier is leaked — the hook surfaces an indistinguishable 401 to
    the caller, while the verifier records the structured outcome for
    server-side audit. ``failure`` is the safe category mirroring
    ``outcome`` — useful for log lines that should not unpack the enum.
    """

    outcome: WorkerCredentialVerificationOutcome
    credential_id: str | None = None
    failure: str | None = None


class WorkerCredentialIssuer(Protocol):
    """Mint a fresh per-execution worker credential at dispatch time.

    Implementations persist the :class:`WorkerCredentialGrant` (digest +
    scope + lifecycle) and return the raw token exactly once via
    :class:`IssuedWorkerCredential`. They must not log, return, persist, or
    side-channel the raw token anywhere else.
    """

    async def issue(
        self,
        *,
        execution_id: str,
        organization_id: str,
        allowed_actions: frozenset[WorkerHookAction],
        expires_at: datetime,
    ) -> WorkerCredentialIssueResult: ...


class WorkerCredentialVerifier(Protocol):
    """Verify a presented worker token against the persisted grant.

    Implementations look up the grant by digest, then apply the rules in
    :func:`evaluate_worker_credential`. Any failure mode returns a typed
    :class:`WorkerCredentialVerificationResult` — never raises through the
    hook handler, so the response never depends on a Python traceback.
    """

    async def verify(
        self,
        *,
        presented_token: SecretStr,
        expected_execution_id: str,
        expected_organization_id: str,
        action: WorkerHookAction,
    ) -> WorkerCredentialVerificationResult: ...


def generate_worker_token() -> SecretStr:
    """Mint a fresh high-entropy worker token.

    Returns a :class:`SecretStr` so the caller cannot accidentally log the
    raw value. The token is url-safe base64 of 32 random bytes (≈ 256 bits
    of entropy via :func:`secrets.token_urlsafe`).
    """
    return SecretStr(secrets.token_urlsafe(_TOKEN_ENTROPY_BYTES))


def compute_worker_token_digest(raw_token: str) -> str:
    """Return the SHA-256 hex digest of a raw worker token.

    The digest is what the server persists in
    :attr:`WorkerCredentialGrant.token_digest`; the raw token is never
    stored. Empty input is rejected — an empty token would compute a fixed
    digest that a caller could brute-force against.
    """
    if not raw_token:
        raise ValueError("raw_token must be a non-empty string")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def compare_worker_token_digests(stored: str, presented: str) -> bool:
    """Constant-time digest equality.

    Wraps :func:`hmac.compare_digest` so callers do not have to remember
    the constant-time idiom. A length mismatch already returns ``False``
    safely; the comparison is non-short-circuiting on equal-length inputs.
    """
    return hmac.compare_digest(stored, presented)


def evaluate_worker_credential(
    grant: WorkerCredentialGrant,
    *,
    presented_token: SecretStr,
    expected_execution_id: str,
    expected_organization_id: str,
    action: WorkerHookAction,
    now: datetime,
) -> WorkerCredentialVerificationResult:
    """Apply the per-execution verification rules to a known grant.

    Pure: no I/O, no clock read, no logging. The caller supplies ``now``
    so the same evaluator is testable under any wall-clock scenario and
    re-usable from a future async verifier without surprise.

    Checks, in this order:

    1. **Digest equality**, constant-time. A mismatch returns
       :attr:`WorkerCredentialVerificationOutcome.rejected_token`.
    2. **Organization boundary**. The grant's tenant must match the
       execution row's tenant; any drift is
       :attr:`WorkerCredentialVerificationOutcome.rejected_organization`.
    3. **Execution scope**. The grant is for one execution; the path
       parameter must match.
    4. **Action allow-list**. The credential authorizes only the
       :class:`WorkerHookAction` set the issuer specified.
    5. **Revocation**. ``revoked_at`` set and ``now`` past it is a
       hard-stop refusal.
    6. **Expiry**. ``now >= expires_at`` is refused — the boundary is
       exclusive so a credential cannot fire on the deadline tick.
    """
    presented_digest = compute_worker_token_digest(presented_token.get_secret_value())
    if not compare_worker_token_digests(grant.token_digest, presented_digest):
        return WorkerCredentialVerificationResult(
            outcome=WorkerCredentialVerificationOutcome.rejected_token,
            failure="rejected_token",
        )
    if grant.organization_id != expected_organization_id:
        return WorkerCredentialVerificationResult(
            outcome=WorkerCredentialVerificationOutcome.rejected_organization,
            failure="rejected_organization",
        )
    if grant.execution_id != expected_execution_id:
        return WorkerCredentialVerificationResult(
            outcome=WorkerCredentialVerificationOutcome.rejected_execution,
            failure="rejected_execution",
        )
    if action not in grant.allowed_actions:
        return WorkerCredentialVerificationResult(
            outcome=WorkerCredentialVerificationOutcome.rejected_action,
            failure="rejected_action",
        )
    if grant.revoked_at is not None and now >= grant.revoked_at:
        return WorkerCredentialVerificationResult(
            outcome=WorkerCredentialVerificationOutcome.rejected_revoked,
            failure="rejected_revoked",
        )
    if now >= grant.expires_at:
        return WorkerCredentialVerificationResult(
            outcome=WorkerCredentialVerificationOutcome.rejected_expired,
            failure="rejected_expired",
        )
    return WorkerCredentialVerificationResult(
        outcome=WorkerCredentialVerificationOutcome.accepted,
        credential_id=grant.credential_id,
    )

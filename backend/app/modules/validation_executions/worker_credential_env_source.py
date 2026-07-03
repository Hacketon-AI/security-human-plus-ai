"""Production container-env side-channel for the per-execution worker token.

This is the production :class:`WorkerBootstrapSecretSource` (design Option 1 in
``docs/validation-worker-credentials-design.md`` → Step 4B). The dispatch path
mints a per-execution credential and gets its raw token to the worker **out of
band** — never through the broker envelope. In production that side-channel is
the worker container's own environment: the orchestrator that launches a fresh,
per-execution container injects the raw token (and its scope) as environment
variables at start time, and this source reads them back once.

Env var contract (all under ``SECURESCOPE_WORKER_CREDENTIAL_``):

* ``SECURESCOPE_WORKER_CREDENTIAL_TOKEN`` — the raw token. Wrapped in
  :class:`SecretStr` the instant it is read; never logged, rendered, or
  serialized here.
* ``SECURESCOPE_WORKER_CREDENTIAL_EXECUTION_ID`` — the execution this container
  was launched to run. A resolve for any *other* execution id fails closed, so
  a container secret can never authenticate a different run.
* ``SECURESCOPE_WORKER_CREDENTIAL_EXPIRES_AT`` — ISO-8601, timezone-aware, UTC.
  Mirrors the grant's expiry so the source can refuse an already-dead credential
  without a database read (the same rule the dev registry and the dispatch-time
  handoff enforce).

Cross-execution isolation ultimately comes from the *per-execution container*
(a fresh container, a fresh env, a fresh token). The in-process consume-once
flag here only stops a redelivered broker message handled by the **same** worker
process from re-reading the token a second time — mirroring the dev registry's
one-time semantics.

Import purity: standard library, the pure credential contract, the platform
clock, and Pydantic's ``SecretStr`` only. No FastAPI, SQLAlchemy, repositories,
services, routers, dispatcher, Celery, or ``app.main`` (pinned by an AST test,
matching the dev registry and the worker bootstrap).
"""

import logging
import os
from collections.abc import Mapping
from datetime import datetime
from threading import Lock

from pydantic import SecretStr

from app.modules.validation_executions.worker_credential_contracts import (
    WorkerCredentialResolution,
    WorkerCredentialResolutionOutcome,
)
from app.platform.clock import Clock

__all__ = [
    "ENV_EXECUTION_ID",
    "ENV_EXPIRES_AT",
    "ENV_TOKEN",
    "EnvironmentWorkerCredentialSource",
]

_logger = logging.getLogger("securescope.validation.worker_credential_env_source")

# The per-execution container injects exactly these three variables. Kept as
# module constants so the launcher (operational wiring) and this reader agree on
# one spelling, and tests reference the names rather than duplicating strings.
ENV_TOKEN = "SECURESCOPE_WORKER_CREDENTIAL_TOKEN"  # noqa: S105 - env var name, not a secret value
ENV_EXECUTION_ID = "SECURESCOPE_WORKER_CREDENTIAL_EXECUTION_ID"
ENV_EXPIRES_AT = "SECURESCOPE_WORKER_CREDENTIAL_EXPIRES_AT"


class EnvironmentWorkerCredentialSource:
    """Resolve the per-execution raw worker token from the container environment.

    Implements :class:`WorkerBootstrapSecretSource`. Construct one per worker
    process; ``env`` defaults to :data:`os.environ` and is injectable so tests
    supply an explicit mapping instead of mutating global process state. The
    ``clock`` drives the exclusive expiry check (a real worker passes
    :class:`SystemClock`).

    A single credential is served at most once (``resolve`` consumes it), and
    only for the execution named in :data:`ENV_EXECUTION_ID`; every other case
    fails closed with a typed :class:`WorkerCredentialResolution` carrying no
    token.
    """

    def __init__(self, clock: Clock, *, env: Mapping[str, str] | None = None) -> None:
        self._clock = clock
        source = os.environ if env is None else env
        # Extract only the three variables this source needs, at construction.
        # The container's env is fixed for the life of the process, so reading
        # once is safe; extracting (rather than snapshotting all of os.environ)
        # keeps *other* process secrets — the DB DSN, broker URL — out of this
        # object, and the raw token is wrapped in ``SecretStr`` immediately so it
        # never lingers as a plain string (rules/data-handling.md → boundary).
        raw_token = source.get(ENV_TOKEN, "").strip()
        self._token: SecretStr | None = SecretStr(raw_token) if raw_token else None
        self._execution_id = source.get(ENV_EXECUTION_ID, "").strip()
        self._raw_expires_at = source.get(ENV_EXPIRES_AT, "").strip()
        self._lock = Lock()
        self._consumed = False

    async def resolve(self, *, execution_id: str) -> WorkerCredentialResolution:
        """Resolve and consume this container's credential for ``execution_id``.

        Outcome mapping (fail-closed by default — only ``found`` carries a
        token):

        * empty requested id → ``invalid_reference`` (no env read).
        * already consumed, or any required var missing/blank, or the container's
          ``EXECUTION_ID`` does not match the request → ``missing``.
        * ``EXPIRES_AT`` not a timezone-aware ISO-8601 instant →
          ``source_unavailable`` (misconfigured injection; never guess an
          expiry).
        * ``now >= expires_at`` (exclusive) → ``expired`` (and consumed).
        * otherwise → ``found`` with the raw token and mirrored expiry (and
          consumed).
        """
        if not execution_id:
            return WorkerCredentialResolution(
                outcome=WorkerCredentialResolutionOutcome.invalid_reference
            )

        now = self._clock.now()
        with self._lock:
            if self._consumed:
                # A redelivered message in this same process cannot re-read the
                # token; a fresh run gets a fresh container with a fresh env.
                return WorkerCredentialResolution(
                    outcome=WorkerCredentialResolutionOutcome.missing
                )

            if (
                self._token is None
                or not self._execution_id
                or not self._raw_expires_at
            ):
                _logger.warning(
                    "worker credential env incomplete for execution %s; "
                    "failing closed (missing)",
                    execution_id,
                )
                return WorkerCredentialResolution(
                    outcome=WorkerCredentialResolutionOutcome.missing
                )

            if self._execution_id != execution_id:
                # This container's secret belongs to a different execution. Never
                # hand it to a client for the requested run.
                _logger.warning(
                    "worker credential env is scoped to a different execution "
                    "than requested (%s); failing closed (missing)",
                    execution_id,
                )
                return WorkerCredentialResolution(
                    outcome=WorkerCredentialResolutionOutcome.missing
                )

            expires_at = _parse_expiry(self._raw_expires_at)
            if expires_at is None:
                # A malformed expiry is an injection bug, not a benign miss.
                # Consume so a retry in-process cannot spin on the same bad env.
                self._consumed = True
                _logger.warning(
                    "worker credential env carried an unparseable expiry for "
                    "execution %s; failing closed (source_unavailable)",
                    execution_id,
                )
                return WorkerCredentialResolution(
                    outcome=WorkerCredentialResolutionOutcome.source_unavailable
                )

            # Consume regardless of expiry so the token is served at most once.
            self._consumed = True

            # Expiry is exclusive: a credential at its expiry instant is dead.
            if now >= expires_at:
                _logger.warning(
                    "worker credential for execution %s is already expired; "
                    "failing closed (expired)",
                    execution_id,
                )
                return WorkerCredentialResolution(
                    outcome=WorkerCredentialResolutionOutcome.expired
                )

        return WorkerCredentialResolution(
            outcome=WorkerCredentialResolutionOutcome.found,
            raw_token=self._token,
            expires_at=expires_at,
        )


def _parse_expiry(raw: str) -> datetime | None:
    """Parse a timezone-aware ISO-8601 expiry, or ``None`` if unusable.

    A naive datetime (no tzinfo) is rejected: comparing it against a
    timezone-aware ``now`` would raise, and silently assuming UTC could extend a
    credential's validity past its real deadline. Fail closed instead.
    """
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed

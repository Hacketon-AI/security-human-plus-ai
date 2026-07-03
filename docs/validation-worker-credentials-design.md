# Per-Execution Validation Worker Credential — Design

## Purpose

This document defines the credential model that authenticates an isolated
worker against the control-plane `worker-started` / `worker-finished` hooks
once the production broker pipeline is enabled. It is the prerequisite for
Step 4 of `docs/validation-dispatch-broker-design.md`'s rollout plan: the
production worker bootstrap must not enable Celery until per-execution
credentials are in place.

This document is design + contract only. The pure types live in
`app/modules/validation_executions/worker_credential_contracts.py`. No DB
schema, no verifier wiring, no broker change, and no worker bootstrap
land in this change.

## Current shared-token limitation

Today, both worker hooks authenticate against a single
`Settings.worker_auth_token` (see `worker_auth.py`):

- The token is identical for every execution and every worker.
- A worker holding the token can drive `worker-started` / `worker-finished`
  for **any** execution, not just the one it was dispatched to run.
- The token is long-lived: it lives in deployed-environment configuration
  and rotates only by operator action.
- Compromising one worker container compromises the entire fleet's worker
  hooks across all tenants and executions until the shared token is
  rotated.

This is the gap `.claude/rules/security-boundaries.md` (worker credentials
must be short-lived, least-privilege, single-scan) closes once
per-execution credentials are wired.

## Target lifecycle

A per-execution worker credential is **issued at dispatch time**, **scoped
to one execution and one tenant**, **authorizes a narrow set of hook
actions**, **expires by wall clock**, and **may be revoked immediately**.
Its raw token leaves the issuer exactly once — to the worker bootstrap —
and the server stores only a SHA-256 digest.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Dispatch (control plane)                     │
│                                                                 │
│   service.create_and_queue ─┐                                   │
│                             │                                   │
│                             ▼                                   │
│             ┌──────────────────────────────┐                    │
│             │   WorkerCredentialIssuer     │                    │
│             │   .issue(execution_id,       │                    │
│             │           organization_id,   │                    │
│             │           allowed_actions,   │                    │
│             │           expires_at)        │                    │
│             └──────────────┬───────────────┘                    │
│                            │ persists                           │
│                            │  ┌─────────────────────────┐       │
│                            └─►│ WorkerCredentialGrant    │       │
│                               │  credential_id           │       │
│                               │  organization_id         │       │
│                               │  execution_id            │       │
│                               │  token_digest (SHA-256) │       │
│                               │  allowed_actions         │       │
│                               │  issued_at / expires_at  │       │
│                               │  revoked_at?             │       │
│                               └─────────────────────────┘       │
│                                                                 │
│   IssuedWorkerCredential(raw_token: SecretStr) ─────────┐       │
└─────────────────────────────────────────────────────────┼───────┘
                                                          │
                                                          │  side-channel
                                                          │  (not the broker)
                                                          ▼
                                  ┌──────────────────────────────┐
                                  │   Worker bootstrap            │
                                  │   - reads raw_token once      │
                                  │   - sets it on the worker env │
                                  │     or container secret       │
                                  └────────────┬─────────────────┘
                                               │
┌──────────────────────────────────────────────┼─────────────────┐
│                Worker process (isolated)      │                 │
│                                               ▼                 │
│   POST /api/v1/validation-executions/{id}/worker-started        │
│     X-Worker-Authorization: <raw_token>                         │
│                       ▲                                         │
│                       └── ValidationDispatchEnvelope            │
│                           (no raw token, no credential_id)      │
└─────────────────────────────────────────────────────────────────┘

           Control plane verify path
           ─────────────────────────
           ┌──────────────────────────────────────────────┐
           │ WorkerCredentialVerifier.verify(...)         │
           │   1. compute digest of presented token       │
           │   2. lookup grant by digest                  │
           │   3. evaluate_worker_credential(...)         │
           │        - digest match (constant-time)        │
           │        - organization match                  │
           │        - execution match                     │
           │        - action allowed                      │
           │        - not revoked                         │
           │        - not expired                         │
           └────────────────┬─────────────────────────────┘
                            │
                            ▼
                  accepted | rejected_*
```

## Issue flow

The issuer is called inside the dispatch transaction — the same
transaction that freezes snapshots, persists the execution row, and hands
the payload to the publisher seam:

1. `generate_worker_token()` mints a `SecretStr` carrying ~256 bits of
   entropy via `secrets.token_urlsafe(32)`.
2. `compute_worker_token_digest(raw_token)` computes the SHA-256 hex
   digest the row will store.
3. The issuer persists a `WorkerCredentialGrant` row with
   `credential_id` (opaque, server-assigned), `organization_id`,
   `execution_id`, `token_digest`, `allowed_actions`, `issued_at`,
   `expires_at`. `revoked_at` starts `None`.
4. The issuer returns `IssuedWorkerCredential(grant, raw_token)` to the
   worker bootstrap. The raw token is **not** persisted anywhere on the
   control plane — only the digest is.
5. Re-issuance is **not** supported. If the bootstrap loses the value, a
   new credential is minted; the old one stays in the row until expiry
   or explicit revocation.

Issuance constraints (rejected with a typed `WorkerCredentialIssueResult`
of outcome `rejected` + a short safe `failure`):

- The execution must exist and be in a pre-`executing` state.
- `allowed_actions` must be a non-empty subset of `WorkerHookAction`.
- `expires_at` must lie inside the engagement testing window and must
  not exceed a configured hard cap (e.g. 24 h) — well-bounded blast
  radius even if a token is leaked.
- The issuer never returns the digest in the result — only the raw
  token, exactly once.

## Verify flow

The hook handler resolves the worker context via the verifier:

1. Read the `X-Worker-Authorization` header. (No new header is required;
   the existing one carries the per-execution raw token.)
2. Compute the SHA-256 digest of the presented token.
3. Look up the matching `WorkerCredentialGrant` by digest. The
   `token_digest` column has a unique index, so a hit is unambiguous;
   absence is a rejection.
4. Apply `evaluate_worker_credential(grant, ...)`:
   - **Digest equality** (constant-time, via `hmac.compare_digest`).
     Failure → `rejected_token`.
   - **Organization boundary**: the grant's `organization_id` must
     equal the execution row's `organization_id`. Failure →
     `rejected_organization`.
   - **Execution scope**: the grant's `execution_id` must equal the
     path parameter. Failure → `rejected_execution`.
   - **Action allow-list**: the hook (`worker_started` /
     `worker_finished`) must appear in `allowed_actions`. Failure →
     `rejected_action`.
   - **Revocation**: `revoked_at` set and `now >= revoked_at` →
     `rejected_revoked`.
   - **Expiry**: `now >= expires_at` → `rejected_expired`.
5. The hook handler surfaces a single indistinguishable 401 on any
   non-accepted outcome — failure-mode equality is preserved from the
   existing `worker_auth.WorkerAuthenticationFailed` contract. The
   structured outcome is recorded server-side for audit; **never** in
   the response body.

Duplicate worker-finished remains idempotent **after** verification
succeeds. The idempotent service-layer rules (see
`docs/validation-dispatch-broker-design.md` → idempotency) are unaffected.

## Expiry and revocation

- **Expiry** is wall-clock based and exclusive: a credential whose
  `expires_at == now` is already expired.
- **Default cap**: `expires_at` cannot exceed a configured hard cap
  (proposed: 24 hours, configurable per environment). A typical scan
  finishes in minutes; the cap exists so a leaked token does not retain
  validity beyond the engagement window.
- **Revocation** is set by writing `revoked_at` on the grant row. It is
  immediate (no broadcast required — the verifier reads the column on
  every check). Revocation triggers:
  - Operator action (kill switch escalation, suspected compromise).
  - Terminal lifecycle transitions of the execution (a credential whose
    execution is `succeeded` / `failed` / `cancelled` / `blocked` should
    be revoked so a redelivery cannot resurrect it).
- The grant row is retained after expiry/revocation for audit; only the
  digest is stored, so retention does not retain a usable secret.

## Broker envelope rule

The raw token **never** appears in:

- `ValidationDispatchEnvelope.payload` or any other envelope field.
- `WorkerDispatchPayload.execution_specification`,
  `scope_snapshot`, or `safety_snapshot`.
- Any logging, structured event, or error message.
- Any audit record beyond the `credential_id` reference.

This is enforced by the existing `dispatch_serialization` JSON-safety
check (no `SecretStr`/bytes/non-JSON values reach the envelope), the
`broker_contracts._assert_json_safe` invariant, and the test
`test_worker_dispatch_payload_does_not_carry_raw_token` in the
credential contracts test suite.

The credential reaches the worker via a **side-channel** the worker
bootstrap controls — not via the broker message. As of Step 4A the
dispatch path carries the raw token to the dispatcher boundary in a
`WorkerCredentialHandoff` (pure, frozen, `raw_token` wrapped in
`SecretStr`); it lives only in process memory between the issuer and the
dispatcher and is never serialized, logged, audited, or returned. The raw
token therefore exists in exactly three transient places — the issuer's
return value, the handoff, and (eventually) the worker's environment —
and nowhere persistent but the SHA-256 digest column. Acceptable options
for the bootstrap step that consumes the handoff (Step 4B):

1. **Worker container secret**: the bootstrap writes the raw token to
   the worker container's environment at start time. The bootstrap
   process holds the value briefly, the worker reads it once, and the
   secret is rotated per execution by spinning a fresh container.
2. **Out-of-band fetch**: the bootstrap mints the credential, hands it
   to a tightly-locked-down credential service keyed by
   `execution_id`, and the worker fetches it once by `credential_id`
   (which *may* live in the envelope as a non-sensitive identifier).
   The credential service authenticates the worker by a fleet identity
   distinct from the worker token.
3. **Envelope-with-reference**: the envelope carries a non-sensitive
   `credential_id` only — the raw token still travels by side-channel.
   This is the only case where the envelope contract would change; it
   requires explicit re-review and is **not** part of this design.

Default for the bootstrap step: option 1 (container env) — simplest,
no new service, smallest blast radius (broker carries nothing
credential-related).

## Logging and data handling

- The raw token is wrapped in `SecretStr` so it cannot accidentally
  appear in `repr`, structured logs, or tracebacks.
- The issuer never logs `IssuedWorkerCredential` beyond
  `credential_id`.
- The verifier logs `(execution_id, action, outcome.value)` only —
  never the digest, the presented token, or a raw exception.
- Audit events reference `credential_id`, not the digest.

These rules layer on top of the existing
`.claude/rules/data-handling.md` posture; the credential module does
not relax any of them.

## Rollout plan

1. **Contracts and design** *(landed)*: pure types,
   `evaluate_worker_credential`, the digest/comparison helpers, and
   this document. Production keeps using the shared token; nothing is
   wired.
2. **DB persistence + verifier implementation** *(landed)*:
   - The Alembic migration `0007_worker_credentials` creates the
     `validation_worker_credentials` table with the column set
     described above and four indexes:
     `uq_validation_worker_credential_token_digest` (unique on
     `token_digest`), and supporting indexes on `organization_id`,
     `execution_id`, and `expires_at`. The unique digest index is the
     deterministic key the verifier looks up; collisions are rejected
     at the database before the application sees them.
   - `ValidationWorkerCredential` (in
     `app/modules/validation_executions/models.py`) carries
     `id`, `organization_id`, `execution_id`, `token_digest`,
     `allowed_actions` (JSON list of `WorkerHookAction` values),
     `issued_at`, `expires_at`, `revoked_at`, plus the standard
     server-managed `created_at` / `updated_at` from
     `TimestampMixin`. There is **no** raw-token column.
   - `WorkerCredentialRepository` exposes four narrow methods:
     `add`, `get_by_token_digest` (the only non-tenant-scoped read,
     used by the verifier), `list_active_for_execution`
     (tenant-scoped), and `revoke_for_execution` (idempotent — a row
     already carrying `revoked_at` is skipped).
   - `PersistedWorkerCredentialIssuer` implements
     `WorkerCredentialIssuer`. It refuses with a typed
     `WorkerCredentialIssueResult(outcome=rejected, failure=...)` on:
     `empty_actions` (empty `allowed_actions`), `invalid_expiry`
     (`expires_at` not in the future or beyond the hard TTL cap of
     **24 hours**, `DEFAULT_CREDENTIAL_HARD_TTL` — configurable per
     issuer), `execution_not_found` (no row matches the supplied
     tenant, *including* malformed UUID strings), and
     `execution_not_issuable` (the row exists but is in a terminal
     status: `succeeded` / `failed` / `cancelled` / `blocked`, or in
     `draft`). On success it generates the raw token via
     `generate_worker_token()`, persists only the SHA-256 digest, and
     returns the raw token exactly once inside
     `IssuedWorkerCredential`. Logs reference only the assigned
     `credential_id` — never the raw token, the digest, or any
     payload.
   - `PersistedWorkerCredentialVerifier` implements
     `WorkerCredentialVerifier`. It computes the digest, looks the
     row up by `get_by_token_digest`, rebuilds the
     `WorkerCredentialGrant`, and delegates to the pure
     `evaluate_worker_credential` rules (digest → organization →
     execution → action → revocation → expiry). A missing row and an
     empty presented token both resolve to `rejected_token`.
   - Persistence-layer import purity is pinned by an AST test:
     `credential_repository.py`, `credential_issuer.py`, and
     `credential_verifier.py` import nothing from `worker_runner` /
     `worker_process` / `http_transport` / `celery` / `fastapi` /
     `router` / `service` / `app.main`.
   - The worker hook (`worker_auth.py`) is **not yet upgraded** —
     production hook verification still uses the shared token. That
     is Step 3.
3. **Worker hook verification upgrade** *(landed)*:
   - The single shared-token comparison in `worker_auth.py` has been
     replaced by two action-specific dependencies —
     `require_worker_started_context` and
     `require_worker_finished_context` — both built on the same
     internal `_authenticate(...)` core. Each receives `execution_id`
     from the route path, looks the credential row up by digest,
     hands the result to `PersistedWorkerCredentialVerifier`, and
     returns a `WorkerContext` carrying `execution_id`,
     `organization_id`, `credential_id`, `action`, and a
     `worker_reference` audit actor (the `credential_id` on the
     per-execution path; `"shared-token-fallback"` on the legacy
     path).
   - `WorkerContext` is now a frozen value object with explicit
     fields; `worker_reference` continues to feed
     `audit.record_execution_event`, so audit events distinguish
     per-credential workers from the legacy shared-token caller.
   - The shared `Settings.worker_auth_token` survives behind the new
     `Settings.worker_shared_token_fallback_enabled` flag — **default
     off in every environment**, including dev/test. Tests that drive
     hooks with the legacy token enable the flag explicitly (the
     `validation_app` fixture does so for backwards-compat coverage);
     Step-3-specific tests assert the default-off behaviour against
     an unconfigured app.
   - Every shared-token success emits a single deprecation warning
     to `securescope.validation.worker_auth` — the token value is
     **never** logged; only `execution_id` and `action` appear.
   - Fall-through safety: a digest hit that fails the per-execution
     scope (wrong execution, wrong action, expired, revoked, wrong
     organization) is **never** retried against the shared token.
     Otherwise an attacker holding a valid credential for execution
     A could trade it for shared-token access to execution B.
   - All failure modes collapse to one indistinguishable
     `WorkerAuthenticationFailed` (HTTP 401, `worker_authentication_failed`).
   - The `service.worker_started` / `service.worker_finished`
     contract is unchanged: the service still locks the row by id
     and derives the organization from the locked row, so the
     credential layer never widens the mutation surface beyond what
     the service already validated.
   - The tenant `X-Organization-Id` header is never consulted on the
     worker path — it remains exclusively the user-tenant boundary.
4. **Worker bootstrap credential injection**:
   - **Step 4A — dispatch-side issuance + handoff contract** *(landed)*:
     `service.create_and_queue` now mints the per-execution credential
     via `PersistedWorkerCredentialIssuer` after the execution row and
     snapshots are persisted and **before** the dispatch publish, inside
     the same request transaction. It grants both hook actions
     (`worker_started` + `worker_finished`), sets `expires_at` to the
     sooner of a **1 hour default TTL** and the engagement testing-window
     end (never beyond the issuer's 24 h hard cap), and hands the raw
     token to the dispatch seam as a `WorkerCredentialHandoff` — a pure,
     frozen value object carrying `execution_id`, `credential_id`,
     `raw_token` (`SecretStr`), and `expires_at`. The handoff is passed to
     `ValidationDispatcher.dispatch(payload, *, handoff=...)` as **internal
     side-channel data**: the broker publisher ignores it (the envelope
     stays credential-free) and the in-memory dev dispatcher ignores it
     (the queue message stays token-free). Failure handling is
     fail-closed: an issuance rejection raises
     `WorkerCredentialIssuanceFailed` (never carrying the token or the
     internal reason) so nothing is dispatched, and because issuance and
     dispatch share the transaction a dispatch failure rolls the credential
     row back with the execution — no orphaned grant. The raw token exists
     **only** in process memory (issuer → handoff → dispatcher) and is
     never written to the DB (digest only), the broker payload/envelope,
     the in-memory queue, logs, audit events (which reference
     `credential_id`), or the API response.
   - **Step 4B — worker bootstrap credential-injection boundary**
     *(landed)*: the worker side can now resolve the per-execution
     credential from a side-channel and inject it into the run, without
     the token ever touching the broker envelope. Three pieces landed:

     1. **Pure source contract** (in `worker_credential_contracts.py`):
        `WorkerBootstrapSecretSource` is a Protocol with
        `async resolve(*, execution_id) -> WorkerCredentialResolution`.
        `WorkerCredentialResolutionOutcome` is the typed result —
        `found` / `missing` / `expired` / `invalid_reference` /
        `source_unavailable`. Only `found` carries a `raw_token`
        (`SecretStr`); every other outcome carries `None`.

     2. **Dev/test in-memory handoff registry**
        (`worker_credential_handoff_registry.py`):
        `InMemoryWorkerCredentialHandoffRegistry` implements the source.
        It stores `WorkerCredentialHandoff` objects by `execution_id`,
        resolves them **once** (a successful resolve consumes the entry,
        so a redelivered broker message cannot re-read the token), drops
        expired handoffs, and never unwraps, serializes, or logs the
        token. It is explicitly **not** production storage — a real
        deployment supplies a locked-down source (container secret or a
        credential service).

     3. **Worker bootstrap** (`celery_worker_bootstrap.py`):
        `run_validation_envelope_with_handoff(envelope, *, source,
        client_factory, kill_switch, transport_factory,
        shared_token_fallback)` reads the **validated** `execution_id`
        from the envelope (`celery_worker.envelope_execution_id`, which
        runs the full envelope + payload contract), resolves the token
        from the side-channel, builds the `WorkerClient` via the injected
        `client_factory`, and delegates to the tested
        `run_validation_envelope`. `build_run_validation_task_with_handoff_source`
        wraps it as a thin Celery task (`ignore_result=True`, no retry).

     Failure is fail-closed: a malformed envelope →
     `BrokerConsumerOutcome.malformed` (no lookup, the handoff is not
     consumed); a missing / expired / invalid / unavailable side-channel
     credential → `BrokerConsumerOutcome.started_delivery_failed`
     **before** `worker-started`, so no target request is made and
     nothing runs. The shared-token fallback is **off** unless the caller
     passes an explicit `shared_token_fallback` token (transitional; the
     server still rejects it unless its own
     `worker_shared_token_fallback_enabled` flag is on, so the worker-side
     fallback cannot unilaterally widen authority). The raw token lives
     only inside the `SecretStr` until `client_factory` unwraps it once;
     it is never logged, serialized, or placed in the envelope.

     The broker envelope contract is **unchanged** — no `credential_id`
     or `raw_token` field was added. Import purity is pinned: the
     bootstrap and registry import no FastAPI, SQLAlchemy, repositories,
     services, routers, dispatcher, or `app.main`; and `app.main` /
     router / service / dispatcher do not import the bootstrap.

   - **Step 4C — production container-env secret source** *(landed)*:
     `EnvironmentWorkerCredentialSource` (in
     `app/modules/validation_executions/worker_credential_env_source.py`)
     is the production `WorkerBootstrapSecretSource` per **option 1**
     (container env) below. A per-execution container is launched with
     the credential injected as three environment variables —
     `SECURESCOPE_WORKER_CREDENTIAL_TOKEN` (raw token, wrapped in
     `SecretStr` the instant it is read),
     `SECURESCOPE_WORKER_CREDENTIAL_EXECUTION_ID` (the execution the
     container was launched for), and
     `SECURESCOPE_WORKER_CREDENTIAL_EXPIRES_AT` (timezone-aware ISO-8601,
     mirroring the grant so the source refuses an already-dead credential
     without a DB read). `resolve(execution_id)` fails closed on every
     non-happy case with a typed outcome carrying no token: empty request
     → `invalid_reference`; incomplete env or an env scoped to a
     *different* execution → `missing` (a container secret can never
     authenticate another run); unparseable/naive expiry →
     `source_unavailable`; `now >= expires_at` → `expired`; otherwise
     `found`. It is **consume-once in-process** (a `Lock`-guarded flag), so
     a broker redelivery handled by the same worker process cannot re-read
     the token — mirroring the dev registry. Cross-execution isolation
     ultimately comes from the per-execution container (fresh container →
     fresh env → fresh token). Import purity matches the registry/bootstrap
     (stdlib + pure contract + platform clock + `SecretStr` only), pinned by
     an AST test.

   - **Step 4D — production hook-delivery transport** *(landed)*:
     `HttpxWorkerResultTransport` (in
     `app/modules/validation_executions/worker_result_transport.py`) is the
     concrete `WorkerResultTransport` the worker uses to POST the
     `worker-started` / `worker-finished` hooks to the control plane. It is
     the delivery-side counterpart to the scanner's `HttpxTransportClient`,
     but for first-party traffic: one bounded (default 10 s), redirect-free,
     TLS-verified (`verify=True`, `trust_env=False`) JSON `POST` that reads
     the **status code only** — the response body is streamed and closed
     unread, so nothing flows back into the worker. `httpx` is imported
     lazily (worker-only dependency; never in the API import graph).
     `build_worker_client_factory(base_url, ...)` returns the
     `WorkerClientFactory` the bootstrap injects: it binds the control-plane
     `base_url` and this transport, and stamps the per-execution
     `SecretStr` token onto each client via the `X-Worker-Authorization`
     header — the token is never logged here. Import purity is pinned by an
     AST test.

     Still deferred to operational wiring: the **deployment** that launches
     the per-execution worker container / Celery worker process, injects the
     `SECURESCOPE_WORKER_CREDENTIAL_*` variables, and constructs
     `build_run_validation_task_with_handoff_source(source=…,
     client_factory=…)` from the two pieces above. The **option 2**
     credential-service source remains a future drop-in behind the same
     Protocol; nothing else changes to adopt it.
5. **Production enablement**: turn off the shared-token fallback in
   staging/production via Settings; keep dev/test usable with either
   model for local convenience. Remove the fallback after a soak
   period with zero observed shared-token verifications.

Each step ships with its own tests, its own `/review-change` pass, and
its own update to this document and to
`docs/validation-dispatch-broker-design.md`.

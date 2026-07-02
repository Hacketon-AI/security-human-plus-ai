# Validation Dispatch Broker Design

This document defines the production broker boundary for validation
execution dispatch and the rollout that connects it to the existing dev
in-memory adapter. No real broker is implemented yet; production dispatch
stays fail-closed in `dispatcher.py` until a concrete publisher is wired.

## Scope

- Defines the wire contract (`broker_contracts.py`).
- Defines who runs the worker, who carries the message, who authenticates.
- Lays out failure modes, idempotency and retry boundaries, and the
  security guarantees that must hold *before* production enablement.
- Does **not** implement Celery, RabbitMQ, Redis, S3, or any production
  broker code.

Relevant rules: `CLAUDE.md`, `.claude/rules/security-boundaries.md`,
`.claude/rules/scan-authorization.md`, `.claude/rules/data-handling.md`,
`docs/stack-decision.md`.

## Current implemented dev lifecycle

The control plane today goes from create to "queued" inside one request
transaction; a development consumer drains the queue and drives the worker
hooks. Nothing runs the scanner inside the API process.

```
HTTP client
   │
   │  POST /api/v1/validation-executions
   ▼
service.create_and_queue
   ├─ validates eligibility (asset, authorization, engagement, time window)
   ├─ freezes scope/safety snapshots and the execution specification
   ├─ persists the row in `queued`
   └─ dispatcher.dispatch(WorkerDispatchPayload)
                    │
                    ├─ production:  UnconfiguredValidationDispatcher  → fail closed
                    └─ dev/test:    InMemoryValidationDispatcher       → enqueue JSON-safe dict

dev consumer (outside the API process)
   ├─ dequeue                                  ← in_memory_queue
   ├─ deserialize via dispatch_serialization
   ├─ POST worker-started                       ← worker_client.start
   ├─ run worker_runner (no DB, no API fetch)
   │     └─ if it raises: build sanitized failed_safely WorkerFinishedRequest
   └─ POST worker-finished                      ← worker_client.deliver
```

Key invariants enforced by tests today:

- The API path only enqueues. `service.create_and_queue` never calls the
  worker. `dispatcher.py`/`service.py`/`router.py`/`main.py` import no
  worker runtime (`worker_runner`, `worker_process`, `worker_client`,
  `http_transport`).
- A malformed queued message never reaches a target transport.
- `worker-started` must succeed before the runner runs.
- A runner crash after `worker-started` is recovered into a sanitized
  `failed_safely` `worker-finished` — no execution can linger in
  `executing` from a runner failure.

## Production target lifecycle

The production target replaces the in-memory queue with a real broker.
Nothing about the dispatch *contract* changes — the publisher commits the
same `WorkerDispatchPayload` to the broker; the worker pulls it back. The
worker is a separate process running the same `worker_runner` and the same
`worker_client`.

```
HTTP client
   │
   ▼
service.create_and_queue
   └─ dispatcher.dispatch(WorkerDispatchPayload)
            │
            └─ <broker publisher>  ── publish(ValidationDispatchEnvelope) ──▶ broker (RabbitMQ)
                                                                              │
                                                                              ▼
                                                                  isolated worker container
                                                                              │
                                                                              ├─ consume_once → envelope
                                                                              ├─ validate envelope, schema_version, sha256
                                                                              ├─ POST worker-started
                                                                              ├─ run scanner (network egress restricted)
                                                                              └─ POST worker-finished (sanitized)
```

The worker container is the only network egress that touches the target.
The control plane only ever sees the sanitized `WorkerFinishedRequest` it
receives back.

## Contract: the wire envelope

Defined in `app/modules/validation_executions/broker_contracts.py`:

```python
@dataclass(frozen=True, slots=True)
class ValidationDispatchEnvelope:
    message_id: str
    schema_version: str       # currently "1"
    payload: Mapping[str, Any] # serialized WorkerDispatchPayload
    payload_sha256: str        # SHA-256 of canonical JSON of payload
    created_at: str            # ISO-8601 UTC
    attempt: int               # broker delivery attempt (>= 1)
    content_type: str = "application/json"
    trace_id: str | None = None
    idempotency_key: str | None = None
```

What goes in `payload`:

- Exactly the five contract fields of `WorkerDispatchPayload`:
  `execution_id`, `template_id`, `execution_specification`,
  `scope_snapshot`, `safety_snapshot`.
- Only JSON primitives — `str`, `int`, `float`, `bool`, `None`,
  `list`, `dict` with string keys.

What does **not** go in the envelope or the payload, ever:

- ORM rows, dataclasses, enum objects, datetime, bytes, `SecretStr`.
- Step evidence.
- Tenant headers (`X-Organization-Id`) or any tenant id.
- Worker credentials (`X-Worker-Authorization`).
- User credentials, requesting user ids, sessions.
- Raw scanner output, response bodies, error messages.

`payload_sha256` is the SHA-256 of the canonical JSON encoding
(`json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`).
Consumers recompute it and refuse the message on mismatch. The dataclass
validates this on construction so a tampered envelope cannot be created
in-process either.

## Publisher and consumer Protocols

```python
class ValidationDispatchPublisher(Protocol):
    async def publish(self, payload: WorkerDispatchPayload) -> DispatchPublishResult: ...


class ValidationDispatchConsumer(Protocol):
    async def consume_once(self) -> BrokerConsumerResult: ...
```

Publisher constraints (enforced by tests):

- Single method — `publish`. No "execute", "run_scan", or any worker-side
  surface. Any new method must be reviewed against
  `.claude/rules/security-boundaries.md`.
- Returns a typed `DispatchPublishResult`; failures are categorical
  (`published` / `rejected` / `publish_failed`) and never carry a raw
  broker exception.

Consumer constraints (enforced by tests):

- Single method — `consume_once`. Returns a `BrokerConsumerResult`
  parallel to the dev consumer's outcomes.
- Runs *outside* the API process. Never imported by `app.main`,
  `dispatcher`, `service`, or `router` at this rollout step.

## Failure modes

| Step                                            | Failure                          | Behaviour                                              |
|-------------------------------------------------|----------------------------------|--------------------------------------------------------|
| Eligibility / authorization in `service.create_and_queue` | Domain error                     | 4xx; nothing queued.                                   |
| `dispatcher.dispatch`                            | Publisher reports `publish_failed` / `rejected` | Request transaction rolls back. Nothing queued, nothing dispatched. The API does **not** retry. |
| Broker accepts, worker never starts              | Broker redelivers with `attempt + 1` | Worker re-processes; idempotency rules apply (see below). |
| `worker-started`                                 | Non-2xx or transport error       | Consumer reports `started_delivery_failed`. Runner is not invoked. No target request. |
| Runner crash (`MalformedWorkerInput` or other)   | Exception raised after `worker-started` | Sanitized `failed_safely` `WorkerFinishedRequest` is built and posted (`error_code=worker_payload_rejected` or `worker_runtime_failed`, `error_message=None`). |
| `worker-finished`                                | Non-2xx or transport error       | Consumer reports `finished_delivery_failed`. No automatic retry. |
| Broker corruption / schema mismatch              | Envelope `schema_version` or `payload_sha256` does not validate | Consumer reports `malformed`. No worker-started, no scanner request. |

## Retry boundaries

- **API never retries.** A failed `dispatch` rolls the request transaction
  back; the client must re-submit. This is the *only* retry the API
  acknowledges.
- **Broker retry is the broker's job.** RabbitMQ redelivery on missed
  ack is a broker concern. Each redelivery arrives with a higher
  `attempt`.
- **The consumer does not retry.** A `consume_once` call processes at
  most one message; it never loops, never re-posts on failure, and
  never re-enqueues. If a delivery to the control plane fails, the
  message is acked anyway (no requeue) and the operator decides.
- **No automatic retry of `worker-finished`.** Re-running a scan to
  obtain a fresh result must be an operator decision.

These rules are deliberate: scans have side effects on real targets, so
retry must be explicit, scoped, and human-authorised — never an automatic
loop.

## Idempotency strategy

Two independent levels:

1. **API idempotency.** `ValidationExecutionCreate.idempotency_key` —
   when set, a repeat create with the same key returns the existing
   execution row and does not re-dispatch. This already works in the
   current code; the integration test
   `test_idempotent_repeat_does_not_enqueue_twice` pins it.

2. **Broker idempotency.** Brokers are at-least-once: an envelope can
   be delivered to the worker more than once. The worker hooks are now
   duplicate-safe in both directions, so a redelivered envelope cannot
   re-run a scan, overwrite a recorded verdict, or insert duplicate
   step rows. The hooks share the same shape: lock the row with
   `SELECT … FOR UPDATE`, inspect the current `status`, and take the
   idempotent path if the row already reflects the requested
   transition.

   **`worker-started` duplicate semantics.**
   - `queued` / `dispatching` → transitions to `executing`, sets
     `started_at`, emits the audit event (the first delivery).
   - `executing` → returns the row unchanged. `started_at` is *not*
     reset, no new audit event is emitted. This is the idempotent
     redelivery path.
   - `succeeded` / `failed` / `cancelled` / `blocked` → rejects with
     `409 invalid_execution_state_transition`. A late `worker-started`
     must never revive a terminal execution (and in particular must
     never revive a terminal cancellation — see
     `.claude/rules/security-boundaries.md`).

   **`worker-finished` duplicate semantics.**
   - `executing` → applies the sanitized result and transitions to
     `succeeded` / `failed` (the first delivery).
   - `succeeded` / `failed` with a *semantically matching* payload →
     returns the row unchanged. `finished_at` is *not* overwritten, no
     duplicate step rows are inserted, no new audit event is emitted.
     The match check compares only **sanitized** fields (`succeeded`,
     `outcome`, `result_summary`, `error_code`, `error_message`) plus
     the multiset of `(step_name, status, sanitized_evidence)` step
     signatures. Step order is ignored; raw payload bytes are never
     compared. No fingerprint column is stored — the comparison is
     done in-process under the row lock, so no schema migration is
     required.
   - `succeeded` / `failed` with a *different* payload → rejects with
     `409 invalid_execution_state_transition`. A stale or conflicting
     redelivery must never overwrite a recorded verdict.
   - `cancelled` / `blocked` → rejects with
     `409 invalid_execution_state_transition`. A redelivered
     `worker-finished` must never revive a terminal cancellation,
     irrespective of payload content.

   **Concurrency.** The hook fetches the row with
   `repository.get_for_update`, so two concurrent duplicate hooks
   serialize on the row lock. The second caller observes the
   already-terminal row and takes the idempotent (or conflict) path —
   no `UPSERT`, no double-insert. Concurrent worker-finished calls
   carrying conflicting verdicts converge on the same lock: the first
   writer wins atomically and the second is rejected with the typed
   `409 invalid_execution_state_transition`, so the stored result is
   always exactly one of the submitted payloads — never a partial
   blend of summary, outcome, or step rows from both.

   **Response surface.** All duplicate paths return the same minimal
   `WorkerExecutionStateResponse` as the first call; spec, snapshots,
   kill-switch token, and step evidence are never reflected back to
   the worker. The integration tests
   `test_worker_started_idempotent_does_not_reset_started_at`,
   `test_worker_finished_idempotent_no_duplicate_step_results`,
   `test_worker_finished_different_result_rejected`,
   `test_worker_finished_after_cancelled_is_rejected`,
   `test_concurrent_worker_started_sets_started_at_once`,
   `test_concurrent_duplicate_worker_finished_inserts_steps_once`, and
   `test_concurrent_duplicate_worker_finished_conflict_preserves_first`
   pin each behaviour against real PostgreSQL.

   **Why this is required before broker enablement.** RabbitMQ is
   at-least-once for any non-trivial consumer (network blip → ack
   never reaches the broker → message redelivered). Without the
   idempotency above, a single dispatch could re-run a scan or
   silently mutate a verdict on retry. Both are unacceptable per
   `.claude/rules/security-boundaries.md` (no autonomous re-execution)
   and `.claude/rules/scan-authorization.md` (a recorded verdict is
   part of the audit trail).

The envelope carries an optional `idempotency_key` so a broker that
implements deduplication (e.g. via Redis or a deduplication exchange)
can use it without the producer needing to know broker internals.
This is an additional defence on top of the hook-level guarantees
above, not a replacement for them.

## Security boundaries

The contract layer holds these invariants; the implementation layer must
not weaken them.

### Worker authentication

- Today: a single shared `worker_auth_token` is configured in `Settings`
  and presented in `X-Worker-Authorization` for every worker hook. This
  is fail-closed (missing/wrong token returns the same auth-failure
  response). It is a *shared* credential, which is a known limitation —
  and, as of the per-execution credential work, it is gated behind
  `worker_shared_token_fallback_enabled` (**default off**).
- Target: a per-execution, short-lived worker credential issued at
  dispatch time and scoped to one scan, as required by
  `.claude/rules/security-boundaries.md` ("worker credentials are
  short-lived, least-privilege, single-scan"). The envelope does **not**
  carry this credential — it is provisioned out-of-band when the worker
  container is launched, and revoked on terminal lifecycle transition.
- Progress (see `docs/validation-worker-credentials-design.md`): the
  contracts, persistence, verifier, and hook upgrade have landed;
  **Step 4A** issues the per-execution credential inside
  `service.create_and_queue` and carries its raw token to the dispatcher
  boundary as a `WorkerCredentialHandoff` (internal side-channel); and
  **Step 4B** adds the worker-side bootstrap credential-injection
  boundary. The worker now obtains its credential through a
  `WorkerBootstrapSecretSource` (a side-channel Protocol) keyed by the
  validated `execution_id` — **never** from the broker envelope. A
  dev/test `InMemoryWorkerCredentialHandoffRegistry` proves the boundary
  (one-time resolve, expiry, no token in repr/JSON/log);
  `celery_worker_bootstrap.run_validation_envelope_with_handoff` resolves
  the token, builds the `WorkerClient`, and runs the started → runner →
  finished lifecycle, failing closed (no `worker-started`, no target
  request) when the side-channel has no live credential. The broker
  envelope contract is **unchanged and stays credential-free**: the
  publisher ignores the handoff and publishes only the envelope, which
  carries no raw token and no `credential_id`. Production enablement stays
  **blocked** until (a) a production `WorkerBootstrapSecretSource` (a
  container-env secret or a locked-down credential service) replaces the
  dev/test registry, (b) the Celery worker process is deployed, and
  (c) the transitional shared-token fallback is removed. The bootstrap
  contract is fully testable today; only the operational deployment
  wiring and fallback removal remain.

### Kill-switch token

- The kill-switch token lives inside `execution_specification` (per
  `.claude/rules/scan-authorization.md`) — the worker polls it to abort
  mid-run. It is part of the contract payload because the worker
  cannot operate without it; it is **not** a long-lived credential and
  it is never logged in cleartext.

### Payload hashing

- `payload_sha256` is recomputed by the consumer on receipt; a mismatch
  fails closed and is reported as `malformed`. The hash protects
  against accidental drift and against a buggy publisher inserting
  fields the contract refuses; it is *not* a substitute for transport
  authentication.
- Combine with broker transport TLS in production. The hash alone does
  not authenticate the publisher to the consumer.

### Evidence and credentials

- The envelope refuses non-JSON-safe values and any payload field
  outside the contract's five-field set. Evidence, tenant headers,
  request bodies, and user credentials therefore *cannot* enter the
  broker via the contract: there is no key for them to occupy.
- Worker step evidence flows back only via the sanitized
  `WorkerFinishedRequest`, which the service further sanitizes on
  ingest before persisting.

### Logs

- No publisher, no consumer, and no contract validator may log a
  payload value, a token, a target URL, or a raw exception. Errors
  reference only the violated rule by its contract name.

### Private network restrictions

- Target reachability rules remain in `SafeHttpTransport`: it refuses
  private/internal/link-local hosts unless the scope explicitly allows
  them, and it raises `TransportTargetBlocked` for any out-of-policy
  target. The broker carries no flag that disables this — the worker
  builds its own transport from the frozen `scope_snapshot`.

### Production dispatcher remains fail-closed

- `get_validation_dispatcher` returns `UnconfiguredValidationDispatcher`
  by default. A concrete broker publisher is selected only when
  `validation_dispatcher_backend` is set to a value mapped to it.
- The `in_memory` backend is rejected in staging/production at startup
  (`Settings._reject_in_memory_dispatcher_outside_development`). When a
  broker backend lands, an analogous validator must reject misuse —
  e.g. refusing `celery` in development unless the operator opts in.

## Why the API must never run the worker inline

- The API process runs alongside user-facing routes, holds the
  database session pool, and is the only process with tenant
  credentials in memory. A scanner crash or a hung target request must
  not take down the API or hold its session.
- `docs/stack-decision.md` is explicit: "Python does not mean scanners
  run inside the web API."
- `.claude/rules/security-boundaries.md` requires "ephemeral isolated
  worker containers" with restricted egress and short-lived,
  single-scan credentials. The API has none of those properties.

## Why broker messages exclude evidence and credentials

- Evidence may be unbounded (response bodies, headers, response chains).
  Putting it on the broker turns the broker into a sensitive-data store
  that must be encrypted at rest, key-rotated, audited, and purged. The
  control plane already has the evidence path via S3 references; the
  broker has no reason to duplicate it.
- A shared worker credential in the envelope would mean every queued
  message contains a usable credential — an enormous blast radius. A
  per-execution credential issued at dispatch time and revoked on
  terminal transition keeps the credential out of the queue entirely.
- Tenant headers in the envelope would invite the worker to act on
  tenant-derived state instead of the row's identity. The worker-finished
  endpoint already authenticates by row id + worker credential, so the
  tenant header has no role on the worker path.

## Rollout plan

1. **Broker contract** *(this change)*: define
   `broker_contracts.py`, lock the envelope shape, the publisher and
   consumer Protocols, and the import-purity tests. Production stays
   fail-closed.

2. **Concrete Celery/RabbitMQ publisher skeleton** *(landed)*: a
   `CeleryValidationDispatchPublisher` lives in
   `celery_publisher.py`. The dispatcher backend enum gained a `celery`
   value; the settings expose `celery_broker_url`,
   `validation_dispatch_{exchange,routing_key,queue_name,task_name,schema_version}`.
   A startup validator refuses `celery` without a broker URL in every
   environment. `dispatcher.get_validation_dispatcher` returns the
   `CeleryValidationDispatcher` when a publisher is bound to
   `app.state.validation_dispatch_publisher`, otherwise it fails closed.

   The publisher is import-clean: it pulls in no `celery`, no worker
   runtime, no FastAPI, no SQLAlchemy. The actual Celery sender is a
   `CelerySendTask` Protocol, injected at construction time. Tests use a
   fake sender; a future runtime-wiring module will wrap a real Celery
   app's `send_task` (with `ignore_result=True`, JSON serializer, no
   result backend) and bind it on startup. That runtime wiring is the
   next step.

3. **Worker process consuming broker messages** *(skeleton landed)*: a
   broker-fed `ValidationDispatchConsumer` lives in
   `celery_worker.py`. The async core,
   `run_validation_envelope(envelope, client, *, kill_switch,
   transport_factory)`, mirrors the proven `in_memory_consumer`
   lifecycle exactly:

   - **Envelope validation.** The wire dict is rebuilt as a
     `ValidationDispatchEnvelope`, which enforces the field set,
     `content_type == "application/json"`, a positive `attempt`, a
     JSON-safe payload carrying exactly the five contract fields, and
     a `payload_sha256` matching the canonical encoding. The consumer
     then pins `schema_version` to its own current version (no silent
     downgrade). Any violation is normalised to a content-free
     `BrokerEnvelopeError`; the result is `malformed` and **no**
     `worker-started`, runner, or `worker-finished` runs.
   - **Lifecycle.** `worker-started` → runner → `worker-finished`,
     fixed order. `worker-started` failure short-circuits to
     `started_delivery_failed` (no runner, no finished). A runner
     exception (`MalformedWorkerInput` or unexpected) is recovered
     into a sanitized `failed_safely` `WorkerFinishedRequest` with a
     short safe `error_code` (`worker_payload_rejected` /
     `worker_runtime_failed`) and `error_message=None`. An active
     kill switch yields the runner's `blocked_by_control` result;
     `worker-finished` is posted normally.
   - **No retry.** A `worker-finished` non-2xx or transport error is
     reported as `finished_delivery_failed`. The consumer never
     re-runs the scan; that decision belongs to an operator.
   - **No local dedup.** Broker redelivery is safe because the
     `worker-started` / `worker-finished` API hooks are idempotent
     (see the idempotency section). The consumer relies on those, not
     on its own state.
   - **Log safety.** Only the opaque broker `message_id` and the
     coarse outcome reach logs. No envelope, payload, target,
     snapshot, kill-switch token, evidence, broker URL, or raw
     exception ever does.

   A thin Celery task wrapper, `make_run_validation_task(celery_app,
   *, client, kill_switch, transport_factory, task_name)`, registers
   the task with `ignore_result=True` (no result backend) and a
   single-statement body: `asyncio.run(run_validation_envelope(...))`.
   The wrapper takes the `WorkerClient`, kill switch, and optional
   transport factory as parameters so the consumer is fully unit-
   tested without inventing a control-plane transport or a worker
   credential.

   Import purity: `celery_worker.py` imports only `broker_contracts`,
   `dispatch_serialization`, the worker runner / client / schemas, and
   the standard library (plus `celery` itself); it imports nothing
   from FastAPI, SQLAlchemy, `app.main`, the dispatcher, service,
   router, or any repository. AST tests pin both that and the
   reverse — the API path (`dispatcher` / `service` / `router` /
   `app.main`) never imports `celery_worker`.

   Remaining gap before production enablement: the worker bootstrap
   (Step 4) must inject the concrete `WorkerResultTransport` and the
   per-execution worker credential into the wrapper's factory. The
   consumer is intentionally agnostic to both — it never invents a
   default credential and never constructs a delivery transport
   in-process.

4. **Per-execution worker credentials** *(design + contracts landed)*:
   the credential model is fixed in
   `app/modules/validation_executions/worker_credential_contracts.py`
   and detailed in
   [`docs/validation-worker-credentials-design.md`](validation-worker-credentials-design.md).
   The full plan covers the issuer, the verifier, the digest-only
   storage rule, expiry/revocation semantics, the constant-time
   verification path, and the side-channel that keeps the raw token
   out of the broker envelope.

   Production worker bootstrap is **blocked** on this step. The
   `celery_worker.py` skeleton's `make_run_validation_task(...)`
   accepts the `WorkerClient` and kill switch as parameters precisely
   so the worker bootstrap can inject a per-execution
   `WorkerClient` (carrying that execution's raw token) without the
   consumer needing to know how it was minted. Until DB persistence
   (the credential design's rollout Step 2), the upgraded `worker_auth`
   verifier (Step 3), and the bootstrap side-channel (Step 4) all
   land, the shared `worker_auth_token` remains the only working
   authentication path — and production stays fail-closed on
   `validation_dispatcher_backend`.

5. **Production enablement**: set `validation_dispatcher_backend` to the
   broker backend in production. Keep the in-memory backend rejected.
   Add the runbook entries (kill switch, requeue, dead-letter) for
   operators.

Each step ships with its own tests, its own review against
`.claude/rules/`, and its own /review-change pass. Steps 2–5 are
out of scope for this change.

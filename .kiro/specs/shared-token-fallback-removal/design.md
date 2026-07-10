# Design Document: Shared-Token Fallback Removal Cleanup

## Overview

The shared-token fallback was already removed from the production auth path in
`worker_auth.py`. This spec completes the cleanup: one stale docstring paragraph
in `worker_credential_contracts.py` still describes the old mechanism. All test
coverage requirements are already satisfied. The only code change is a targeted
docstring edit — no runtime behavior is altered.

## Architecture

No architectural change. The per-execution credential is already the sole
worker-auth path:

```
worker-started / worker-finished HTTP request
        │
        ▼
require_worker_started_context / require_worker_finished_context
  (worker_auth.py — FastAPI dependency)
        │
        ▼
_authenticate()
  1. Missing header → WorkerAuthenticationFailed
  2. Digest lookup via WorkerCredentialRepository
  3. PersistedWorkerCredentialVerifier.verify() → accepted / rejected
  4. No shared-token fallback branch exists
```

## Components and Interfaces

| Component | Role | Change |
|-----------|------|--------|
| `worker_credential_contracts.py` | Pure contracts, leaf helpers, `evaluate_worker_credential` | Docstring-only edit |
| `worker_auth.py` | FastAPI dependency enforcement | No change (already accurate) |
| `test_worker_auth.py` | Unit — fail-closed properties | No change (already complete) |
| `test_validation_worker_hook_auth.py` | Integration — end-to-end per-execution auth | No change (already complete) |

## Data Models

No schema or data model changes. The `ValidationWorkerCredential` table and all
ORM models remain unchanged.

## Correctness Properties

### Property 1: No shared-token path in production code

Searching `backend/app/` for `shared_token`, `WORKER_SHARED_TOKEN`, or
`fallback` in worker-auth–related files returns zero matches after the
docstring edit.

**Validates: Requirements 2.1, 2.2**

### Property 2: Fail-closed on every rejection mode

Every failure mode — missing header, wrong digest, wrong execution, wrong
action, expired credential, revoked credential — raises `WorkerAuthenticationFailed`
with `code == "worker_authentication_failed"`. All failure modes produce an
indistinguishable response message.

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 3: No token leakage to logs

The raw token value never appears in any log record at `DEBUG` level or above
during a failed or successful authentication attempt.

**Validates: Requirements 3.4**

### Property 4: Docstring consistency

After the edit, `worker_credential_contracts.py` and `worker_auth.py` both
state that the per-execution credential is the only worker-auth path and that
no shared-token fallback exists.

**Validates: Requirements 1.1, 1.2, 5.1, 5.2, 5.3**

## Error Handling

No new error paths are introduced. The existing `WorkerAuthenticationFailed`
exception (subclass of `AuthenticationRequiredError`) is the only failure
surface, and its behavior is unchanged.

## Testing Strategy

All required test coverage already exists:

- **Unit** (`test_worker_auth.py`): missing header, unmatched token,
  indistinguishable failure modes, no token in logs.
- **Integration** (`test_validation_worker_hook_auth.py`): happy path for
  `worker-started` and `worker-finished`, wrong execution, wrong action,
  expired credential, revoked credential, replay idempotency, no raw token
  in logs.

Task 3 runs both suites to confirm no regressions after the docstring edit.

# Requirements Document

## Introduction

The shared-token fallback for validation-worker authentication has already been
removed from the production code (`worker_auth.py`). This spec covers the
follow-on cleanup work: correcting a stale docstring in
`worker_credential_contracts.py` that still describes the old shared-token
design, verifying no dead code paths reference the removed fallback, and
confirming that all fail-closed behavior is adequately tested.

## Glossary

- **Worker_Auth**: The `worker_auth.py` module — the FastAPI dependency layer
  that authenticates `worker-started` / `worker-finished` hook calls.
- **Contracts_Module**: `worker_credential_contracts.py` — pure contracts and
  leaf helpers for per-execution worker credentials; contains no FastAPI or DB
  dependencies.
- **Per_Execution_Credential**: A `ValidationWorkerCredential` row scoped to
  one execution, one action set, and a short TTL. The only worker-auth path
  after fallback removal.
- **Shared_Token_Fallback**: The removed code path that previously allowed any
  worker call to authenticate with a single process-wide token.
- **Integration_Suite**: `tests/integration/test_validation_worker_hook_auth.py`.
- **Unit_Suite**: `tests/unit/test_worker_auth.py`.

---

## Requirements

### Requirement 1: Remove Stale Shared-Token Reference from Contracts Module

**User Story:** As a developer reading `worker_credential_contracts.py`, I want
the module docstring to reflect the current per-execution-only design, so that
I am not misled into thinking a shared-token path still exists.

#### Acceptance Criteria

1. THE Contracts_Module SHALL contain no docstring or comment text that states
   or implies a shared-token mechanism is used by `worker_auth` or any other
   module.
2. WHEN the Contracts_Module docstring is updated, THE Contracts_Module SHALL
   accurately describe the per-execution credential as the sole authentication
   path for worker hooks.
3. THE Contracts_Module SHALL preserve all existing export names, type
   contracts, and runtime behavior unchanged.

---

### Requirement 2: Confirm No Dead Code References the Removed Fallback

**User Story:** As a maintainer, I want assurance that no source file in
`app/` references the old shared-token fallback logic, so that there is no
confusion about which code is live.

#### Acceptance Criteria

1. THE Worker_Auth module SHALL contain no function, branch, or comment that
   references a shared-token fallback path.
2. WHEN a search for shared-token-related symbols (e.g., `shared_token`,
   `WORKER_SHARED_TOKEN`, `fallback`) is performed across `app/`, THE codebase
   SHALL return zero matches in worker-auth–related files.

---

### Requirement 3: Fail-Closed Behavior Is Fully Covered by Unit Tests

**User Story:** As a developer, I want the unit test suite to explicitly assert
every failure mode of `_authenticate`, so that a future refactor cannot
accidentally introduce a path that does not fail closed.

#### Acceptance Criteria

1. THE Unit_Suite SHALL contain a test that asserts a missing
   `X-Worker-Authorization` header raises `WorkerAuthenticationFailed`.
2. THE Unit_Suite SHALL contain a test that asserts a token whose digest
   matches no persisted credential raises `WorkerAuthenticationFailed`.
3. THE Unit_Suite SHALL contain a test that asserts the exception `code`
   attribute is `"worker_authentication_failed"` for all failure modes, and
   that all failure modes produce an indistinguishable response message.
4. THE Unit_Suite SHALL contain a test that asserts the presented token value
   does not appear in any log record emitted at `DEBUG` level or above during
   a failed authentication attempt.

---

### Requirement 4: Integration Suite Covers Per-Execution Happy Path

**User Story:** As a developer, I want the integration suite to confirm that a
valid per-execution credential is accepted and that scope mismatches are
rejected, so that the production auth path is verified end-to-end.

#### Acceptance Criteria

1. THE Integration_Suite SHALL contain a test that asserts a valid
   per-execution credential for the correct execution and action is accepted
   and returns a `WorkerContext` with the correct `execution_id`,
   `organization_id`, and `action`.
2. THE Integration_Suite SHALL contain at least one test that asserts a
   per-execution credential presented for the wrong `execution_id` raises
   `WorkerAuthenticationFailed`.
3. THE Integration_Suite SHALL contain at least one test that asserts a
   per-execution credential presented for the wrong `action` raises
   `WorkerAuthenticationFailed`.
4. IF a per-execution credential's `expires_at` is in the past, THEN THE
   Integration_Suite SHALL assert that the request raises
   `WorkerAuthenticationFailed`.

---

### Requirement 5: Module-Level Documentation Reflects Post-Removal State

**User Story:** As a new team member reading any module touched by the fallback
removal, I want all module-level docstrings to describe only the current
per-execution-only design, so that the documentation is a reliable guide.

#### Acceptance Criteria

1. THE Worker_Auth module docstring SHALL state that the per-execution
   credential is the only worker-auth path and that no shared-token fallback
   exists.
2. WHEN the Contracts_Module docstring is read, THE Contracts_Module docstring
   SHALL not contain the phrase "shared token" or any equivalent phrase
   describing the old fallback mechanism.
3. THE Worker_Auth module docstring and the Contracts_Module docstring SHALL
   remain consistent with each other regarding the per-execution-only design.

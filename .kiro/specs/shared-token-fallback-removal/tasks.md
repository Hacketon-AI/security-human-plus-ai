# Implementation Plan: Shared-Token Fallback Removal Cleanup

## Overview

Three sequential tasks: fix the one stale docstring, verify no dead symbols
remain, then confirm the test suites pass.

## Task Dependency Graph

```json
{
  "waves": [
    {"tasks": [1]},
    {"tasks": [2]},
    {"tasks": [3]}
  ]
}
```

## Tasks

- [x] 1. Fix stale docstring in `worker_credential_contracts.py`
  - Open `backend/app/modules/validation_executions/worker_credential_contracts.py`
  - Replace the opening paragraph that says "The control plane today authenticates the worker hooks … with a single shared token" with an accurate description of the per-execution-only design
  - The replacement must:
    - Remove all language implying a shared-token path exists or existed
    - State that each credential is scoped to one execution, one action set, and a short TTL
    - Reference `worker_auth.py` as the dependency that enforces this at the API layer
    - Preserve all `__all__` entries and all exported names unchanged
  - **Files**: `backend/app/modules/validation_executions/worker_credential_contracts.py`

- [x] 2. Verify no shared-token symbols remain in `app/`
  - Search `backend/app/` for any occurrence of `shared_token`, `WORKER_SHARED_TOKEN`, or `fallback` in worker-auth–related files
  - Confirm zero matches; if any are found, remove or update them
  - **Files**: `backend/app/` (read-only scan, edit only if matches found)

- [x] 3. Run unit and integration test suites to confirm no regressions
  - Run `pytest backend/tests/unit/test_worker_auth.py -v`
  - Run `pytest backend/tests/integration/test_validation_worker_hook_auth.py -v`
  - All tests must pass; no new failures may be introduced
  - **Files**: none (verification only)

## Notes

- Task 1 is documentation-only; no imports, exports, or runtime behavior change.
- Import-purity tests guard that `worker_credential_contracts` stays clean of
  FastAPI/SQLAlchemy — the docstring edit cannot affect those tests.
- If Task 2 finds unexpected matches, open a separate follow-up; do not expand
  this task's scope.

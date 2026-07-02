# Rule: Scan Authorization

Technical shape of the active-scan gate. Boundaries are in `CLAUDE.md`; this
file defines the fields and states code must enforce. Do not weaken these to
make a feature easier.

## Required before any active scan dispatch

An active scan must not leave the orchestrator without an immutable execution
specification carrying all of:

- `asset_id` — references a verified, owned-or-authorized asset.
- `authorization_id` — references a non-expired written authorization.
- `scope` — explicit allow-list (hosts, paths, endpoints). Empty scope ≠ all.
- `testing_window` — start/end timestamps; dispatch outside the window fails.
- `rate_limit` — required, positive; passed to the worker, not advisory.
- `kill_switch_token` — key the worker polls to abort mid-run.
- `intrusive` — explicit flag; defaults to passive/low-impact when absent.

Missing or invalid field → reject with a domain error. Never default an
authorization, scope, or window.

## Dual approval

Scans targeting `production` or `core_banking` require two distinct approver
identities recorded before dispatch. A single identity approving twice is not
two approvals.

## Kill switch

The worker must check the kill switch between phases and abort promptly. The
control plane must be able to set the abort state without waiting for the
worker. A scan that cannot be stopped must not start.

## State

Model scan lifecycle as an explicit enum (e.g. `requested → authorized →
scheduled → running → completed | aborted | rejected`). No implicit transitions.

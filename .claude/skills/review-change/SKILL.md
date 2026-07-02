---
name: review-change
description: Review a pending code change against SecureScope security boundaries, data-handling rules, and the Python engineering standard before it is committed. Use when asked to review a diff, a branch, or staged work on this project, or as the self-review step in the required workflow.
---

# Review Change

Security-focused review for SecureScope changes. Read `.claude/CLAUDE.md` and
the files in `.claude/rules/` first; this skill applies them to a concrete diff.
Report only findings with real impact. Do not rewrite the change here — surface
issues and let the author fix them.

## 1. Establish the diff

Determine exactly what changed and stay within it:

```bash
git diff --staged   # or: git diff <base>...HEAD
git status
```

If there is no VCS, review the files the author names. Flag unrelated edits,
style-only churn, and accidental generated boilerplate as scope violations.

## 2. Security boundaries (blocking)

Reject, do not soften, any change that adds or enables: autonomous
exploitation, persistence, lateral movement, credential harvesting, destructive
payloads, denial-of-service, or bulk extraction. Confirm against
`rules/security-boundaries.md`:

- Scanner logic does not run in the API or a secret-sharing Celery worker.
- Worker credentials are short-lived, least-privilege, single-scan.
- Intrusive behavior stays behind the `intrusive` flag + policy; passive is
  the default.
- No dispatch path can target a host outside the verified asset scope.

## 3. Scan authorization (blocking)

For any code touching scan dispatch, check `rules/scan-authorization.md`:

- Execution spec carries asset, authorization, scope, testing window, rate
  limit, and kill-switch token — none defaulted or optional.
- `production` / `core_banking` require two distinct approver identities.
- Kill switch is checkable mid-run and the control plane can abort
  independently. A scan that cannot be stopped must not start.
- Lifecycle transitions are explicit enum states, not implicit.

## 4. Data handling and leakage (blocking)

Against `rules/data-handling.md`:

- No secret, token, or unmasked sensitive value reaches a log, audit event,
  error message, or API response.
- Evidence/reports stored as encrypted-S3 references, not raw blobs in
  PostgreSQL.
- Raw scanner output is not relocated to a non-sensitive path to dodge the
  `settings.json` deny list.
- External input is validated and typed at the boundary; unexpected fields
  rejected.

## 5. Engineering standard

Against `rules/python-style.md` and `CLAUDE.md`:

- Typed results and domain-specific errors; explicit enums/value objects.
- No placeholder, fake-success, silent fallback, dead code, or speculative
  abstraction (no base class / interface before a second caller).
- Domain names, not `data`/`helper`/`manager`/`processor`/`utils`.
- Side effects, transactions, retries, timeouts, idempotency are explicit.
- Tests added or updated for the behavior changed.

## 6. Quality gates

Confirm the author ran, and that they pass:

```bash
make format
make lint
make typecheck
make test
```

Do not approve when a relevant gate failed or was not run.

## Output

Report in priority order:

1. **Blocking** — boundary, authorization, or data-leakage violations.
2. **Required** — standard or correctness issues that must be fixed.
3. **Optional** — improvements worth considering.

For each finding give `file:line`, the rule it breaks, and the concrete fix.
State clearly whether the change is safe to commit.

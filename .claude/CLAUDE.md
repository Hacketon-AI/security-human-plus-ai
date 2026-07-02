# SecureScope Engineering Guide

SecureScope is an authorized defensive security testing platform for web,
mobile, API, core banking, and attendance systems.

## Read First

Before changing code:

1. Read this file and every applicable file in `.claude/rules/`.
2. Inspect the affected module, tests, configuration, and adjacent patterns.
3. State assumptions when the repository does not answer an important question.
4. Keep the change inside the requested scope.

## Product Boundaries

- Only support testing of assets owned by the organization or covered by
  explicit written authorization.
- Active scans require a verified asset, valid authorization, approved scope,
  testing window, rate limit, and emergency stop path.
- Production and core banking tests require dual approval.
- Never add autonomous exploitation, persistence, lateral movement, credential
  harvesting, destructive payloads, denial-of-service behavior, or bulk data
  extraction.
- Default to passive or low-impact checks. Intrusive checks are opt-in and
  policy-controlled.
- Treat credentials, tokens, personal data, banking data, biometric data,
  evidence, and raw scanner output as sensitive.

## Architecture Direction

- Backend control plane: Python 3.12+, FastAPI, Pydantic v2.
- Persistence: PostgreSQL, SQLAlchemy 2.x, Alembic.
- Background orchestration: Celery with RabbitMQ.
- Cache, rate limiting, and short-lived coordination: Redis.
- Scanner execution: ephemeral isolated containers. Never execute scanners
  inside the API process.
- Frontend: TypeScript, React/Next.js.
- Object storage: S3-compatible encrypted storage for evidence and reports.
- Observability: OpenTelemetry, structured logs, metrics, and audit events.
- Start as a modular monolith. Extract services only after a demonstrated
  scaling, isolation, or ownership need.

## Engineering Standard

- Produce production-quality code, not tutorial code or generic AI templates.
- Follow existing patterns before introducing new abstractions or dependencies.
- Use precise domain names. Avoid vague names such as `data`, `helper`,
  `manager`, `processor`, or `utils` when a domain-specific name is possible.
- Keep functions focused and modules cohesive. Do not create abstractions for
  a single trivial use.
- No placeholder implementations, fake success responses, silent fallback,
  dead code, speculative features, or unexplained TODO comments.
- Validate all external input at system boundaries.
- Represent domain states explicitly with enums or value objects.
- Return typed results and domain-specific errors.
- Make side effects, transactions, retries, timeouts, and idempotency explicit.
- Never log secrets or unmasked sensitive data.
- Comments explain intent, risk, or non-obvious constraints. They do not narrate
  obvious code.

## Required Workflow

1. Understand the behavior and threat model.
2. Write or update focused tests.
3. Implement the smallest complete change.
4. Run formatting, linting, type checking, and relevant tests.
5. Review the diff for security, data leakage, unrelated edits, and accidental
   generated boilerplate.
6. Report changed files, verification performed, and remaining risks.

## Quality Gates

Use the project commands once they exist:

```bash
make format
make lint
make typecheck
make test
```

Do not claim completion when relevant checks fail or were not run.

## Git Discipline

- Do not rewrite history, force push, reset, or discard user changes.
- Do not mix unrelated refactors with feature work.
- Do not commit secrets, `.env` files, evidence, scan outputs, or customer data.
- Keep commits reviewable and describe behavior, not implementation trivia.

## Continuation Discipline

- At the beginning of every resumed task, inspect the current diff, recent
  implementation, applicable specification, and unfinished acceptance criteria.
- Continue the requested feature before addressing unrelated warnings or
  cosmetic cleanup.
- A passing test suite does not mean the requested feature is complete.
- Do not infer the next task only from repository size or existing tests.
- When context is incomplete, report what is missing instead of selecting an
  unrelated improvement.
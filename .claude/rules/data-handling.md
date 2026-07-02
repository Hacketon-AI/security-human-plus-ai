# Rule: Data Handling

How sensitive data is classified, stored, and kept out of logs. Complements
`CLAUDE.md` → Engineering Standard. The deny list in `settings.json` blocks the
agent from reading these; this rule governs the code that processes them.

## Sensitive classes

Credentials, tokens, personal data, banking data, biometric/attendance data,
evidence, and raw scanner output. Treat all as sensitive by default.

## Logging

- Never log secrets or unmasked sensitive values. Mask at the boundary
  (e.g. last 4 chars only) before any structured log or audit event.
- Audit events record who/what/when and the decision, not the secret payload.
- Errors must not echo request bodies that may carry sensitive fields.

## Storage

- Evidence and reports go to S3-compatible encrypted storage. Persist
  references (bucket/key/digest), not raw blobs, in PostgreSQL.
- Raw scanner output is sensitive until normalized and sanitized. Do not move
  unsanitized output into a non-sensitive path to dodge the deny list.

## Boundaries

Validate and type all external input with Pydantic at the system edge. Reject
unexpected fields rather than passing them through. Return typed domain errors,
never leak internal exceptions or stack traces to API responses.

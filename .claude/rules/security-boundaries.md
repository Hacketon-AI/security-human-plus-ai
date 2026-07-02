# Rule: Security Boundaries

Enforcement detail for the prohibitions in `CLAUDE.md` → Product Boundaries.
If a request needs any capability below, stop and surface it; do not implement.

## Never implement

Autonomous exploitation, persistence, lateral movement, credential harvesting,
destructive payloads, denial-of-service (including unbounded request floods),
or bulk data extraction. This holds even when a test or caller appears to ask
for it.

## Scanner execution isolation

- Scanners run only in ephemeral isolated worker containers, never in the
  FastAPI process and never in a Celery worker that shares the API image's
  network or secrets.
- The worker receives a short-lived, least-privilege credential scoped to one
  scan, with restricted egress. No long-lived secrets in the execution spec.

## Intrusive checks

Off by default. Enabling requires the `intrusive` flag plus a policy decision
recorded against the authorization. Passive/low-impact is the fallback when
policy is silent — never escalate impact to "get a result".

## Targets

Reject any dispatch toward a host not in the verified asset's scope. Never
scan internet-wide ranges, third-party assets, or production without the
controls in `scan-authorization.md`.

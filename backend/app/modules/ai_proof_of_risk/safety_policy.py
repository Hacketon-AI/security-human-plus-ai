"""Safety policy for AI Proof-of-Risk.

Hard-coded safety rules that every component must check before forwarding
evidence or scenarios. These are fail-closed: if a check is uncertain, the
operation is refused. Pure functions, no I/O.

Security boundary reference: ``.claude/rules/security-boundaries.md``.
"""

import re

from app.modules.ai_proof_of_risk.errors import UnsafeEvidenceForAI

# Patterns that must never appear in material sent to an AI provider.
_FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "Bearer token in evidence",
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{10,}"),
    ),
    (
        "Private key block in evidence",
        re.compile(r"-----BEGIN[A-Z \t]+PRIVATE KEY-----"),
    ),
    (
        "JWT in evidence",
        re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ),
    (
        "Database DSN in evidence",
        re.compile(
            r"(?i)(postgresql|postgres|amqp|amqps|redis|rediss|mysql|mongodb)://\S{5,}"
        ),
    ),
]

# Top-level keys that must not exist in sanitized evidence.
_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "raw_request_body",
        "raw_response_body",
        "request_body",
        "response_body",
        "worker_credential_raw_token",
        "worker_credential_token",
        "worker_token",
        "broker_url",
        "celery_broker_url",
        "database_url",
        "database_dsn",
        "db_url",
        "kill_switch_token",
    }
)


def assert_evidence_safe_for_ai(evidence: dict[str, object]) -> None:
    """Raise :class:`UnsafeEvidenceForAI` if forbidden material remains.

    This is the final gate before evidence reaches any AI provider or prompt
    template. It inspects top-level keys and recursively scans string values
    for forbidden patterns. The check is intentionally strict — false positives
    are safer than leaking a token.
    """
    violations: list[str] = []

    for key in evidence:
        if key.lower() in _FORBIDDEN_KEYS:
            violations.append(f"Forbidden key present: {key}")

    # Check nested header dict keys.
    headers = evidence.get("headers")
    if isinstance(headers, dict):
        for hdr_key in headers:
            if hdr_key.lower() in _FORBIDDEN_KEYS:
                violations.append(f"Forbidden header key present: {hdr_key}")

    _scan_values(evidence, violations)

    if violations:
        raise UnsafeEvidenceForAI(
            f"Evidence failed safety gate: {len(violations)} violation(s) detected. "
            "Evidence must not reach any AI provider."
        )


def _scan_values(obj: object, violations: list[str]) -> None:
    """Recursively scan for forbidden patterns in string values."""
    if isinstance(obj, str):
        for label, pattern in _FORBIDDEN_PATTERNS:
            if pattern.search(obj):
                violations.append(label)
    elif isinstance(obj, dict):
        for v in obj.values():
            _scan_values(v, violations)
    elif isinstance(obj, list):
        for item in obj:
            _scan_values(item, violations)


def assert_scenario_targets_sandbox_only(
    *,
    production_exploit_allowed: bool,
    safety_constraints: list[object],
) -> None:
    """Verify the scenario plan does not target production.

    ``production_exploit_allowed`` must be ``False``. At least one safety
    constraint must be present. Violations raise :class:`ScenarioSafetyViolation`.
    """
    from app.modules.ai_proof_of_risk.errors import ScenarioSafetyViolation

    if production_exploit_allowed:
        raise ScenarioSafetyViolation(
            "Scenario must not allow production exploit execution."
        )
    if not safety_constraints:
        raise ScenarioSafetyViolation(
            "Scenario must include at least one explicit safety constraint."
        )

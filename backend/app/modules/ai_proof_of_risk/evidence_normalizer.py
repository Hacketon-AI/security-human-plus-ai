"""Evidence normalizer for AI Proof-of-Risk.

Transforms raw validation-execution evidence into a standardised shape suitable
for redaction and downstream analysis. This is the boundary between the
validation-executions module's evidence format and the AI module's input
contracts. Pure functions, no I/O.
"""

from app.modules.ai_proof_of_risk.schemas import SanitizedFinding

# Well-known finding types that the attack-surface graph and scenario generator
# recognize. Other finding types are passed through but only processed by the
# AI routing layer, not by the deterministic generators.
KNOWN_FINDING_TYPES: frozenset[str] = frozenset(
    {
        "missing_csp",
        "missing_x_frame_options",
        "insecure_cookie_flags",
        "permissive_cors",
        "missing_hsts",
    }
)


def normalize_finding(
    *,
    finding_id: str,
    finding_type: str,
    asset_host: str,
    evidence: dict[str, object],
) -> SanitizedFinding:
    """Build a :class:`SanitizedFinding` from validated, pre-redacted fields.

    Callers must pass evidence that has already been through
    :func:`~app.modules.ai_proof_of_risk.redaction.redact_evidence`. This
    function does not re-redact — it trusts the contract and normalises the
    shape.
    """
    return SanitizedFinding(
        finding_id=finding_id,
        finding_type=finding_type,
        asset_host=asset_host,
        evidence=evidence,
    )


def classify_finding_type(finding_type: str) -> bool:
    """Return whether a finding type is recognized for deterministic analysis."""
    return finding_type in KNOWN_FINDING_TYPES

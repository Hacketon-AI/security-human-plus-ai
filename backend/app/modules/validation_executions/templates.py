"""Validation template registry.

A template is a named, safe, read-only check definition. It carries the risk
tier the check operates at and the immutable safety bounds a worker must honour
(timeouts, redirect/request/response caps). Templates never contain payloads,
credentials, or mutation logic — only the parameters of a passive check.

Only one template exists in this stage: read-only HTTP security-header
validation. New templates must stay within the product boundaries in
``.claude/rules/security-boundaries.md`` (passive/low-impact, in-scope only).
"""

from dataclasses import dataclass

from app.modules.authorizations.enums import RiskTier
from app.modules.validation_executions.errors import UnknownValidationTemplate

HTTP_SECURITY_HEADER_VALIDATION = "HTTP_SECURITY_HEADER_VALIDATION"


@dataclass(frozen=True, slots=True)
class SafetyLimits:
    """Bounds a worker must enforce. Recorded into the safety snapshot."""

    timeout_seconds: float
    redirect_limit: int
    max_requests: int
    max_response_bytes: int


@dataclass(frozen=True, slots=True)
class ValidationTemplate:
    """A registered, safe validation check definition.

    ``method`` is constrained to read-only verbs; ``risk_tier`` is the impact
    level the check runs at and must be permitted by both the authorization and
    the engagement.
    """

    template_id: str
    description: str
    risk_tier: RiskTier
    allowed_methods: tuple[str, ...]
    safety_limits: SafetyLimits


# The single safe template: read-only header inspection, no payloads, no
# mutation, bounded work, origin-only.
_HTTP_SECURITY_HEADER_VALIDATION = ValidationTemplate(
    template_id=HTTP_SECURITY_HEADER_VALIDATION,
    description=(
        "Read-only HTTP security-header validation. Issues bounded HEAD/GET "
        "requests to the target origin and inspects response headers only."
    ),
    risk_tier=RiskTier.tier_0_passive,
    allowed_methods=("HEAD", "GET"),
    safety_limits=SafetyLimits(
        timeout_seconds=5.0,
        redirect_limit=3,
        max_requests=5,
        max_response_bytes=65536,
    ),
)

_TEMPLATES: dict[str, ValidationTemplate] = {
    _HTTP_SECURITY_HEADER_VALIDATION.template_id: _HTTP_SECURITY_HEADER_VALIDATION,
}


def get_template(template_id: str) -> ValidationTemplate:
    """Return the registered template or raise :class:`UnknownValidationTemplate`."""
    template = _TEMPLATES.get(template_id)
    if template is None:
        raise UnknownValidationTemplate(f"unknown validation template: {template_id}")
    return template

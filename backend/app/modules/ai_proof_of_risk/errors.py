"""AI Proof-of-Risk domain errors.

Domain-specific exceptions following the project error taxonomy. Messages never
carry unmasked sensitive data (see ``.claude/rules/data-handling.md``).
"""

from app.platform.errors import ConflictError, DomainValidationError


class RedactionPolicyViolation(DomainValidationError):
    """Evidence contains material that could not be safely redacted.

    Raised when redaction detects a pattern it cannot mask without risking
    partial leakage (e.g. truncated private key block). The caller must not
    forward the evidence to any AI provider or non-sensitive path.
    """

    code = "redaction_policy_violation"


class UnsafeEvidenceForAI(DomainValidationError):
    """Evidence failed the safety gate and must not reach an AI provider.

    This is the final pre-routing check: if any raw body, credential header, or
    secret survived redaction the evidence is rejected outright.
    """

    code = "unsafe_evidence_for_ai"


class ProviderNotAvailable(ConflictError):
    """The selected AI provider is not reachable or not configured.

    The router falls back to ``deterministic_fallback`` when this occurs; this
    error is raised only if the caller explicitly requested a specific provider
    that is unavailable.
    """

    code = "provider_not_available"


class ScenarioSafetyViolation(DomainValidationError):
    """A scenario plan violates safety constraints.

    Raised when a generated scenario targets production, includes arbitrary
    exploit payloads, or omits mandatory sandbox isolation markers.
    """

    code = "scenario_safety_violation"


class AttackGraphConstructionError(ConflictError):
    """The attack-surface graph could not be built from the provided findings.

    Typically raised when the input findings are empty or contain no recognized
    vulnerability patterns.
    """

    code = "attack_graph_construction_error"


class SandboxTargetRejectedError(DomainValidationError):
    """The sandbox target was rejected by the guard."""

    code = "sandbox_target_rejected"


class UnsupportedSandboxScenarioError(DomainValidationError):
    """No approved simulation handler exists for this scenario."""

    code = "unsupported_sandbox_scenario"


class UnsafeScenarioError(DomainValidationError):
    """The scenario violates digital twin sandbox safety invariants."""

    code = "unsafe_scenario"


class SandboxSimulationDisabledError(ConflictError):
    """Sandbox simulation is disabled by configuration."""

    code = "sandbox_simulation_disabled"


class MissingExecutionError(ConflictError):
    """The requested execution does not exist or is inaccessible."""

    code = "missing_execution"


class UnverifiedAssetError(ConflictError):
    """The asset target is not verified as safe/owned."""

    code = "unverified_asset"

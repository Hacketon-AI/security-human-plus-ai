"""Pydantic schemas for the AI Proof-of-Risk module.

All contracts are frozen Pydantic v2 models with ``extra="forbid"``. Sensitive
fields are never present — inputs arrive pre-redacted and outputs never carry
raw evidence, tokens, or credentials.
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.ai_proof_of_risk.enums import (
    AIRoute,
    AnalysisMode,
    Audience,
    ExploitSimulationType,
    FindingComplexity,
    GraphEdgeKind,
    GraphNodeKind,
    ProofType,
    ProviderStatus,
    RedactionCategory,
    ScenarioType,
)

# ---------------------------------------------------------------------------
# Redaction contracts
# ---------------------------------------------------------------------------


class RedactionEntry(BaseModel):
    """One redacted field or pattern occurrence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: RedactionCategory
    field_path: str = Field(
        description=(
            "Dot-delimited path to the redacted field (e.g. 'headers.Authorization')."
        ),
        max_length=300,
    )
    original_length: int = Field(
        ge=0,
        description="Character length of the original value before masking.",
    )


class RedactionResult(BaseModel):
    """Output of the deterministic redaction pass."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sanitized_evidence: dict[str, object]
    redaction_summary: list[RedactionEntry]
    removed_fields: list[str]
    safety_warnings: list[str]


# ---------------------------------------------------------------------------
# Security router contracts
# ---------------------------------------------------------------------------


class RoutingRequest(BaseModel):
    """Input to the token-efficient security router."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    execution_id: UUID
    finding_id: str = Field(min_length=1, max_length=200)
    finding_type: str = Field(min_length=1, max_length=200)
    complexity: FindingComplexity
    sanitized_evidence: dict[str, object]
    analysis_mode: AnalysisMode | None = None
    audience: Audience | None = None
    ai_router_mode: str = "hybrid"
    force_remote_reasoning: bool = False


class ComplexityClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    complexity: FindingComplexity


class RouteSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    suggested_route: AIRoute


class SafeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    summary: str


class EvidenceSufficiencyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    is_sufficient: bool
    missing_elements: list[str]


class RemediationHint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    hint: str
    effort: str


class RoutingDecision(BaseModel):
    """Output of the security router."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_route: AIRoute
    reason: str = Field(max_length=500)
    provider_name: str = Field(max_length=100)
    model_name: str = Field(max_length=200)
    local_provider_available: bool = False
    remote_provider_available: bool = False
    attempted_local_call: bool = False
    attempted_remote_call: bool = False
    avoided_remote_call: bool
    estimated_remote_tokens: int = Field(ge=0)
    estimated_local_tokens: int = Field(ge=0)
    token_saving_estimate: int = Field(default=0)
    fallback_used: bool
    fallback_reason: str | None = None
    local_provider_latency_ms: float | None = None
    remote_provider_latency_ms: float | None = None


# ---------------------------------------------------------------------------
# Attack surface graph contracts
# ---------------------------------------------------------------------------


class GraphNode(BaseModel):
    """A node in the attack-surface graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1, max_length=200)
    kind: GraphNodeKind
    label: str = Field(max_length=500)
    metadata: dict[str, object] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """A directed edge in the attack-surface graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=200)
    target_id: str = Field(min_length=1, max_length=200)
    kind: GraphEdgeKind
    label: str = Field(max_length=500)


class AttackSurfaceGraph(BaseModel):
    """Complete attack-surface graph for a set of sanitized findings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    finding_count: int = Field(ge=0)
    missing_control_count: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Sanitized finding input
# ---------------------------------------------------------------------------


class SanitizedFinding(BaseModel):
    """A single sanitized security finding used as graph and scenario input.

    All credential material must already be redacted before constructing this
    model. ``evidence`` must come from a :class:`RedactionResult`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_id: str = Field(min_length=1, max_length=200)
    finding_type: str = Field(min_length=1, max_length=200)
    asset_host: str = Field(min_length=1, max_length=500)
    evidence: dict[str, object] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Digital twin scenario contracts
# ---------------------------------------------------------------------------


class SandboxComponent(BaseModel):
    """A component replicated inside the digital-twin sandbox."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=200)
    role: str = Field(max_length=500)


class SafetyConstraint(BaseModel):
    """An explicit safety constraint on the scenario."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    constraint_id: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=1000)


class DigitalTwinScenario(BaseModel):
    """A digital-twin scenario plan — describes execution, not runs it.

    ``production_exploit_allowed`` is always ``False``. This field exists as a
    machine-readable assertion that every consumer must verify.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str = Field(min_length=1, max_length=200)
    execution_id: UUID
    finding_refs: list[str]
    vulnerability_pattern: str = Field(max_length=500)
    scenario_type: ScenarioType
    controls_replicated: list[str]
    sandbox_components: list[SandboxComponent]
    exploit_simulation_type: ExploitSimulationType
    safe_proof_goal: str = Field(max_length=1000)
    expected_proof_token: str = Field(max_length=200)
    safety_constraints: list[SafetyConstraint]
    production_exploit_allowed: bool = Field(
        default=False,
        description="Always False. Production exploit is never allowed.",
    )


# ---------------------------------------------------------------------------
# Provider status contracts
# ---------------------------------------------------------------------------


class ProviderHealthStatus(BaseModel):
    """Health status of an AI provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_name: str = Field(max_length=100)
    status: ProviderStatus
    model_name: str = Field(max_length=200)
    supports_streaming: bool = False


# ---------------------------------------------------------------------------
# Sandbox Runner contracts
# ---------------------------------------------------------------------------


class SandboxTarget(BaseModel):
    """Target environment explicitly assigned for a sandbox scenario run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sandbox_base_url: str = Field(max_length=1000)
    scenario_id: str = Field(max_length=200)
    execution_id: UUID
    allowed_host: str = Field(max_length=200)
    allowed_scheme: str = Field(max_length=10)
    sandbox_network_id: str | None = Field(default=None, max_length=200)
    is_ephemeral: bool
    created_by_securescope: bool


class ProofOfRiskArtifact(BaseModel):
    """The final proof generated by executing a scenario in the digital twin."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proof_id: str = Field(max_length=200)
    scenario_id: str = Field(max_length=200)
    execution_id: UUID
    proof_type: ProofType
    proof_token: str = Field(max_length=1000)
    sandbox_target: SandboxTarget
    confirmed: bool
    evidence_summary: str = Field(max_length=5000)
    steps_summary: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    created_at: str = Field(max_length=100)
    sanitized_metadata: dict[str, str] = Field(default_factory=dict)
    production_target_used: bool = Field(
        default=False,
        description="Always False. Production exploit is never allowed.",
    )


# ---------------------------------------------------------------------------
# API / Service Contracts
# ---------------------------------------------------------------------------


class AIProofOfRiskAnalysisRequest(BaseModel):
    """Client request to generate AI proof-of-risk."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_mode: AnalysisMode
    audience: Audience
    include_sanitized_evidence: bool = True
    allow_sandbox_simulation: bool = False
    force_remote_reasoning: bool = False


class RiskTribunalVerdict(BaseModel):
    """Deterministic placeholder for a risk tribunal result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attacker_view: str = Field(max_length=5000)
    defender_view: str = Field(max_length=5000)
    lab_view: str = Field(max_length=5000)
    judge_verdict: str = Field(max_length=5000)
    severity: str = Field(max_length=50)
    confidence: str = Field(max_length=50)
    false_positive_risk: str = Field(max_length=50)
    business_impact: str = Field(max_length=5000)
    recommended_priority: str = Field(max_length=50)
    limitations: list[str] = Field(default_factory=list)


class RemediationPlan(BaseModel):
    """Deterministic remediation plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    immediate_fix: str = Field(max_length=5000)
    developer_tasks: list[str] = Field(default_factory=list)
    devops_tasks: list[str] = Field(default_factory=list)
    security_owner_tasks: list[str] = Field(default_factory=list)
    safe_config_examples: list[str] = Field(default_factory=list)
    verification_steps: list[str] = Field(default_factory=list)
    regression_tests: list[str] = Field(default_factory=list)
    estimated_effort: str = Field(max_length=50)
    risk_reduction: str = Field(max_length=500)


class RetestPlan(BaseModel):
    """Deterministic retest plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    retest_checklist: list[str] = Field(default_factory=list)
    before_state: str = Field(max_length=1000)
    expected_after_state: str = Field(max_length=1000)
    safe_validation_template: str = Field(max_length=5000)
    success_criteria: list[str] = Field(default_factory=list)
    evidence_needed: list[str] = Field(default_factory=list)
    risk_delta_if_fixed: str = Field(max_length=1000)


class AIProofOfRiskAnalysisResponse(BaseModel):
    """Comprehensive response for AI proof-of-risk generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_id: str = Field(max_length=100)
    execution_id: UUID
    status: str = Field(max_length=50)
    mode: AnalysisMode
    risk_summary: str | None = None
    attack_surface_graph: dict[str, Any] | None = (
        None  # Generic dict placeholder for the graph representation
    )
    exploitability_hypotheses: list[str] | None = None
    digital_twin_scenarios: list[DigitalTwinScenario] | None = None
    sandbox_proof_artifacts: list[ProofOfRiskArtifact] | None = None
    tribunal_verdict: RiskTribunalVerdict | None = None
    remediation_plan: RemediationPlan | None = None
    retest_plan: RetestPlan | None = None
    executive_summary: str | None = None
    technical_summary: str | None = None
    model_routing_trace: list[str] = Field(default_factory=list)
    token_saving_estimate: int = 0
    safety_notes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    created_at: str = Field(max_length=100)

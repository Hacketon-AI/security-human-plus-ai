"""Service Orchestrator.

Orchestrates the AI Proof-of-Risk pipeline. Enforces safety bounds,
data redaction, and strict API-to-sandbox isolation.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.modules.ai_proof_of_risk.attack_surface_graph import (
    build_attack_surface_graph,
)
from app.modules.ai_proof_of_risk.digital_twin_scenario import (
    generate_scenario,
)
from app.modules.ai_proof_of_risk.enums import AIRoute, FindingComplexity
from app.modules.ai_proof_of_risk.errors import (
    MissingExecutionError,
    UnverifiedAssetError,
)
from app.modules.ai_proof_of_risk.execution_evidence_provider import (
    ExecutionEvidenceProvider,
)
from app.modules.ai_proof_of_risk.prompt_templates import SAFETY_INSTRUCTIONS
from app.modules.ai_proof_of_risk.redaction import redact_evidence
from app.modules.ai_proof_of_risk.remediation import generate_remediation_plan
from app.modules.ai_proof_of_risk.report_generator import generate_report
from app.modules.ai_proof_of_risk.retest_planner import generate_retest_plan
from app.modules.ai_proof_of_risk.risk_tribunal import generate_risk_tribunal
from app.modules.ai_proof_of_risk.sandbox_guards import SandboxTargetGuard
from app.modules.ai_proof_of_risk.sandbox_runner import SandboxRunner
from app.modules.ai_proof_of_risk.schemas import (
    AIProofOfRiskAnalysisRequest,
    AIProofOfRiskAnalysisResponse,
    RoutingRequest,
    SandboxTarget,
    SanitizedFinding,
)
from app.modules.ai_proof_of_risk.security_router import route_finding


class ServiceConfig(BaseModel):
    """Configuration for AI Proof-of-Risk Service."""

    ai_proof_of_risk_enabled: bool = True
    ai_sandbox_simulation_enabled: bool = False
    ai_sandbox_base_url: str | None = None
    ai_router_mode: str = "deterministic"
    ai_max_remote_tokens: int = 4000


class AIProofOfRiskService:
    """Orchestrates the AI Proof-of-Risk pipeline."""

    def __init__(
        self,
        evidence_provider: ExecutionEvidenceProvider,
        config: ServiceConfig | None = None,
        providers: dict[str, Any] | None = None,
    ) -> None:
        self.evidence_provider = evidence_provider
        self.config = config or ServiceConfig()

        from app.config import get_settings
        from app.modules.ai_proof_of_risk.fireworks_provider import (
            DefaultHTTPClient,
            FireworksConfig,
            FireworksGemmaReasoningProvider,
        )
        from app.modules.ai_proof_of_risk.local_amd_provider import (
            LocalAmdModelProvider,
        )

        settings = get_settings()
        fireworks_config = FireworksConfig(
            fireworks_api_key=settings.fireworks_api_key,
            fireworks_base_url=settings.fireworks_base_url,
            fireworks_model_name=settings.fireworks_model_name,
            ai_fireworks_timeout_seconds=settings.ai_fireworks_timeout_seconds,
            ai_fireworks_max_retries=settings.ai_fireworks_max_retries,
            ai_max_remote_tokens=settings.ai_max_remote_tokens,
            ai_temperature=settings.ai_temperature,
        )

        if providers is None:
            self.providers = {
                "fireworks_gemma": FireworksGemmaReasoningProvider(
                    config=fireworks_config,
                    http_client=DefaultHTTPClient(),
                ),
                "local_amd_model": LocalAmdModelProvider(
                    config=settings,
                    http_client=DefaultHTTPClient(),
                ),
            }
        else:
            self.providers = providers

        # Sandbox target guard config - allow localhost for dev/test fake sandbox
        self.sandbox_guard = SandboxTargetGuard(
            allow_localhost_sandbox=True,
            allow_private_ip_sandbox=True,
        )
        self.sandbox_runner = SandboxRunner(
            enabled=self.config.ai_sandbox_simulation_enabled,
            guard=self.sandbox_guard,
        )

    def analyze_execution(
        self,
        execution_id: UUID,
        request: AIProofOfRiskAnalysisRequest,
        context: dict[str, Any] | None = None,
    ) -> AIProofOfRiskAnalysisResponse:
        """Runs the analysis pipeline for a given execution."""

        # 1. Load execution evidence
        try:
            evidence = self.evidence_provider.get_execution_evidence(
                execution_id, context
            )
        except Exception as e:
            raise MissingExecutionError(str(e)) from e

        # 2. Validate eligibility
        if not evidence or not evidence.tenant_access_confirmed:
            raise MissingExecutionError(
                "Execution not found or cross-tenant access denied."
            )

        if not evidence.asset_verified:
            raise UnverifiedAssetError("Asset target is not verified as safe/owned.")

        if not evidence.raw_step_results_to_be_redacted:
            # Fallback to sanitized if raw doesn't exist for some reason
            raw_results = evidence.sanitized_step_results or []
        else:
            raw_results = evidence.raw_step_results_to_be_redacted

        # 3. Redact evidence
        redacted_results = []
        for step in raw_results:
            redaction_result = redact_evidence(step)
            redacted_results.append(redaction_result.sanitized_evidence)

        # 4. Normalize (Mock implementation for step 3)
        normalized_findings = []
        for step in redacted_results:
            if "finding_refs" in step:
                # Mock SanitizedFinding
                finding_refs = step.get("finding_refs")
                finding = SanitizedFinding(
                    finding_id=f"find_{step.get('step_id', 'unknown')}",
                    finding_type=str(finding_refs[0])
                    if isinstance(finding_refs, list) and finding_refs
                    else "Unknown",
                    asset_host=getattr(evidence, "original_target_hostname", "unknown")
                    or "unknown",
                    evidence=step.get("evidence", {}) if isinstance(step, dict) else {},
                )
                normalized_findings.append(finding)

        # 5. Choose route
        route = None
        if normalized_findings:
            req = RoutingRequest(
                execution_id=execution_id,
                finding_id=normalized_findings[0].finding_id,
                finding_type=normalized_findings[0].finding_type,
                complexity=FindingComplexity.complex
                if request.analysis_mode == "full_report"
                else FindingComplexity.simple,
                sanitized_evidence=normalized_findings[0].evidence,
                analysis_mode=request.analysis_mode,
                audience=request.audience,
                force_remote_reasoning=request.force_remote_reasoning,
                ai_router_mode=self.config.ai_router_mode,
            )
            route = route_finding(req, providers=self.providers)

        trace_val = route.selected_route.value if route else "none"
        model_routing_trace = [f"Selected route: {trace_val}"]

        # Outputs initialization
        attack_surface_graph = None
        exploitability_hypotheses = None
        digital_twin_scenarios = []

        if normalized_findings:
            # Generate graph
            attack_surface_graph_model = build_attack_surface_graph(normalized_findings)
            attack_surface_graph = attack_surface_graph_model.model_dump()

            # Generate Exploitability Hypotheses
            exploitability_hypotheses = ["Simulated attack hypothesis."]

            # Generate scenario
            try:
                scenario = generate_scenario(
                    finding=normalized_findings[0],
                    execution_id=execution_id,
                    scenario_sequence=1,
                )
                digital_twin_scenarios.append(scenario)
            except ScenarioSafetyViolation as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Skipping digital twin scenario generation: {e}")

        # 9. Sandbox simulation
        sandbox_proof_artifacts = None
        if (
            request.allow_sandbox_simulation
            and self.config.ai_sandbox_simulation_enabled
        ):
            sandbox_proof_artifacts = []
            if digital_twin_scenarios and self.config.ai_sandbox_base_url:
                for scen in digital_twin_scenarios:
                    # Create sandbox target ONLY from trusted config.
                    # NEVER from request.
                    target = SandboxTarget(
                        sandbox_base_url=self.config.ai_sandbox_base_url,
                        scenario_id=scen.scenario_id,
                        execution_id=execution_id,
                        allowed_host=evidence.original_target_hostname or "unknown",
                        allowed_scheme="https"
                        if self.config.ai_sandbox_base_url.startswith("https")
                        else "http",
                        is_ephemeral=True,
                        created_by_securescope=True,
                    )

                    try:
                        proof = self.sandbox_runner.run_scenario(scen, target)
                        sandbox_proof_artifacts.append(proof)
                    except Exception as e:
                        import logging

                        logger = logging.getLogger(__name__)
                        logger.error(f"Sandbox runner failed: {e}")

        # Fireworks provider integration
        use_fireworks = (
            route is not None
            and route.selected_route == AIRoute.fireworks_gemma
            and self.config.ai_router_mode != "deterministic"
            and "fireworks_gemma" in self.providers
        )
        fw_provider = self.providers.get("fireworks_gemma") if use_fireworks else None

        # Prepare inputs for Fireworks if needed
        safe_evidence = normalized_findings[0].evidence if normalized_findings else {}
        graph_summary = attack_surface_graph
        scenario_summary = (
            digital_twin_scenarios[0].model_dump() if digital_twin_scenarios else None
        )
        proof_summary = (
            [p.model_dump() for p in sandbox_proof_artifacts]
            if sandbox_proof_artifacts
            else None
        )

        # 10. Generate Risk Tribunal
        tribunal_verdict = None
        if digital_twin_scenarios:
            if use_fireworks and fw_provider:
                tribunal_verdict = fw_provider.generate_risk_tribunal(  # type: ignore
                    sanitized_evidence=safe_evidence,
                    attack_graph_summary=graph_summary,
                    digital_twin_scenario_summary=scenario_summary,
                    sandbox_proof_artifact_summary=proof_summary,
                    audience=request.audience.value,
                    safety_instructions=SAFETY_INSTRUCTIONS,
                )
            if not tribunal_verdict:
                tribunal_verdict = generate_risk_tribunal(digital_twin_scenarios[0])

        # 11. Remediation and Retest
        remediation_plan = None
        retest_plan = None
        if digital_twin_scenarios:
            if use_fireworks and fw_provider:
                remediation_plan = fw_provider.generate_remediation_plan(  # type: ignore
                    sanitized_evidence=safe_evidence,
                    attack_graph_summary=graph_summary,
                    digital_twin_scenario_summary=scenario_summary,
                    sandbox_proof_artifact_summary=proof_summary,
                    audience=request.audience.value,
                    safety_instructions=SAFETY_INSTRUCTIONS,
                )
            if not remediation_plan:
                remediation_plan = generate_remediation_plan(digital_twin_scenarios[0])

            retest_plan = generate_retest_plan(digital_twin_scenarios[0])

        # 13. Generate Report Summary
        report_data = None
        if use_fireworks and fw_provider:
            report_data = fw_provider.generate_executive_report(  # type: ignore
                sanitized_evidence=safe_evidence,
                attack_graph_summary=graph_summary,
                digital_twin_scenario_summary=scenario_summary,
                sandbox_proof_artifact_summary=proof_summary,
                audience=request.audience.value,
                safety_instructions=SAFETY_INSTRUCTIONS,
            )

        if not report_data:
            report_data = generate_report(
                audience=request.audience,
                attack_surface_graph=attack_surface_graph,
                exploitability_hypotheses=exploitability_hypotheses,
                scenarios=digital_twin_scenarios,
                sandbox_proofs=sandbox_proof_artifacts,
                tribunal_verdict=tribunal_verdict,
                remediation_plan=remediation_plan,
                retest_plan=retest_plan,
            )

        if route:
            model_routing_trace.append(f"Provider: {route.provider_name}")
            model_routing_trace.append(f"Model: {route.model_name}")
            model_routing_trace.append(
                f"Attempted remote call: {not route.avoided_remote_call}"
            )
            model_routing_trace.append(
                f"Estimated remote tokens: {route.estimated_remote_tokens}"
            )
            model_routing_trace.append(f"Fallback used: {route.fallback_used}")

        return AIProofOfRiskAnalysisResponse(
            analysis_id=f"analysis_{execution_id.hex[:8]}",
            execution_id=execution_id,
            status="completed",
            mode=request.analysis_mode,
            risk_summary="Analysis completed.",
            attack_surface_graph=attack_surface_graph,
            exploitability_hypotheses=exploitability_hypotheses,
            digital_twin_scenarios=digital_twin_scenarios,
            sandbox_proof_artifacts=sandbox_proof_artifacts,
            tribunal_verdict=tribunal_verdict,
            remediation_plan=remediation_plan,
            retest_plan=retest_plan,
            executive_summary=report_data.get(
                "executive_summary", "Summary not generated."
            ),
            technical_summary=report_data.get(
                "technical_summary", "Technical summary not generated."
            ),
            model_routing_trace=model_routing_trace,
            token_saving_estimate=route.estimated_local_tokens if route else 0,
            safety_notes=[report_data.get("safety_statement", "Safe mock data used.")],
            limitations=report_data.get("limitations", []),
            created_at=datetime.now(UTC).isoformat(),
        )

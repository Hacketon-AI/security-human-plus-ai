"""Sandbox Runner.

Executes deterministic proof-of-risk simulations inside the digital-twin sandbox.
Handlers are explicitly registered; no dynamic code execution or arbitrary payloads
are permitted.
"""

from typing import Protocol

from app.modules.ai_proof_of_risk.enums import ProofType, ScenarioType
from app.modules.ai_proof_of_risk.errors import (
    SandboxSimulationDisabledError,
    SandboxTargetRejectedError,
    UnsafeScenarioError,
    UnsupportedSandboxScenarioError,
)
from app.modules.ai_proof_of_risk.proof_artifact import create_proof_artifact
from app.modules.ai_proof_of_risk.sandbox_guards import SandboxTargetGuard
from app.modules.ai_proof_of_risk.schemas import (
    DigitalTwinScenario,
    ProofOfRiskArtifact,
    SandboxTarget,
)


class SandboxSimulationHandler(Protocol):
    """Protocol for approved deterministic sandbox simulation handlers."""

    def supports(self, scenario: DigitalTwinScenario) -> bool: ...

    def run(
        self, scenario: DigitalTwinScenario, sandbox_target: SandboxTarget
    ) -> ProofOfRiskArtifact: ...


class MissingCspSandboxSimulationHandler:
    def supports(self, scenario: DigitalTwinScenario) -> bool:
        return scenario.scenario_type == ScenarioType.missing_csp_browser_risk

    def run(
        self, scenario: DigitalTwinScenario, sandbox_target: SandboxTarget
    ) -> ProofOfRiskArtifact:
        return create_proof_artifact(
            scenario_id=scenario.scenario_id,
            execution_id=scenario.execution_id,
            proof_type=ProofType.csp_sandbox_marker_execution,
            sandbox_target=sandbox_target,
            evidence_summary=(
                "A harmless marker would execute only in the "
                "sandbox because CSP is missing."
            ),
            steps_summary=[
                "Load sandbox page",
                "Inject deterministic marker script",
                "Observe execution",
            ],
        )


class ClickjackingSandboxSimulationHandler:
    def supports(self, scenario: DigitalTwinScenario) -> bool:
        return (
            scenario.scenario_type == ScenarioType.missing_x_frame_options_clickjacking
        )

    def run(
        self, scenario: DigitalTwinScenario, sandbox_target: SandboxTarget
    ) -> ProofOfRiskArtifact:
        return create_proof_artifact(
            scenario_id=scenario.scenario_id,
            execution_id=scenario.execution_id,
            proof_type=ProofType.clickjacking_frame_allowed,
            sandbox_target=sandbox_target,
            evidence_summary=(
                "Sandbox page is frameable because "
                "X-Frame-Options/frame-ancestors are absent."
            ),
            steps_summary=[
                "Create transparent iframe overlay",
                "Load target sandbox page",
                "Record click coordinates",
            ],
        )


class InsecureCookieFlagSandboxSimulationHandler:
    def supports(self, scenario: DigitalTwinScenario) -> bool:
        return scenario.scenario_type == ScenarioType.insecure_cookie_flag_risk

    def run(
        self, scenario: DigitalTwinScenario, sandbox_target: SandboxTarget
    ) -> ProofOfRiskArtifact:
        return create_proof_artifact(
            scenario_id=scenario.scenario_id,
            execution_id=scenario.execution_id,
            proof_type=ProofType.insecure_cookie_attribute_confirmed,
            sandbox_target=sandbox_target,
            evidence_summary="Dummy sandbox cookie lacks Secure/HttpOnly/SameSite.",
            steps_summary=["Observe cookie headers", "Simulate cleartext interception"],
        )


class PermissiveCorsSandboxSimulationHandler:
    def supports(self, scenario: DigitalTwinScenario) -> bool:
        return scenario.scenario_type == ScenarioType.permissive_cors_simulation

    def run(
        self, scenario: DigitalTwinScenario, sandbox_target: SandboxTarget
    ) -> ProofOfRiskArtifact:
        return create_proof_artifact(
            scenario_id=scenario.scenario_id,
            execution_id=scenario.execution_id,
            proof_type=ProofType.permissive_cors_policy_confirmed,
            sandbox_target=sandbox_target,
            evidence_summary="Sandbox CORS policy allows unsafe origin pattern.",
            steps_summary=[
                "Send credentialed cross-origin request",
                "Verify allowed origin reflection",
            ],
        )


class SandboxRunner:
    """Orchestrates safe simulation runs inside the sandbox."""

    def __init__(
        self, enabled: bool = True, guard: SandboxTargetGuard | None = None
    ) -> None:
        self.enabled = enabled
        self.guard = guard or SandboxTargetGuard()
        self.handlers: list[SandboxSimulationHandler] = [
            MissingCspSandboxSimulationHandler(),
            ClickjackingSandboxSimulationHandler(),
            InsecureCookieFlagSandboxSimulationHandler(),
            PermissiveCorsSandboxSimulationHandler(),
        ]

    def run_scenario(
        self,
        scenario: DigitalTwinScenario,
        target: SandboxTarget,
    ) -> ProofOfRiskArtifact:
        """Executes a scenario securely against the sandbox target."""
        if not self.enabled:
            raise SandboxSimulationDisabledError(
                "Sandbox simulation is disabled by configuration."
            )

        # 1. Validate scenario safety constraints
        if scenario.production_exploit_allowed:
            raise UnsafeScenarioError("Scenario explicitly allows production exploit.")

        has_sandbox_only_constraint = False
        for constraint in scenario.safety_constraints:
            if constraint.constraint_id == "sandbox_only":
                has_sandbox_only_constraint = True
                break

        if not has_sandbox_only_constraint:
            raise UnsafeScenarioError(
                "Scenario is missing mandatory 'sandbox_only' safety constraint."
            )

        # 2. Validate target through Guard
        guard_result = self.guard.validate(target, scenario)
        if not guard_result.allowed:
            raise SandboxTargetRejectedError(
                f"Target rejected: {guard_result.reason}. "
                f"Violations: {guard_result.violations}"
            )

        # 3. Dispatch to handler
        for handler in self.handlers:
            if handler.supports(scenario):
                return handler.run(scenario, target)

        raise UnsupportedSandboxScenarioError(
            f"No handler for scenario type: {scenario.scenario_type}"
        )

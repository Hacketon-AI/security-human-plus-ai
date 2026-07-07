import sys
from uuid import uuid4

import pytest
from app.modules.ai_proof_of_risk.enums import (
    ExploitSimulationType,
    ProofType,
    ScenarioType,
)
from app.modules.ai_proof_of_risk.errors import (
    SandboxSimulationDisabledError,
    UnsafeScenarioError,
    UnsupportedSandboxScenarioError,
)
from app.modules.ai_proof_of_risk.sandbox_guards import SandboxTargetGuard
from app.modules.ai_proof_of_risk.sandbox_runner import SandboxRunner
from app.modules.ai_proof_of_risk.schemas import (
    DigitalTwinScenario,
    ProofOfRiskArtifact,
    SafetyConstraint,
    SandboxTarget,
)


def create_scenario(
    scenario_type: ScenarioType = ScenarioType.missing_csp_browser_risk,
    exploit_type: ExploitSimulationType = ExploitSimulationType.browser_xss_injection,
    production_exploit_allowed: bool = False,
    safety_constraints: list[SafetyConstraint] | None = None,
) -> DigitalTwinScenario:
    if safety_constraints is None:
        safety_constraints = [
            SafetyConstraint(
                constraint_id="sandbox_only",
                description="Must run in sandbox.",
            )
        ]
    return DigitalTwinScenario(
        scenario_id="scenario-123",
        execution_id=uuid4(),
        finding_refs=["finding-1"],
        vulnerability_pattern="Missing CSP",
        scenario_type=scenario_type,
        controls_replicated=[],
        sandbox_components=[],
        exploit_simulation_type=exploit_type,
        safe_proof_goal="Get token",
        expected_proof_token="token",
        safety_constraints=safety_constraints,
        production_exploit_allowed=production_exploit_allowed,
    )


def create_target(
    url: str, allowed_host: str, sandbox_owned: bool, created_by_securescope: bool
) -> SandboxTarget:
    return SandboxTarget(
        sandbox_base_url=url,
        scenario_id="scenario-123",
        execution_id=uuid4(),
        allowed_host=allowed_host,
        allowed_scheme="https" if url.startswith("https") else "http",
        is_ephemeral=True,
        created_by_securescope=created_by_securescope,
    )


def test_guard_rejects_public_internet_target() -> None:
    guard = SandboxTargetGuard()
    target = create_target("https://google.com", "example.com", True, True)
    res = guard.validate(target, create_scenario())
    assert not res.allowed


def test_guard_rejects_production_domain_target() -> None:
    guard = SandboxTargetGuard()
    target = create_target("https://example.com", "example.com", True, True)
    res = guard.validate(target, create_scenario())
    assert not res.allowed


def test_guard_rejects_metadata_ip() -> None:
    guard = SandboxTargetGuard()
    target = create_target("http://169.254.169.254", "example.com", True, True)
    res = guard.validate(target, create_scenario())
    assert not res.allowed


def test_guard_rejects_metadata_google_internal() -> None:
    guard = SandboxTargetGuard()
    target = create_target("http://metadata.google.internal", "example.com", True, True)
    res = guard.validate(target, create_scenario())
    assert not res.allowed


def test_guard_rejects_arbitrary_private_ip_when_not_sandbox_owned() -> None:
    guard = SandboxTargetGuard(allow_private_ip_sandbox=False)
    target = create_target("http://10.0.0.5", "example.com", False, True)
    res = guard.validate(target, create_scenario())
    assert not res.allowed


def test_guard_rejects_localhost_when_not_explicitly_sandbox_owned() -> None:
    guard = SandboxTargetGuard(allow_localhost_sandbox=False)
    target = create_target("http://localhost", "example.com", False, True)
    res = guard.validate(target, create_scenario())
    assert not res.allowed


def test_guard_allows_fake_sandbox_target_when_sandbox_owned() -> None:
    guard = SandboxTargetGuard()
    target = create_target(
        "http://sandbox-fake.sandbox.internal", "example.com", True, True
    )
    res = guard.validate(target, create_scenario())
    assert res.allowed


def test_guard_rejects_url_with_userinfo() -> None:
    guard = SandboxTargetGuard()
    target = create_target(
        "http://user:pass@sandbox-fake.sandbox.internal", "example.com", True, True
    )
    res = guard.validate(target, create_scenario())
    assert not res.allowed


def test_runner_sandbox_simulation_disabled_by_default() -> None:
    runner = SandboxRunner(enabled=False)
    scenario = create_scenario()
    target = create_target(
        "http://sandbox-fake.sandbox.internal", "example.com", True, True
    )
    with pytest.raises(SandboxSimulationDisabledError):
        runner.run_scenario(scenario, target)


def test_runner_accepts_only_approved_scenario_types() -> None:
    runner = SandboxRunner(enabled=True)
    scenario = create_scenario(scenario_type=ScenarioType.missing_csp_browser_risk)
    target = create_target(
        "http://sandbox-fake.sandbox.internal", "example.com", True, True
    )
    proof = runner.run_scenario(scenario, target)
    assert isinstance(proof, ProofOfRiskArtifact)


def test_runner_rejects_unsupported_scenario_type() -> None:
    runner = SandboxRunner(enabled=True)
    runner.handlers = []  # No handlers to force unsupported
    scenario = create_scenario()
    target = create_target(
        "http://sandbox-fake.sandbox.internal", "example.com", True, True
    )
    with pytest.raises(UnsupportedSandboxScenarioError):
        runner.run_scenario(scenario, target)


def test_runner_rejects_scenario_if_production_exploit_allowed() -> None:
    runner = SandboxRunner(enabled=True)
    scenario = create_scenario(production_exploit_allowed=True)
    target = create_target(
        "http://sandbox-fake.sandbox.internal", "example.com", True, True
    )
    with pytest.raises(UnsafeScenarioError):
        runner.run_scenario(scenario, target)


def test_runner_rejects_scenario_without_sandbox_only_safety_constraints() -> None:
    runner = SandboxRunner(enabled=True)
    scenario = create_scenario(safety_constraints=[])
    target = create_target(
        "http://sandbox-fake.sandbox.internal", "example.com", True, True
    )
    with pytest.raises(UnsafeScenarioError):
        runner.run_scenario(scenario, target)


def test_runner_never_uses_original_asset_target() -> None:
    runner = SandboxRunner(enabled=True)
    scenario = create_scenario()
    target = create_target(
        "http://sandbox-fake.sandbox.internal", "example.com", True, True
    )
    proof = runner.run_scenario(scenario, target)
    assert proof.production_target_used is False


def test_runner_returns_proof_of_risk_artifact_for_missing_csp() -> None:
    runner = SandboxRunner(enabled=True)
    scenario = create_scenario(scenario_type=ScenarioType.missing_csp_browser_risk)
    target = create_target(
        "http://sandbox-fake.sandbox.internal", "example.com", True, True
    )
    proof = runner.run_scenario(scenario, target)
    assert proof.proof_type == ProofType.csp_sandbox_marker_execution


def test_runner_returns_proof_of_risk_artifact_for_clickjacking() -> None:
    runner = SandboxRunner(enabled=True)
    scenario = create_scenario(
        scenario_type=ScenarioType.missing_x_frame_options_clickjacking
    )
    target = create_target(
        "http://sandbox-fake.sandbox.internal", "example.com", True, True
    )
    proof = runner.run_scenario(scenario, target)
    assert proof.proof_type == ProofType.clickjacking_frame_allowed


def test_runner_returns_proof_of_risk_artifact_for_insecure_cookie_flag() -> None:
    runner = SandboxRunner(enabled=True)
    scenario = create_scenario(scenario_type=ScenarioType.insecure_cookie_flag_risk)
    target = create_target(
        "http://sandbox-fake.sandbox.internal", "example.com", True, True
    )
    proof = runner.run_scenario(scenario, target)
    assert proof.proof_type == ProofType.insecure_cookie_attribute_confirmed


def test_runner_returns_proof_of_risk_artifact_for_permissive_cors() -> None:
    runner = SandboxRunner(enabled=True)
    scenario = create_scenario(scenario_type=ScenarioType.permissive_cors_simulation)
    target = create_target(
        "http://sandbox-fake.sandbox.internal", "example.com", True, True
    )
    proof = runner.run_scenario(scenario, target)
    assert proof.proof_type == ProofType.permissive_cors_policy_confirmed


def test_sandbox_runner_import_purity() -> None:

    forbidden = [
        "worker_runner",
        "worker_process",
        "http_transport",
        "celery_worker_bootstrap",
    ]
    for mod in forbidden:
        assert mod not in sys.modules

    runner_mod = sys.modules["app.modules.ai_proof_of_risk.sandbox_runner"]
    assert "subprocess" not in runner_mod.__dict__
    assert "os.system" not in sys.modules

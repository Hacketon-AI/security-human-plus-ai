import sys
import uuid

import pytest
from app.modules.ai_proof_of_risk.digital_twin_scenario import generate_scenario
from app.modules.ai_proof_of_risk.enums import ExploitSimulationType, ScenarioType
from app.modules.ai_proof_of_risk.errors import ScenarioSafetyViolation
from app.modules.ai_proof_of_risk.schemas import SanitizedFinding

_EXECUTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_finding(
    finding_type: str = "missing_csp",
    finding_id: str = "f1",
    asset_host: str = "app.example.com",
) -> SanitizedFinding:
    return SanitizedFinding(
        finding_type=finding_type,
        finding_id=finding_id,
        asset_host=asset_host,
        evidence={},
    )


def test_csp_scenario_generated() -> None:
    finding = _make_finding(finding_type="missing_csp")
    scenario = generate_scenario(
        finding=finding,
        execution_id=_EXECUTION_ID,
        scenario_sequence=1,
    )

    assert scenario.scenario_type is ScenarioType.missing_csp_browser_risk
    assert (
        scenario.exploit_simulation_type is ExploitSimulationType.browser_xss_injection
    )


def test_clickjacking_scenario_generated() -> None:
    finding = _make_finding(finding_type="missing_x_frame_options")
    scenario = generate_scenario(
        finding=finding,
        execution_id=_EXECUTION_ID,
        scenario_sequence=1,
    )

    assert scenario.scenario_type is ScenarioType.missing_x_frame_options_clickjacking


def test_scenario_says_production_exploit_not_allowed() -> None:
    finding = _make_finding()
    scenario = generate_scenario(
        finding=finding,
        execution_id=_EXECUTION_ID,
        scenario_sequence=1,
    )

    assert scenario.production_exploit_allowed is False


def test_scenario_has_safety_constraints() -> None:
    finding = _make_finding()
    scenario = generate_scenario(
        finding=finding,
        execution_id=_EXECUTION_ID,
        scenario_sequence=1,
    )

    assert len(scenario.safety_constraints) > 0

    descriptions = " ".join(c.description for c in scenario.safety_constraints).lower()
    assert "sandbox" in descriptions or "production" in descriptions, (
        "Expected safety constraints to mention"
        f" 'sandbox' or 'production'; got: {descriptions}"
    )


def test_scenario_has_sandbox_components() -> None:
    finding = _make_finding()
    scenario = generate_scenario(
        finding=finding,
        execution_id=_EXECUTION_ID,
        scenario_sequence=1,
    )

    assert scenario.sandbox_components, "sandbox_components must be non-empty"


def test_scenario_has_expected_proof_token() -> None:
    finding = _make_finding()
    scenario = generate_scenario(
        finding=finding,
        execution_id=_EXECUTION_ID,
        scenario_sequence=1,
    )

    assert isinstance(scenario.expected_proof_token, str)
    assert len(scenario.expected_proof_token) > 0


def test_unsupported_finding_type_raises() -> None:
    finding = _make_finding(finding_type="missing_hsts")
    with pytest.raises(ScenarioSafetyViolation):
        generate_scenario(
            finding=finding,
            execution_id=_EXECUTION_ID,
            scenario_sequence=1,
        )


def test_no_raw_token_in_scenario_output() -> None:
    finding = _make_finding()
    scenario = generate_scenario(
        finding=finding,
        execution_id=_EXECUTION_ID,
        scenario_sequence=1,
    )

    json_output = scenario.model_dump_json()
    assert "Bearer " not in json_output
    assert "eyJ" not in json_output
    assert "-----BEGIN" not in json_output
    assert "password=" not in json_output


def test_import_purity() -> None:
    modules_before = set(sys.modules.keys())

    import app.modules.ai_proof_of_risk  # noqa: F401

    new_modules = set(sys.modules.keys()) - modules_before

    forbidden = {
        "worker_runner",
        "worker_process",
        "http_transport",
        "celery_worker_bootstrap",
        "app.main",
    }
    for module_name in new_modules:
        base_name = module_name.rsplit(".", 1)[-1]
        assert base_name not in forbidden, (
            f"Importing app.modules.ai_proof_of_risk should not pull in '{module_name}'"
        )
        assert module_name not in forbidden, (
            f"Importing app.modules.ai_proof_of_risk should not pull in '{module_name}'"
        )

from unittest.mock import MagicMock

from app.modules.ai_proof_of_risk.enums import ScenarioType
from app.modules.ai_proof_of_risk.remediation import generate_remediation_plan
from app.modules.ai_proof_of_risk.schemas import DigitalTwinScenario


def test_generates_csp_remediation() -> None:
    scenario = MagicMock(spec=DigitalTwinScenario)
    scenario.scenario_type = ScenarioType.missing_csp_browser_risk
    remediation = generate_remediation_plan(scenario)
    assert "Content-Security-Policy" in str(remediation).replace(
        "-", ""
    ) or "CSP" in str(remediation)


def test_generates_clickjacking_remediation() -> None:
    scenario = MagicMock(spec=DigitalTwinScenario)
    scenario.scenario_type = ScenarioType.missing_x_frame_options_clickjacking
    remediation = generate_remediation_plan(scenario)
    assert "X-Frame-Options" in str(remediation) or "frame-ancestors" in str(
        remediation
    )


def test_generates_cookie_remediation() -> None:
    scenario = MagicMock(spec=DigitalTwinScenario)
    scenario.scenario_type = ScenarioType.insecure_cookie_flag_risk
    remediation = generate_remediation_plan(scenario)
    content = str(remediation).lower()
    assert "httponly" in content or "secure" in content or "samesite" in content


def test_generates_cors_remediation() -> None:
    scenario = MagicMock(spec=DigitalTwinScenario)
    scenario.scenario_type = ScenarioType.permissive_cors_simulation
    remediation = generate_remediation_plan(scenario)
    content = str(remediation).lower()
    assert "access-control-allow-origin" in content or "cors" in content


def test_generates_generic_remediation() -> None:
    scenario = MagicMock(spec=DigitalTwinScenario)
    scenario.scenario_type = "unknown"
    remediation = generate_remediation_plan(scenario)
    content = str(remediation).lower()
    assert "address missing security controls" in content

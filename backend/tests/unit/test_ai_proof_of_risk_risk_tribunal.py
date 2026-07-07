from unittest.mock import MagicMock

from app.modules.ai_proof_of_risk.risk_tribunal import generate_risk_tribunal
from app.modules.ai_proof_of_risk.schemas import DigitalTwinScenario


def test_risk_tribunal_returns_all_views() -> None:
    scenario = MagicMock(spec=DigitalTwinScenario)
    scenario.vulnerability_pattern = "Test"
    tribunal = generate_risk_tribunal(scenario)

    assert tribunal.attacker_view is not None
    assert tribunal.defender_view is not None
    assert tribunal.lab_view is not None
    assert tribunal.judge_verdict is not None


def test_risk_tribunal_does_not_include_production_exploit_instructions() -> None:
    scenario = MagicMock(spec=DigitalTwinScenario)
    scenario.vulnerability_pattern = "Test"
    tribunal = generate_risk_tribunal(scenario)

    # Assert no production target or exact exploit strings
    content = (
        f"{tribunal.attacker_view} {tribunal.defender_view} "
        f"{tribunal.lab_view} {tribunal.judge_verdict}"
    ).lower()

    assert "production" not in content
    assert "exploit instructions" not in str(tribunal.judge_verdict).lower()
    assert "exploit target" not in content

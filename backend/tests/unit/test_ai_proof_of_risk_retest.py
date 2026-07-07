from unittest.mock import MagicMock

from app.modules.ai_proof_of_risk.retest_planner import generate_retest_plan
from app.modules.ai_proof_of_risk.schemas import DigitalTwinScenario


def test_retest_creates_before_after_plan() -> None:
    scenario = MagicMock(spec=DigitalTwinScenario)
    scenario.vulnerability_pattern = "Test"
    plan = generate_retest_plan(scenario)

    assert plan.before_state is not None
    assert plan.expected_after_state is not None
    assert plan.safe_validation_template is not None


def test_retest_does_not_rerun_worker() -> None:
    scenario = MagicMock(spec=DigitalTwinScenario)
    scenario.vulnerability_pattern = "Test"
    plan = generate_retest_plan(scenario)

    # Assert there is no command to execute the worker
    content = str(plan).lower()
    assert "celery worker" not in content
    assert "rerun" not in content or "manual" in content or "api" in content

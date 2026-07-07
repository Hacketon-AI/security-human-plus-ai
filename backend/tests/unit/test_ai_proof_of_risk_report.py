from unittest.mock import MagicMock

from app.modules.ai_proof_of_risk.enums import Audience
from app.modules.ai_proof_of_risk.report_generator import generate_report
from app.modules.ai_proof_of_risk.schemas import DigitalTwinScenario


def test_generate_report() -> None:
    scenario = MagicMock(spec=DigitalTwinScenario)
    report = generate_report(
        audience=Audience.executive,
        attack_surface_graph=None,
        exploitability_hypotheses=None,
        scenarios=[scenario],
        sandbox_proofs=None,
        tribunal_verdict=None,
        remediation_plan=None,
        retest_plan=None,
    )

    assert report is not None

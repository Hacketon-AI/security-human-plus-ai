"""Remediation Planner.

Deterministic remediation plans for common vulnerabilities identified
in the digital twin.
"""

from app.modules.ai_proof_of_risk.enums import ScenarioType
from app.modules.ai_proof_of_risk.schemas import DigitalTwinScenario, RemediationPlan


def generate_remediation_plan(scenario: DigitalTwinScenario) -> RemediationPlan:
    """Generates a deterministic remediation plan based on the scenario type."""

    if scenario.scenario_type == ScenarioType.missing_csp_browser_risk:
        return RemediationPlan(
            immediate_fix="Implement Content-Security-Policy header.",
            developer_tasks=["Define CSP directives."],
            devops_tasks=["Deploy CSP header in proxy."],
            security_owner_tasks=["Review CSP policy."],
            safe_config_examples=["Content-Security-Policy: default-src 'self'"],
            verification_steps=["Check headers."],
            regression_tests=["Verify site works with CSP."],
            estimated_effort="Medium",
            risk_reduction="High",
        )
    elif scenario.scenario_type == ScenarioType.missing_x_frame_options_clickjacking:
        return RemediationPlan(
            immediate_fix="Add X-Frame-Options or CSP frame-ancestors.",
            developer_tasks=["Add header to response."],
            devops_tasks=["Configure web server to emit headers."],
            security_owner_tasks=["Verify framing policy."],
            safe_config_examples=["X-Frame-Options: DENY"],
            verification_steps=["Inspect response headers."],
            regression_tests=[
                "Test if application can be framed legitimately if required."
            ],
            estimated_effort="Low",
            risk_reduction="High",
        )
    elif scenario.scenario_type == ScenarioType.insecure_cookie_flag_risk:
        return RemediationPlan(
            immediate_fix="Set Secure and HttpOnly flags on cookies.",
            developer_tasks=["Update cookie setter logic."],
            devops_tasks=[],
            security_owner_tasks=["Audit all sensitive cookies."],
            safe_config_examples=["Set-Cookie: session=123; Secure; HttpOnly"],
            verification_steps=["Check Set-Cookie header."],
            regression_tests=["Ensure auth flows work."],
            estimated_effort="Low",
            risk_reduction="High",
        )
    elif scenario.scenario_type == ScenarioType.permissive_cors_simulation:
        return RemediationPlan(
            immediate_fix="Restrict Access-Control-Allow-Origin.",
            developer_tasks=["Configure strict origins."],
            devops_tasks=[],
            security_owner_tasks=["Review API consumers."],
            safe_config_examples=["Access-Control-Allow-Origin: https://trusted.com"],
            verification_steps=["Send Origin header and check response."],
            regression_tests=["Test trusted origins."],
            estimated_effort="Medium",
            risk_reduction="High",
        )
    # Generic fallback
    return RemediationPlan(
        immediate_fix="Address missing security controls.",
        developer_tasks=["Implement controls."],
        devops_tasks=[],
        security_owner_tasks=["Review security posture."],
        safe_config_examples=[],
        verification_steps=["Re-test."],
        regression_tests=["Run test suite."],
        estimated_effort="Unknown",
        risk_reduction="Unknown",
    )

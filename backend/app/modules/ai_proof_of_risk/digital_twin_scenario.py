"""Digital-twin scenario generator for AI Proof-of-Risk.

Generates scenario *plans* from sanitized findings. No execution is performed —
scenarios describe what a sandbox exploit runner would do, not run it. Every
scenario explicitly asserts that production exploit is not allowed and carries
mandatory safety constraints.

Pure functions, no I/O. See ``docs/ai-proof-of-risk-digital-twin-design.md``.
"""

from uuid import UUID

from app.modules.ai_proof_of_risk.enums import ExploitSimulationType, ScenarioType
from app.modules.ai_proof_of_risk.errors import ScenarioSafetyViolation
from app.modules.ai_proof_of_risk.schemas import (
    DigitalTwinScenario,
    SafetyConstraint,
    SandboxComponent,
    SanitizedFinding,
)

# ---------------------------------------------------------------------------
# Scenario templates keyed by finding type
# ---------------------------------------------------------------------------

_MANDATORY_SAFETY_CONSTRAINTS: list[SafetyConstraint] = [
    SafetyConstraint(
        constraint_id="sandbox_only",
        description=(
            "Scenario execution targets sandbox environment only."
            " Production exploit is not allowed."
        ),
    ),
    SafetyConstraint(
        constraint_id="no_arbitrary_payloads",
        description=(
            "No arbitrary exploit payloads. Only pre-defined safe proof tokens."
        ),
    ),
    SafetyConstraint(
        constraint_id="no_real_target_intrusion",
        description=(
            "No real target intrusion. Scenario operates on digital-twin replica."
        ),
    ),
    SafetyConstraint(
        constraint_id="time_bounded",
        description="Scenario execution is time-bounded with automatic termination.",
    ),
]


class _ScenarioTemplate:
    """Internal template for building a scenario from a finding type."""

    def __init__(
        self,
        *,
        scenario_type: ScenarioType,
        exploit_simulation_type: ExploitSimulationType,
        vulnerability_pattern: str,
        controls_replicated: list[str],
        sandbox_components: list[SandboxComponent],
        safe_proof_goal: str,
    ) -> None:
        self.scenario_type = scenario_type
        self.exploit_simulation_type = exploit_simulation_type
        self.vulnerability_pattern = vulnerability_pattern
        self.controls_replicated = controls_replicated
        self.sandbox_components = sandbox_components
        self.safe_proof_goal = safe_proof_goal


_TEMPLATES: dict[str, _ScenarioTemplate] = {
    "missing_csp": _ScenarioTemplate(
        scenario_type=ScenarioType.missing_csp_browser_risk,
        exploit_simulation_type=ExploitSimulationType.browser_xss_injection,
        vulnerability_pattern=(
            "Missing Content-Security-Policy allows inline script execution"
        ),
        controls_replicated=[
            "CSP header absent",
            "Inline script injection point",
        ],
        sandbox_components=[
            SandboxComponent(
                name="mock_web_server", role="Serves HTML without CSP header"
            ),
            SandboxComponent(
                name="headless_browser",
                role="Renders page and evaluates injected script",
            ),
            SandboxComponent(
                name="proof_collector",
                role="Captures proof token from script execution",
            ),
        ],
        safe_proof_goal=(
            "Demonstrate that a safe proof token can be"
            " exfiltrated via inline script when CSP is absent"
        ),
    ),
    "missing_x_frame_options": _ScenarioTemplate(
        scenario_type=ScenarioType.missing_x_frame_options_clickjacking,
        exploit_simulation_type=ExploitSimulationType.clickjacking_frame_embed,
        vulnerability_pattern=(
            "Missing X-Frame-Options allows page embedding in attacker iframe"
        ),
        controls_replicated=[
            "X-Frame-Options header absent",
            "No CSP frame-ancestors",
        ],
        sandbox_components=[
            SandboxComponent(
                name="mock_target_page",
                role="Serves frameable page without X-Frame-Options",
            ),
            SandboxComponent(
                name="attacker_page",
                role="Embeds target page in transparent iframe overlay",
            ),
            SandboxComponent(
                name="click_recorder",
                role="Records click coordinates proving UI redressing",
            ),
        ],
        safe_proof_goal=(
            "Demonstrate that target page can be framed"
            " and clicks redirected in sandbox"
        ),
    ),
    "insecure_cookie_flags": _ScenarioTemplate(
        scenario_type=ScenarioType.insecure_cookie_flag_risk,
        exploit_simulation_type=ExploitSimulationType.cookie_hijack_replay,
        vulnerability_pattern=(
            "Missing Secure/HttpOnly/SameSite flags expose cookies to interception"
        ),
        controls_replicated=[
            "Cookie without Secure flag",
            "Cookie without HttpOnly flag",
        ],
        sandbox_components=[
            SandboxComponent(
                name="mock_web_server", role="Sets cookies without security flags"
            ),
            SandboxComponent(
                name="network_tap", role="Captures cookies over simulated cleartext"
            ),
            SandboxComponent(
                name="proof_collector", role="Demonstrates cookie readable by script"
            ),
        ],
        safe_proof_goal=(
            "Demonstrate that cookies are accessible"
            " via JavaScript and cleartext in sandbox"
        ),
    ),
    "permissive_cors": _ScenarioTemplate(
        scenario_type=ScenarioType.permissive_cors_simulation,
        exploit_simulation_type=ExploitSimulationType.cors_credential_theft,
        vulnerability_pattern=(
            "Permissive CORS reflects arbitrary Origin with credentials"
        ),
        controls_replicated=[
            "Access-Control-Allow-Origin: *",
            "Access-Control-Allow-Credentials: true",
        ],
        sandbox_components=[
            SandboxComponent(
                name="mock_api_server", role="Responds with permissive CORS headers"
            ),
            SandboxComponent(
                name="attacker_origin",
                role="Cross-origin page making credentialed request",
            ),
            SandboxComponent(
                name="proof_collector", role="Captures cross-origin response data"
            ),
        ],
        safe_proof_goal=(
            "Demonstrate that cross-origin credentialed request succeeds in sandbox"
        ),
    ),
    "missing_hsts": _ScenarioTemplate(
        scenario_type=ScenarioType.generic_security_header_risk,
        exploit_simulation_type=ExploitSimulationType.missing_security_header_simulation,
        vulnerability_pattern="Missing Strict-Transport-Security enables downgrade attacks",  # noqa: E501
        controls_replicated=["HSTS header absent"],
        sandbox_components=[
            SandboxComponent(
                name="mock_web_server", role="Serves content without HSTS"
            ),
            SandboxComponent(
                name="network_tap", role="Simulates cleartext interception"
            ),
        ],
        safe_proof_goal="Demonstrate downgrade to cleartext HTTP in sandbox",
    ),
    "missing_referrer_policy": _ScenarioTemplate(
        scenario_type=ScenarioType.generic_security_header_risk,
        exploit_simulation_type=ExploitSimulationType.missing_security_header_simulation,
        vulnerability_pattern="Missing Referrer-Policy allows referer leakage",
        controls_replicated=["Referrer-Policy header absent"],
        sandbox_components=[
            SandboxComponent(
                name="mock_web_server", role="Serves content without Referrer-Policy"
            ),
            SandboxComponent(name="attacker_page", role="Captures referer payload"),
        ],
        safe_proof_goal="Demonstrate referer header leakage in sandbox",
    ),
    "missing_permissions_policy": _ScenarioTemplate(
        scenario_type=ScenarioType.generic_security_header_risk,
        exploit_simulation_type=ExploitSimulationType.missing_security_header_simulation,
        vulnerability_pattern="Missing Permissions-Policy allows unrestricted browser features",  # noqa: E501
        controls_replicated=["Permissions-Policy header absent"],
        sandbox_components=[
            SandboxComponent(
                name="mock_web_server", role="Serves content without Permissions-Policy"
            ),
            SandboxComponent(name="headless_browser", role="Executes capability check"),
        ],
        safe_proof_goal="Demonstrate unrestricted feature access in sandbox",
    ),
    "missing_x_content_type_options": _ScenarioTemplate(
        scenario_type=ScenarioType.generic_security_header_risk,
        exploit_simulation_type=ExploitSimulationType.missing_security_header_simulation,
        vulnerability_pattern="Missing X-Content-Type-Options enables MIME sniffing",
        controls_replicated=["X-Content-Type-Options header absent"],
        sandbox_components=[
            SandboxComponent(
                name="mock_web_server", role="Serves content without nosniff"
            ),
            SandboxComponent(name="headless_browser", role="Executes sniffed content"),
        ],
        safe_proof_goal="Demonstrate MIME sniffing XSS execution in sandbox",
    ),
    "missing_security_header": _ScenarioTemplate(
        scenario_type=ScenarioType.generic_security_header_risk,
        exploit_simulation_type=ExploitSimulationType.missing_security_header_simulation,
        vulnerability_pattern="Missing standard security header degrades defense-in-depth",  # noqa: E501
        controls_replicated=["Security header absent"],
        sandbox_components=[
            SandboxComponent(
                name="mock_web_server", role="Serves content without header"
            )
        ],
        safe_proof_goal="Demonstrate absence of defense-in-depth control in sandbox",
    ),
}


def generate_scenario(
    *,
    finding: SanitizedFinding,
    execution_id: UUID,
    scenario_sequence: int,
) -> DigitalTwinScenario:
    """Generate a digital-twin scenario plan for a sanitized finding.

    Returns a scenario plan with explicit safety constraints. The scenario
    targets sandbox only — ``production_exploit_allowed`` is always ``False``.

    Raises :class:`ScenarioSafetyViolation` if the finding type is not
    supported for scenario generation.
    """
    template = _TEMPLATES.get(finding.finding_type)
    if template is None:
        raise ScenarioSafetyViolation(
            f"No scenario template for finding type '{finding.finding_type}'. "
            "Only supported types may be simulated in the sandbox."
        )

    scenario_id = f"scenario:{execution_id}:{scenario_sequence}"
    proof_token = f"proof:{execution_id}:{finding.finding_id}"

    scenario = DigitalTwinScenario(
        scenario_id=scenario_id,
        execution_id=execution_id,
        finding_refs=[finding.finding_id],
        vulnerability_pattern=template.vulnerability_pattern,
        scenario_type=template.scenario_type,
        controls_replicated=template.controls_replicated,
        sandbox_components=template.sandbox_components,
        exploit_simulation_type=template.exploit_simulation_type,
        safe_proof_goal=template.safe_proof_goal,
        expected_proof_token=proof_token,
        safety_constraints=_MANDATORY_SAFETY_CONSTRAINTS,
        production_exploit_allowed=False,
    )

    return scenario

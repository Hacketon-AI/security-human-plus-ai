"""Prompt templates for AI Proof-of-Risk analysis.

Step 1 defines the template contracts and deterministic templates. Live model
calls are deferred — these templates are used by the routing and scenario
layers to estimate token cost and validate prompt safety.
"""

from app.modules.ai_proof_of_risk.enums import AIRoute

SAFETY_INSTRUCTIONS = """
SECURITY AND SAFETY DIRECTIVE:
- You are an isolated digital twin evaluator.
- You have NO network access and NO execution capability.
- Real target received safe non-destructive validation only.
- Real exploit simulation is sandbox-only.
- Never provide operational exploit steps for production targets.
- Do NOT include exploit payloads for RCE, SQLi, XSS, authentication bypass,
  persistence, lateral movement, privilege escalation, malware, DoS, 
  or data exfiltration.
- Use sanitized evidence only.
- Return strict JSON only.
"""

CLASSIFY_FINDING_COMPLEXITY_PROMPT = """
Classify the complexity of the finding as 'simple', 'medium', or 'complex'.
Return JSON matching schema: {"complexity": "simple|medium|complex"}.
"""

SUGGEST_ROUTE_PROMPT = """
Suggest a routing decision for this finding. Choices:
'rule_only', 'local_amd_model', 'fireworks_gemma'.
Return JSON matching schema: {"suggested_route": "..."}.
"""

SUMMARIZE_SIMPLE_FINDING_PROMPT = """
Provide a short, safe summary of the finding.
Return JSON matching schema: {"summary": "..."}.
"""

CHECK_EVIDENCE_SUFFICIENCY_PROMPT = """
Check if the evidence provided is sufficient to confirm the risk.
Return JSON matching schema: {"is_sufficient": true/false, "missing_elements": ["..."]}.
"""

GENERATE_SHORT_REMEDIATION_HINT_PROMPT = """
Generate a short remediation hint and estimated effort (low/medium/high).
Return JSON matching schema: {"hint": "...", "effort": "..."}.
"""

# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

_CLASSIFICATION_TEMPLATE = """\
You are a security analyst. \
Classify the following sanitized finding.

Finding type: {finding_type}
Asset: {asset_host}
Evidence summary: {evidence_summary}

Classify the severity and exploitability. Do not include raw tokens, credentials,
or headers in your response."""

_REASONING_TEMPLATE = """\
You are an expert security researcher. \
Analyze the following sanitized findings
and produce a proof-of-risk report.

Findings:
{findings_summary}

Attack surface graph:
{graph_summary}

Instructions:
1. Explain the attack chain from prerequisite to business impact.
2. Assess real-world exploitability.
3. Recommend prioritized remediations.
4. Do not include raw tokens, credentials, or headers."""

_RULE_ONLY_TEMPLATE = """Deterministic rule evaluation for: {finding_type}
Asset: {asset_host}
Missing control: {missing_control}
Remediation: {remediation}"""


# Map route → template.
_TEMPLATES: dict[AIRoute, str] = {
    AIRoute.rule_only: _RULE_ONLY_TEMPLATE,
    AIRoute.local_amd_model: _CLASSIFICATION_TEMPLATE,
    AIRoute.fireworks_gemma: _REASONING_TEMPLATE,
    AIRoute.deterministic_fallback: _RULE_ONLY_TEMPLATE,
}


def get_template(route: AIRoute) -> str:
    """Return the prompt template for a routing destination."""
    return _TEMPLATES[route]


def estimate_template_tokens(route: AIRoute) -> int:
    """Rough token count estimate for the template (excluding variable content).

    Used by the router for cost estimation. Actual token counts depend on
    the model's tokenizer; these are conservative overestimates.
    """
    template = _TEMPLATES[route]
    # Rough estimate: ~4 characters per token.
    return len(template) // 4

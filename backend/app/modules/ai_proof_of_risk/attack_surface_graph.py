"""Deterministic attack-surface graph generator.

Builds a directed graph from sanitized security findings, linking assets to
findings, missing controls, prerequisites, potential impacts, business risks,
and remediations. The graph is deterministic — same findings always produce the
same graph.

Supports: missing CSP, missing X-Frame-Options, insecure cookie flags,
permissive CORS, and missing HSTS. Pure functions, no I/O.
"""

from app.modules.ai_proof_of_risk.enums import GraphEdgeKind, GraphNodeKind
from app.modules.ai_proof_of_risk.errors import AttackGraphConstructionError
from app.modules.ai_proof_of_risk.schemas import (
    AttackSurfaceGraph,
    GraphEdge,
    GraphNode,
    SanitizedFinding,
)

# ---------------------------------------------------------------------------
# Finding type → graph fragment definitions
# ---------------------------------------------------------------------------

# Each entry maps a finding type to the deterministic graph fragment it
# produces: the missing control, impact chain, business risk, and remediation.

_FINDING_FRAGMENTS: dict[str, dict[str, str]] = {
    "missing_csp": {
        "control": "Content-Security-Policy header",
        "prerequisite": "Attacker-controlled content injection point",
        "impact": "Cross-site scripting (XSS) via inline script injection",
        "risk": "Session hijack, data theft, or defacement",
        "remediation": "Deploy strict CSP with nonce or hash-based script allowlisting",
    },
    "missing_x_frame_options": {
        "control": "X-Frame-Options or CSP frame-ancestors header",
        "prerequisite": "Victim visits attacker-controlled page with embedded iframe",
        "impact": "Clickjacking — user performs unintended actions",
        "risk": "Unauthorized transactions or privilege escalation via UI redressing",
        "remediation": "Set X-Frame-Options: DENY or CSP frame-ancestors 'none'",
    },
    "insecure_cookie_flags": {
        "control": "Secure, HttpOnly, and SameSite cookie attributes",
        "prerequisite": "Network attacker or XSS on the same origin",
        "impact": "Session cookie theft or fixation",
        "risk": "Account takeover via stolen session",
        "remediation": "Set Secure, HttpOnly, and SameSite=Strict on session cookies",
    },
    "permissive_cors": {
        "control": "Restrictive Access-Control-Allow-Origin policy",
        "prerequisite": "Victim authenticated to the target origin",
        "impact": "Cross-origin credential theft via malicious page",
        "risk": "Unauthorized API access using stolen credentials",
        "remediation": (
            "Restrict CORS to explicit trusted origins; never reflect Origin"
        ),
    },
    "missing_hsts": {
        "control": "Strict-Transport-Security header",
        "prerequisite": "Network attacker on the path (e.g. public Wi-Fi)",
        "impact": "SSL stripping — downgrade HTTPS to HTTP",
        "risk": "Credential interception or session hijack via cleartext traffic",
        "remediation": "Enable HSTS with max-age ≥ 31536000 and includeSubDomains",
    },
    "missing_referrer_policy": {
        "control": "Referrer-Policy header",
        "prerequisite": "User navigates from the application to an external site",
        "impact": "Leakage of sensitive URL parameters via Referer header",
        "risk": "Exposure of session tokens or PII to third parties",
        "remediation": "Set Referrer-Policy to 'strict-origin-when-cross-origin' or 'no-referrer'",
    },
    "missing_permissions_policy": {
        "control": "Permissions-Policy header",
        "prerequisite": "Third-party scripts or frames loaded in the application",
        "impact": "Unauthorized access to browser features (camera, microphone, geolocation)",
        "risk": "Privacy violation and potential data exfiltration",
        "remediation": "Deploy Permissions-Policy to explicitly allow or deny specific browser features",
    },
    "missing_x_content_type_options": {
        "control": "X-Content-Type-Options header",
        "prerequisite": "Application hosts user-uploaded content or untrusted data",
        "impact": "MIME-sniffing leading to XSS execution",
        "risk": "Malicious scripts executed in the context of the application",
        "remediation": "Set X-Content-Type-Options: nosniff",
    },
    "missing_security_header": {
        "control": "Standard HTTP Security Header",
        "prerequisite": "Attacker leverages missing defense-in-depth controls",
        "impact": "Increased susceptibility to various client-side attacks",
        "risk": "Broader attack surface for client-side exploitation",
        "remediation": "Implement missing recommended HTTP security headers",
    },
}


def build_attack_surface_graph(
    findings: list[SanitizedFinding],
) -> AttackSurfaceGraph:
    """Build a deterministic attack-surface graph from sanitized findings.

    Raises :class:`AttackGraphConstructionError` if no recognized findings are
    provided.
    """
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    missing_control_count = 0
    recognized_count = 0

    # Collect unique assets.
    seen_assets: set[str] = set()

    for finding in findings:
        fragment = _FINDING_FRAGMENTS.get(finding.finding_type)
        if fragment is None:
            continue

        recognized_count += 1

        # Asset node (deduplicated).
        asset_id = f"asset:{finding.asset_host}"
        if asset_id not in seen_assets:
            nodes.append(
                GraphNode(
                    node_id=asset_id,
                    kind=GraphNodeKind.asset,
                    label=finding.asset_host,
                )
            )
            seen_assets.add(asset_id)

        # Finding node.
        finding_node_id = f"finding:{finding.finding_id}"
        nodes.append(
            GraphNode(
                node_id=finding_node_id,
                kind=GraphNodeKind.finding,
                label=f"{finding.finding_type} on {finding.asset_host}",
            )
        )
        edges.append(
            GraphEdge(
                source_id=asset_id,
                target_id=finding_node_id,
                kind=GraphEdgeKind.contributes_to,
                label="exposes",
            )
        )

        # Missing control node.
        control_id = f"control:{finding.finding_id}"
        nodes.append(
            GraphNode(
                node_id=control_id,
                kind=GraphNodeKind.missing_control,
                label=fragment["control"],
            )
        )
        edges.append(
            GraphEdge(
                source_id=finding_node_id,
                target_id=control_id,
                kind=GraphEdgeKind.contributes_to,
                label="missing",
            )
        )
        missing_control_count += 1

        # Prerequisite node.
        prereq_id = f"prereq:{finding.finding_id}"
        nodes.append(
            GraphNode(
                node_id=prereq_id,
                kind=GraphNodeKind.prerequisite,
                label=fragment["prerequisite"],
            )
        )
        edges.append(
            GraphEdge(
                source_id=prereq_id,
                target_id=finding_node_id,
                kind=GraphEdgeKind.requires,
                label="requires",
            )
        )

        # Potential impact node.
        impact_id = f"impact:{finding.finding_id}"
        nodes.append(
            GraphNode(
                node_id=impact_id,
                kind=GraphNodeKind.potential_impact,
                label=fragment["impact"],
            )
        )
        edges.append(
            GraphEdge(
                source_id=finding_node_id,
                target_id=impact_id,
                kind=GraphEdgeKind.contributes_to,
                label="leads to",
            )
        )

        # Business risk node.
        risk_id = f"risk:{finding.finding_id}"
        nodes.append(
            GraphNode(
                node_id=risk_id,
                kind=GraphNodeKind.business_risk,
                label=fragment["risk"],
            )
        )
        edges.append(
            GraphEdge(
                source_id=impact_id,
                target_id=risk_id,
                kind=GraphEdgeKind.contributes_to,
                label="causes",
            )
        )

        # Remediation node.
        remediation_id = f"remediation:{finding.finding_id}"
        nodes.append(
            GraphNode(
                node_id=remediation_id,
                kind=GraphNodeKind.remediation,
                label=fragment["remediation"],
            )
        )
        edges.append(
            GraphEdge(
                source_id=remediation_id,
                target_id=finding_node_id,
                kind=GraphEdgeKind.mitigated_by,
                label="fixes",
            )
        )

    if recognized_count == 0:
        raise AttackGraphConstructionError(
            "No recognized finding types in input;"
            " cannot construct attack-surface graph."
        )

    return AttackSurfaceGraph(
        nodes=nodes,
        edges=edges,
        finding_count=recognized_count,
        missing_control_count=missing_control_count,
    )

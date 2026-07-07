import pytest
from app.modules.ai_proof_of_risk.attack_surface_graph import build_attack_surface_graph
from app.modules.ai_proof_of_risk.enums import GraphEdgeKind, GraphNodeKind
from app.modules.ai_proof_of_risk.errors import AttackGraphConstructionError
from app.modules.ai_proof_of_risk.schemas import SanitizedFinding


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


def test_graph_for_missing_csp() -> None:
    finding = _make_finding(finding_type="missing_csp")
    graph = build_attack_surface_graph([finding])

    node_kinds = {node.kind for node in graph.nodes}
    assert GraphNodeKind.asset in node_kinds
    assert GraphNodeKind.finding in node_kinds
    assert GraphNodeKind.missing_control in node_kinds
    assert GraphNodeKind.prerequisite in node_kinds
    assert GraphNodeKind.potential_impact in node_kinds
    assert GraphNodeKind.business_risk in node_kinds
    assert GraphNodeKind.remediation in node_kinds

    assert graph.finding_count == 1
    assert graph.missing_control_count == 1


def test_graph_for_missing_x_frame_options() -> None:
    finding = _make_finding(finding_type="missing_x_frame_options")
    graph = build_attack_surface_graph([finding])

    node_labels = [node.label for node in graph.nodes]
    combined = " ".join(node_labels).lower()
    has_relevant_label = (
        "x-frame-options" in combined
        or "frame" in combined
        or "clickjacking" in combined
    )
    assert has_relevant_label, (
        "Expected node labels to mention X-Frame-Options,"
        f" frame, or Clickjacking; got {node_labels}"
    )


def test_graph_edges_exist() -> None:
    finding = _make_finding(finding_type="missing_csp")
    graph = build_attack_surface_graph([finding])

    edge_kinds = {edge.kind for edge in graph.edges}
    assert GraphEdgeKind.contributes_to in edge_kinds
    assert GraphEdgeKind.requires in edge_kinds
    assert GraphEdgeKind.mitigated_by in edge_kinds


def test_graph_deduplicates_assets() -> None:
    findings = [
        _make_finding(finding_id="f1", asset_host="app.example.com"),
        _make_finding(finding_id="f2", asset_host="app.example.com"),
    ]
    graph = build_attack_surface_graph(findings)

    asset_nodes = [n for n in graph.nodes if n.kind == GraphNodeKind.asset]
    assert len(asset_nodes) == 1


def test_graph_multiple_findings() -> None:
    findings = [
        _make_finding(finding_type="missing_csp", finding_id="f1"),
        _make_finding(finding_type="missing_hsts", finding_id="f2"),
    ]
    graph = build_attack_surface_graph(findings)

    assert graph.finding_count == 2


def test_empty_findings_raises_error() -> None:
    with pytest.raises(AttackGraphConstructionError):
        build_attack_surface_graph([])


def test_unrecognized_finding_type_raises_error() -> None:
    finding = _make_finding(finding_type="unknown_type")
    with pytest.raises(AttackGraphConstructionError):
        build_attack_surface_graph([finding])

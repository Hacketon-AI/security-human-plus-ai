from typing import Any

from pydantic import BaseModel, Field


class DomainSafeScanRequest(BaseModel):
    domain: str = Field(..., description="The domain to scan")
    scheme: str = Field(..., description="The scheme to use (http or https)")
    confirm_authorized: bool = Field(..., description="Must be true to authorize scan")
    scan_type: str = Field("http_security_headers", description="Type of scan")
    run_ai_proof_of_risk: bool = Field(
        False, description="Run AI Proof of Risk integration"
    )


class DomainSafeScanResponse(BaseModel):
    scan_result: dict[str, Any]
    ai_analysis_summary: str | None = None
    routing_trace: Any | None = None
    attack_graph: Any | None = None
    digital_twin_scenarios: Any | None = None
    remediation: Any | None = None
    safety_statement: str | None = None
    scan_metadata: dict[str, Any] | None = None

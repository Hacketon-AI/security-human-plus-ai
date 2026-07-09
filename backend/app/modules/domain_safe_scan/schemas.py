from typing import Any, Optional
from pydantic import BaseModel, Field

class DomainSafeScanRequest(BaseModel):
    domain: str = Field(..., description="The domain to scan")
    scheme: str = Field(..., description="The scheme to use (http or https)")
    confirm_authorized: bool = Field(..., description="Must be true to authorize scan")
    scan_type: str = Field("http_security_headers", description="Type of scan")
    run_ai_proof_of_risk: bool = Field(False, description="Run AI Proof of Risk integration")

class DomainSafeScanResponse(BaseModel):
    scan_result: dict[str, Any]
    ai_analysis_summary: Optional[str] = None
    routing_trace: Optional[Any] = None
    attack_graph: Optional[Any] = None
    digital_twin_scenarios: Optional[Any] = None
    remediation: Optional[Any] = None
    safety_statement: Optional[str] = None
    scan_metadata: Optional[dict[str, Any]] = None

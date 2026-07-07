import ipaddress
import socket
from typing import Any
import httpx
from uuid import UUID

from app.modules.domain_safe_scan.schemas import DomainSafeScanRequest, DomainSafeScanResponse
from app.modules.ai_proof_of_risk.service import AIProofOfRiskService
from app.modules.ai_proof_of_risk.schemas import AIProofOfRiskAnalysisRequest
from app.modules.ai_proof_of_risk.execution_evidence_provider import ExecutionEvidenceProvider

class MockEvidenceProvider(ExecutionEvidenceProvider):
    def __init__(self, headers: dict[str, str], domain: str):
        self.headers = headers
        self.domain = domain

    def get_execution_evidence(self, execution_id: UUID, context: dict[str, Any] | None = None) -> Any:
        class MockEvidence:
            tenant_access_confirmed = True
            asset_verified = True
            raw_step_results_to_be_redacted = [
                {
                    "step_id": "http_security_headers",
                    "finding_refs": ["MissingSecurityHeaders"],
                    "evidence": {"headers": self.headers},
                }
            ]
            sanitized_step_results = raw_step_results_to_be_redacted
            original_target_hostname = self.domain

        return MockEvidence()

class DomainSafeScanService:
    async def analyze(self, request: DomainSafeScanRequest) -> DomainSafeScanResponse:
        if not request.confirm_authorized:
            raise ValueError("Scan not authorized")

        domain = request.domain
        
        # Validation for localhost and .internal strings
        if "localhost" in domain.lower() or domain.endswith(".local") or domain.endswith(".internal"):
            raise ValueError("Local or internal domains are not allowed")

        # Block userinfo
        if "@" in domain or ":" in domain:
            raise ValueError("Userinfo or port in domain is not allowed. Please provide only the domain name.")

        # Resolve IP to block private ranges
        try:
            ip_address = socket.gethostbyname(domain)
            ip_obj = ipaddress.ip_address(ip_address)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast:
                raise ValueError("Target resolves to a private, loopback, link-local, or multicast IP")
        except socket.gaierror:
            pass # DNS resolution failed, let httpx handle or fail

        url = f"{request.scheme}://{domain}"
        
        headers = {}
        missing_headers = []
        target_headers = [
            "Strict-Transport-Security",
            "Content-Security-Policy", 
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Referrer-Policy",
            "Permissions-Policy"
        ]

        try:
            async with httpx.AsyncClient(timeout=5.0, max_redirects=1, follow_redirects=True) as client:
                async with client.stream("GET", url) as response:
                    for k, v in response.headers.items():
                        headers[k.lower()] = v
        except Exception as e:
            return DomainSafeScanResponse(scan_result={"error": str(e)})

        for th in target_headers:
            if th.lower() not in headers:
                missing_headers.append(th)

        scan_result = {
            "found_headers": headers,
            "missing_headers": missing_headers,
            "status": "completed"
        }

        resp = DomainSafeScanResponse(scan_result=scan_result)

        if request.run_ai_proof_of_risk:
            dummy_id = UUID("00000000-0000-0000-0000-000000000000")
            ai_req = AIProofOfRiskAnalysisRequest(
                audience="executive",
                analysis_mode="full_report",
                allow_sandbox_simulation=False,
                force_remote_reasoning=False
            )
            
            provider = MockEvidenceProvider(headers=headers, domain=domain)
            ai_service = AIProofOfRiskService(evidence_provider=provider)
            
            try:
                ai_resp = ai_service.analyze_execution(dummy_id, ai_req)
                resp.ai_analysis_summary = ai_resp.executive_summary
                resp.routing_trace = ai_resp.model_routing_trace
                resp.attack_graph = ai_resp.attack_surface_graph
                resp.digital_twin_scenarios = ai_resp.digital_twin_scenarios
                resp.remediation = ai_resp.remediation_plan
                resp.safety_statement = ai_resp.safety_notes[0] if ai_resp.safety_notes else None
            except Exception as e:
                resp.ai_analysis_summary = f"AI integration failed: {e}"

        return resp

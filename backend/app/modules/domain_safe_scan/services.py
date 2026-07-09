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
    def __init__(self, headers: dict[str, str], domain: str, missing_headers: list[str]):
        self.headers = headers
        self.domain = domain
        self.missing_headers = missing_headers

    def get_execution_evidence(self, execution_id: UUID, context: dict[str, Any] | None = None) -> Any:
        mapping = {
            "Strict-Transport-Security": "missing_hsts",
            "Content-Security-Policy": "missing_csp",
            "X-Frame-Options": "missing_x_frame_options",
            "Referrer-Policy": "missing_referrer_policy",
            "Permissions-Policy": "missing_permissions_policy",
            "X-Content-Type-Options": "missing_x_content_type_options"
        }
        
        raw_steps = []
        for header in self.missing_headers:
            f_type = mapping.get(header, "missing_security_header")
            raw_steps.append({
                "step_id": f"missing_{header.lower()}",
                "finding_refs": [f_type],
                "evidence": {
                    "finding_type": f_type,
                    "title": f"Missing {header}",
                    "severity": "medium",
                    "affected_origin": self.domain,
                    "observed_header_absent": header,
                    "safe_evidence_summary": f"The {header} header is missing from the HTTP response.",
                    "remediation_hint": f"Configure the server to include the {header} header."
                }
            })

        class MockEvidence:
            tenant_access_confirmed = True
            asset_verified = True
            raw_step_results_to_be_redacted = raw_steps
            sanitized_step_results = raw_steps
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

        import uuid
        session_scan_id = f"sscan_{uuid.uuid4().hex[:8]}"
        correlation_id = f"corr_{uuid.uuid4().hex[:8]}"

        scan_metadata = {
            "source": "domain_safe_scan",
            "scan_id": session_scan_id,
            "correlation_id": correlation_id,
            "domain": request.domain,
            "scheme": request.scheme,
            "scan_type": request.scan_type,
            "authorization_confirmed": request.confirm_authorized,
            "evidence_source": "live_http_response_headers",
            "status": "completed",
            "finding_count": len(missing_headers)
        }

        resp = DomainSafeScanResponse(scan_result=scan_result, scan_metadata=scan_metadata)

        if request.run_ai_proof_of_risk:
            if not missing_headers:
                resp.ai_analysis_summary = "All recommended security headers are present. No attack surface graph or remediation required."
                resp.routing_trace = None
                resp.attack_graph = None
                resp.digital_twin_scenarios = None
                resp.remediation = None
                resp.safety_statement = "Safe: Target configuration adheres to HTTP security best practices."
                return resp

            dummy_id = UUID("00000000-0000-0000-0000-000000000000")
            ai_req = AIProofOfRiskAnalysisRequest(
                audience="executive",
                analysis_mode="full_report",
                allow_sandbox_simulation=False,
                force_remote_reasoning=False
            )
            
            provider = MockEvidenceProvider(headers=headers, domain=domain, missing_headers=missing_headers)
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

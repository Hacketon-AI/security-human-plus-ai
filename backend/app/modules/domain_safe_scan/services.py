import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from app.modules.ai_proof_of_risk.execution_evidence_provider import (
    ExecutionEvidenceProvider,
)
from app.modules.ai_proof_of_risk.schemas import AIProofOfRiskAnalysisRequest
from app.modules.ai_proof_of_risk.service import AIProofOfRiskService
from app.modules.domain_safe_scan.schemas import (
    DomainSafeScanRequest,
    DomainSafeScanResponse,
)


def _normalize_domain_input(domain_input: str) -> str:
    """Return a hostname from a bare domain or an HTTP(S) root URL."""
    raw_domain = domain_input.strip()
    if not raw_domain:
        raise ValueError("Domain is required")

    value_to_parse = raw_domain if "://" in raw_domain else f"//{raw_domain}"
    try:
        parsed = urlsplit(value_to_parse)
        hostname = parsed.hostname
    except ValueError as exc:
        raise ValueError("Invalid domain or URL") from exc

    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only http and https URLs are allowed")

    has_userinfo = (
        parsed.username is not None
        or parsed.password is not None
        or "@" in parsed.netloc
    )
    if has_userinfo:
        raise ValueError(
            "Userinfo or port in domain is not allowed. "
            "Please provide only the domain name."
        )

    # The colon in ``https://`` is outside netloc; a colon inside netloc is
    # therefore an explicit port (or an unsupported IPv6 literal).
    if ":" in parsed.netloc:
        raise ValueError(
            "Userinfo or port in domain is not allowed. "
            "Please provide only the domain name."
        )

    has_path_or_url_suffix = (
        parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or "?" in raw_domain
        or "#" in raw_domain
    )
    if has_path_or_url_suffix:
        raise ValueError("Please provide only the domain name, without a path or query")

    if hostname is None or any(character.isspace() for character in hostname):
        raise ValueError("Invalid domain or URL")
    if hostname.endswith(".."):
        raise ValueError("Invalid domain or URL")

    normalized_domain = hostname.lower().removesuffix(".")
    if not normalized_domain:
        raise ValueError("Invalid domain or URL")
    return normalized_domain


class MockEvidenceProvider(ExecutionEvidenceProvider):
    def __init__(
        self, headers: dict[str, str], domain: str, missing_headers: list[str]
    ):
        self.headers = headers
        self.domain = domain
        self.missing_headers = missing_headers

    def get_execution_evidence(
        self, execution_id: UUID, context: dict[str, Any] | None = None
    ) -> Any:
        mapping = {
            "Strict-Transport-Security": "missing_hsts",
            "Content-Security-Policy": "missing_csp",
            "X-Frame-Options": "missing_x_frame_options",
            "Referrer-Policy": "missing_referrer_policy",
            "Permissions-Policy": "missing_permissions_policy",
            "X-Content-Type-Options": "missing_x_content_type_options",
        }

        raw_steps = []
        for header in self.missing_headers:
            f_type = mapping.get(header, "missing_security_header")
            raw_steps.append(
                {
                    "step_id": f"missing_{header.lower()}",
                    "finding_refs": [f_type],
                    "evidence": {
                        "finding_type": f_type,
                        "title": f"Missing {header}",
                        "severity": "medium",
                        "affected_origin": self.domain,
                        "observed_header_absent": header,
                        "safe_evidence_summary": f"The {header} header is missing from the HTTP response.",  # noqa: E501
                        "remediation_hint": f"Configure the server to include the {header} header.",  # noqa: E501
                    },
                }
            )

        class MockEvidence:
            tenant_access_confirmed = True
            asset_verified = True
            raw_step_results_to_be_redacted = raw_steps
            sanitized_step_results = raw_steps
            original_target_hostname = self.domain

        return MockEvidence()


class DomainSafeScanService:
    async def analyze(
        self, request: DomainSafeScanRequest, *, organization_id: UUID
    ) -> DomainSafeScanResponse:
        if not request.confirm_authorized:
            raise ValueError("Scan not authorized")

        scheme = request.scheme.lower()
        if scheme not in {"http", "https"}:
            raise ValueError("Scheme must be http or https")

        domain = _normalize_domain_input(request.domain)

        # Validation for localhost and .internal strings
        if (
            "localhost" in domain.lower()
            or domain.endswith(".local")
            or domain.endswith(".internal")
        ):
            raise ValueError("Local or internal domains are not allowed")

        # Resolve IP to block private ranges
        try:
            ip_address = socket.gethostbyname(domain)
            ip_obj = ipaddress.ip_address(ip_address)
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_multicast
            ):
                raise ValueError(
                    "Target resolves to a private, loopback, link-local, or multicast IP"  # noqa: E501
                )
        except socket.gaierror:
            pass  # DNS resolution failed, let httpx handle or fail

        url = f"{scheme}://{domain}"

        headers = {}
        missing_headers = []
        target_headers = [
            "Strict-Transport-Security",
            "Content-Security-Policy",
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Referrer-Policy",
            "Permissions-Policy",
        ]

        try:
            async with httpx.AsyncClient(
                timeout=5.0, max_redirects=1, follow_redirects=True
            ) as client:
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
            "status": "completed",
        }

        import uuid

        session_scan_id = f"sscan_{uuid.uuid4().hex[:8]}"
        correlation_id = f"corr_{uuid.uuid4().hex[:8]}"

        scan_metadata = {
            "source": "domain_safe_scan",
            "organization_id": str(organization_id),
            "scan_id": session_scan_id,
            "correlation_id": correlation_id,
            "domain": request.domain,
            "scheme": request.scheme,
            "scan_type": request.scan_type,
            "authorization_confirmed": request.confirm_authorized,
            "evidence_source": "live_http_response_headers",
            "status": "completed",
            "finding_count": len(missing_headers),
        }

        resp = DomainSafeScanResponse(
            scan_result=scan_result, scan_metadata=scan_metadata
        )

        if request.run_ai_proof_of_risk:
            if not missing_headers:
                resp.ai_analysis_summary = "All recommended security headers are present. No attack surface graph or remediation required."  # noqa: E501
                resp.routing_trace = None
                resp.attack_graph = None
                resp.digital_twin_scenarios = None
                resp.remediation = None
                resp.safety_statement = "Safe: Target configuration adheres to HTTP security best practices."  # noqa: E501
                return resp

            dummy_id = UUID("00000000-0000-0000-0000-000000000000")
            ai_req = AIProofOfRiskAnalysisRequest(
                audience="executive",
                analysis_mode="full_report",
                allow_sandbox_simulation=False,
                force_remote_reasoning=False,
            )

            provider = MockEvidenceProvider(
                headers=headers, domain=domain, missing_headers=missing_headers
            )
            ai_service = AIProofOfRiskService(evidence_provider=provider)

            try:
                ai_resp = ai_service.analyze_execution(dummy_id, ai_req)
                resp.ai_analysis_summary = ai_resp.executive_summary
                resp.routing_trace = ai_resp.model_routing_trace
                resp.attack_graph = ai_resp.attack_surface_graph
                resp.digital_twin_scenarios = ai_resp.digital_twin_scenarios
                resp.remediation = ai_resp.remediation_plan
                resp.safety_statement = (
                    ai_resp.safety_notes[0] if ai_resp.safety_notes else None
                )
            except Exception as e:
                resp.ai_analysis_summary = f"AI integration failed: {e}"

        return resp

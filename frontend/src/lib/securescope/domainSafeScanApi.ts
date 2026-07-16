import { authenticatedRequest } from "./api";

export interface DomainSafeScanRequest {
  domain: string;
  scheme: string;
  confirm_authorized: boolean;
  scan_type: string;
  run_ai_proof_of_risk?: boolean;
}

export interface DomainSafeScanResponse {
  scan_id: string;
  domain: string;
  status: string;
  missing_headers: string[];
  ai_summary: string;
  attack_graph_preview?: {
    nodes: unknown[];
    edges: unknown[];
  };
}

export async function runDomainSafeScan(
  requestBody: DomainSafeScanRequest
): Promise<DomainSafeScanResponse> {
  return authenticatedRequest("/domain-safe-scan/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody),
  }) as Promise<DomainSafeScanResponse>;
}

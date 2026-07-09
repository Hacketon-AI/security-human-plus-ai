// API Client for Domain Safe Scan
const getApiBaseUrl = () => {
  if (typeof window !== "undefined") {
    // Client-side: relative to handle Next.js rewrites proxy
    return "";
  }
  return process.env.API_INTERNAL_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
};

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
    nodes: any[];
    edges: any[];
  };
}

export async function runDomainSafeScan(requestBody: DomainSafeScanRequest): Promise<DomainSafeScanResponse> {
  const url = `${getApiBaseUrl()}/domain-safe-scan/analyze`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => "Unknown error");
    throw new Error(`HTTP error ${response.status}: ${errorText}`);
  }

  return response.json();
}

export type AIAnalysisMode = "quick_summary" | "full_report" | "tribunal_only" | "graph_only";

export interface AIProofOfRiskRequest {
  analysis_mode: AIAnalysisMode;
  audience?: string;
  include_sanitized_evidence?: boolean;
  allow_sandbox_simulation?: boolean;
  force_remote_reasoning?: boolean;
}

export interface AttackSurfaceNode {
  id: string;
  type: string;
  label: string;
  description?: string;
}

export interface AttackSurfaceEdge {
  source: string;
  target: string;
  label: string;
}

export interface AttackSurfaceGraph {
  nodes: AttackSurfaceNode[];
  edges: AttackSurfaceEdge[];
  confidence_score?: number;
  limitations?: string[];
}

export interface DigitalTwinScenario {
  scenario_id: string;
  scenario_type: string;
  execution_id: string;
  finding_refs: string[];
  vulnerability_pattern: string;
  controls_replicated: string[];
  sandbox_components: string[];
  exploit_simulation_type: string;
  safe_proof_goal: string;
  expected_proof_token?: string;
  safety_constraints: string[];
  production_exploit_allowed: boolean;
}

export interface ProofOfRiskArtifact {
  proof_id: string;
  scenario_id: string;
  execution_id: string;
  proof_type: string;
  proof_token?: string;
  sandbox_target: string;
  confirmed: boolean;
  evidence_summary: string;
  steps_summary: string[];
  safety_notes: string[];
  production_target_used: boolean;
}

export interface RiskTribunalVerdict {
  attacker_view: string;
  defender_view: string;
  lab_view: string;
  judge_verdict: string;
  severity: string;
  confidence: string;
  false_positive_risk: string;
  business_impact: string;
  recommended_priority: string;
  limitations?: string[];
}

export interface RemediationPlan {
  immediate_fix?: string;
  developer_tasks?: string[];
  devops_tasks?: string[];
  security_owner_tasks?: string[];
  safe_config_examples?: string[];
  verification_steps?: string[];
  regression_tests?: string[];
  estimated_effort?: string;
  risk_reduction?: string;
}

export interface RetestPlan {
  retest_checklist?: string[];
  before_state?: string;
  expected_after_state?: string;
  safe_validation_template?: string;
  success_criteria?: string;
  evidence_needed?: string;
  risk_delta_if_fixed?: string;
}

export interface ModelRoutingTrace {
  selected_route: string;
  provider_name?: string;
  model_name?: string;
  local_provider_available: boolean;
  remote_provider_available: boolean;
  attempted_local_call: boolean;
  attempted_remote_call: boolean;
  avoided_remote_call: boolean;
  fallback_used: boolean;
  fallback_reason?: string;
  estimated_local_tokens?: number;
  estimated_remote_tokens?: number;
  token_saving_estimate?: number;
}

export interface AIProofOfRiskResponse {
  analysis_id: string;
  status: string;
  mode: AIAnalysisMode;
  created_at: string;
  execution_id: string;
  executive_summary?: string;
  technical_summary?: string;
  attack_surface_graph?: AttackSurfaceGraph;
  digital_twin_scenarios?: DigitalTwinScenario[];
  sandbox_proof_artifacts?: ProofOfRiskArtifact[];
  tribunal_verdict?: RiskTribunalVerdict;
  remediation_plan?: RemediationPlan;
  retest_plan?: RetestPlan;
  model_routing_trace?: string[];
  token_saving_estimate?: number;
  routing_details?: ModelRoutingTrace;
  limitations?: string[];
  safety_notes?: string[];
}

const getApiBaseUrl = () => {
  if (typeof window !== "undefined") {
    return "";
  }
  return process.env.API_INTERNAL_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
};

export const normalizeApiError = (err: any): string => {
  if (err instanceof Error) {
    if (err.message.includes("422")) {
      return "Validation error. Please check your inputs.";
    }
    // Mask raw internal errors
    return "An error occurred while communicating with the AI service.";
  }
  return "An unexpected error occurred.";
};

export async function analyzeProofOfRisk(
  executionId: string,
  payload: AIProofOfRiskRequest
): Promise<AIProofOfRiskResponse> {
  const isMock = process.env.NEXT_PUBLIC_USE_MOCK_API === "true";
  
  if (isMock) {
    // Generate safe mock response
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve({
          analysis_id: "mock_analysis_123",
          status: "completed",
          mode: payload.analysis_mode,
          created_at: new Date().toISOString(),
          execution_id: executionId,
          executive_summary: "This is a mock executive summary.",
          technical_summary: "This is a mock technical summary.",
          model_routing_trace: ["Rule Engine", "AMD ROCm Local Model"],
          routing_details: {
            selected_route: "local_amd_model",
            provider_name: "LocalAmdModelProvider",
            model_name: "gemma-local",
            local_provider_available: true,
            remote_provider_available: true,
            attempted_local_call: true,
            attempted_remote_call: false,
            avoided_remote_call: true,
            fallback_used: false,
            estimated_local_tokens: 150,
            estimated_remote_tokens: 0,
            token_saving_estimate: 150,
          },
          attack_surface_graph: {
            nodes: [
              { id: "asset_1", type: "asset", label: "Web Server" },
              { id: "finding_1", type: "finding", label: "Open Port" }
            ],
            edges: [
              { source: "asset_1", target: "finding_1", label: "has_finding" }
            ],
            confidence_score: 0.9
          },
          digital_twin_scenarios: [
            {
              scenario_id: "scenario_1",
              scenario_type: "exploitation",
              execution_id: executionId,
              finding_refs: ["finding_1"],
              vulnerability_pattern: "Missing authentication",
              controls_replicated: ["WAF"],
              sandbox_components: ["Mock Web"],
              exploit_simulation_type: "SQLi",
              safe_proof_goal: "Read /etc/passwd",
              safety_constraints: ["No DB write"],
              production_exploit_allowed: false,
            }
          ],
          sandbox_proof_artifacts: payload.allow_sandbox_simulation ? [
            {
              proof_id: "proof_1",
              scenario_id: "scenario_1",
              execution_id: executionId,
              proof_type: "read_file",
              sandbox_target: "Mock Web",
              confirmed: true,
              evidence_summary: "Successfully read file in sandbox.",
              steps_summary: ["Send payload", "Read response"],
              safety_notes: ["Sandbox only"],
              production_target_used: false,
            }
          ] : [],
          tribunal_verdict: {
            attacker_view: "Attacker uses open port.",
            defender_view: "WAF blocked it.",
            lab_view: "High",
            judge_verdict: "Vulnerable",
            severity: "High",
            confidence: "High",
            false_positive_risk: "Low",
            business_impact: "High",
            recommended_priority: "P1",
          },
          remediation_plan: {
            immediate_fix: "Close port.",
          },
          retest_plan: {
            retest_checklist: ["Port scan"],
          },
          safety_notes: [
            "Real exploit validation was performed only inside a controlled SecureScope digital twin sandbox. The production/authorized domain received safe, non-destructive validation only."
          ]
        });
      }, 1500);
    });
  }

  const url = `${getApiBaseUrl()}/ai-proof-of-risk/executions/${executionId}/analyze`;
  
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => "Unknown error");
      // Log safely
      console.error(`HTTP error ${response.status}`);
      throw new Error(`HTTP error ${response.status}`);
    }

    return response.json();
  } catch (error) {
    throw new Error(normalizeApiError(error));
  }
}

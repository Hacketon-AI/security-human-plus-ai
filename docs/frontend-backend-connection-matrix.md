# Backend-to-Frontend Connection Matrix
### AI Proof-of-Risk UI Integration

| UI Element | Backend Endpoint | Request Field Used | Response Field Rendered | Mock Fallback | Status |
|---|---|---|---|---|---|
| **Execution ID input/selector** | `POST /ai-proof-of-risk/executions/{id}/analyze` | `{execution_id}` (URL Path) | - | Yes | ✅ Connected |
| **Analysis mode selector** | `POST /ai-proof-of-risk/executions/{id}/analyze` | `analysis_mode` | `mode` | Yes | ✅ Connected |
| **Audience selector** | `POST /ai-proof-of-risk/executions/{id}/analyze` | `audience` | (Guides text content) | Yes | ✅ Connected |
| **Include sanitized evidence toggle** | `POST /ai-proof-of-risk/executions/{id}/analyze` | `include_sanitized_evidence` | - | Yes | ✅ Connected |
| **Sandbox simulation toggle** | `POST /ai-proof-of-risk/executions/{id}/analyze` | `allow_sandbox_simulation` | - | Yes | ✅ Connected |
| **Force remote reasoning toggle** | `POST /ai-proof-of-risk/executions/{id}/analyze` | `force_remote_reasoning` | - | Yes | ✅ Connected |
| **Run Analysis button** | `POST /ai-proof-of-risk/executions/{id}/analyze` | All above fields | - | Yes | ✅ Connected |
| **Analysis Summary panel** | `POST /ai-proof-of-risk/executions/{id}/analyze` | - | `technical_summary` | Yes | ✅ Connected |
| **AI Routing Trace panel** | `POST /ai-proof-of-risk/executions/{id}/analyze` | - | `routing_details.*`, `model_routing_trace` | Yes | ✅ Connected |
| **Attack Surface Graph panel** | `POST /ai-proof-of-risk/executions/{id}/analyze` | - | `attack_surface_graph` | Yes | ✅ Connected |
| **Digital Twin Scenario panel** | `POST /ai-proof-of-risk/executions/{id}/analyze` | - | `digital_twin_scenarios` | Yes | ✅ Connected |
| **Sandbox Proof Artifact panel** | `POST /ai-proof-of-risk/executions/{id}/analyze` | - | `sandbox_proof_artifacts` | Yes | ✅ Connected |
| **Risk Tribunal panel** | `POST /ai-proof-of-risk/executions/{id}/analyze` | - | `tribunal_verdict` | Yes | ✅ Connected |
| **Remediation Plan panel** | `POST /ai-proof-of-risk/executions/{id}/analyze` | - | `remediation_plan` | Yes | ✅ Connected |
| **Retest Plan panel** | `POST /ai-proof-of-risk/executions/{id}/analyze` | - | `retest_plan` | Yes | ✅ Connected |
| **Executive Report panel** | `POST /ai-proof-of-risk/executions/{id}/analyze` | - | `executive_summary` | Yes | ✅ Connected |
| **Safety Statement banner** | `POST /ai-proof-of-risk/executions/{id}/analyze` | - | `safety_notes` | Yes | ✅ Connected |
| **Dashboard AI Command Strip** | *Store / Static Env* | - | `latestAiProofOfRiskAnalysis` | Yes | ✅ Connected |
| **Dashboard Workflow Rail** | *Zustand Action* | - | Navigation to `openExecution` | Yes | ✅ Connected |
| **Dashboard Quick Actions** | *Zustand Action* | - | Navigation to `openExecution` | Yes | ✅ Connected |
| **Dashboard AI Routing Panel** | *Store / API cache* | - | `routing_details.*` from store | Yes | ✅ Connected |
| **Dashboard Attack Surface Preview** | *Store / API cache* | - | `attack_surface_graph` from store | Yes | ✅ Connected |
| **Dashboard Digital Twin Preview** | *Store / API cache* | - | `digital_twin_scenarios`, `sandbox_proof_artifacts` from store | Yes | ✅ Connected |
| **Dashboard Tribunal Preview** | *Store / API cache* | - | `tribunal_verdict` from store | Yes | ✅ Connected |
| **Scan My Authorized Domain Panel** | `POST /domain-safe-scan/analyze` | `domain`, `scheme`, `confirm_authorized`, `scan_type`, `run_ai_proof_of_risk` | `scan_result`, `ai_analysis_summary`, `attack_graph`, `scan_metadata` | No | ✅ Connected |

### Information Architecture & State Management

| State Element | Managed In | Source | Purpose |
|---|---|---|---|
| **`activeAnalysisSource`** | `Zustand store` (`useApp`) | UI Interaction (Dashboard / Domain Scan) | Differentiates between `manual_execution`, `demo_execution`, and `domain_safe_scan`. Drives conditional rendering across Dashboard and ExecutionDetailPage. |
| **`latestScanMetadata`** | `Zustand store` (`useApp`) | `POST /domain-safe-scan/analyze` | Holds ephemeral `scan_id` (Session Scan ID) and `correlation_id` from the backend to ensure identifiers are accurate and not misleading. |
| **`latestDomainSafeScanResult`** | `Zustand store` (`useApp`) | `POST /domain-safe-scan/analyze` | Contains full HTTP header scan results, routing trace, attack graph, and AI tribunal generated automatically by the backend. |
| **`latestAiProofOfRiskAnalysis`** | `Zustand store` (`useApp`) | `POST /ai-proof-of-risk/executions/{id}/analyze` | Holds on-demand AI reasoning results for historic mock/manual executions. |
| **Execution Detail Pages** | `ExecutionDetailPage.tsx` | UI State | Conditionally renders `Session Scan ID` vs `Execution ID` and suppresses persistent metadata (Scope/Safety) when visualizing an ephemeral `domain_safe_scan`. |
| **Dashboard Panels** | `DashboardPage.tsx` | UI State | Explicitly separated into "Section A: Manual Backend Security Validation" and "Section B: AI Proof-of-Risk Intelligence" to clarify system capabilities. |

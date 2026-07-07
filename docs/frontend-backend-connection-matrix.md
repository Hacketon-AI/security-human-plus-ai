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
| **Scan My Authorized Domain Panel** | `POST /domain-safe-scan/analyze` | `domain`, `scheme`, `scan_type` | `missing_headers`, `ai_summary`, `attack_graph_preview` | Yes | ✅ Connected |

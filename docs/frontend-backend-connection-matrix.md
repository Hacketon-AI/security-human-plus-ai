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

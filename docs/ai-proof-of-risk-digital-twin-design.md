# AI Proof-of-Risk Digital Twin Engine — Design Document

## Status: Step 4 Complete (AI Provider Integration)

> **Module**: `app.modules.ai_proof_of_risk`
> **Owner**: SecureScope Engineering
> **Hackathon Track**: AMD Hackathon Track 3 — AI Security Innovation

---

## 1. Product Positioning

SecureScope's AI Proof-of-Risk Digital Twin Engine transforms static security
findings into actionable, evidence-backed risk assessments. Instead of listing
"missing header" findings, it:

1. Builds an **attack-surface graph** showing how findings chain together.
2. Generates **digital-twin scenarios** that describe how a vulnerability could
   be exploited — safely, in a sandbox replica of the target.
3. Routes analysis to the **cheapest sufficient AI provider**, minimizing cost
   and latency while maximizing insight.

The result is a **proof of risk** — not a theoretical description, but a
demonstrable exploit path validated in an isolated sandbox.

---

## 2. AMD Hackathon Track 3 Strategy

### Track 3: AI-Powered Security Analysis

This engine is built for Track 3 with design principles borrowed from Track 1
(token-efficient routing). The strategy:

| Pillar | Approach |
|---|---|
| **Token efficiency** | Route simple findings to deterministic rules (zero tokens). Use local AMD model for medium tasks. Reserve Fireworks Gemma for complex reasoning only. |
| **AMD hardware path** | ROCm-accelerated local model serving on AMD Developer Cloud for classification tasks. Keeps sensitive evidence local. |
| **Safety-first** | All evidence redacted before AI routing. Digital-twin scenarios target sandbox only. Production exploit never allowed. |
| **Deterministic foundation** | Attack graphs and scenario plans are deterministic — same input always produces the same output. AI is layered on top, not required for core function. |

### Track 1 Inspiration: Token-Efficient Router

The security router borrows Track 1's cost-optimization approach:

- **`rule_only`**: Zero AI tokens. Deterministic rules for well-known header
  findings (missing CSP, X-Frame-Options, HSTS, cookie flags, CORS).
- **`local_amd_model`**: Zero remote tokens. Local Gemma 3 4B on AMD/ROCm for
  medium-complexity classification.
- **`fireworks_gemma`**: Remote inference via Fireworks API with Gemma 3 27B-IT
  for complex reasoning and report generation.
- **`deterministic_fallback`**: Graceful degradation when no provider is
  available.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Control Plane                        │
│                                                          │
│  validation_executions ──► evidence_normalizer           │
│                                │                         │
│                                ▼                         │
│                           redaction ──────────────────┐  │
│                                │                      │  │
│                                ▼                      │  │
│                        safety_policy                  │  │
│                                │                      │  │
│                    ┌───────────┼───────────┐          │  │
│                    ▼           ▼           ▼          │  │
│             security_router  attack_   digital_twin_  │  │
│                    │         surface_  scenario        │  │
│              ┌─────┼─────┐   graph                    │  │
│              ▼     ▼     ▼                            │  │
│         rule_only AMD  Fireworks                      │  │
│         (local)  local  remote                        │  │
│                  GPU    API                            │  │
└──────────────────────────────────────────────────────────┘
                         │
                         ▼ (future Step 2+)
              ┌─────────────────────┐
              │  Sandbox Executor   │
              │  (Digital Twin)     │
              │  Isolated container │
              │  No production      │
              │  access             │
              └─────────────────────┘
```

### Module Isolation

The `ai_proof_of_risk` module does **not** import:
- `worker_runner`, `worker_process`, `http_transport`
- `celery_worker_bootstrap`, `celery_worker`
- `app.main`

It depends only on `app.platform.errors` and its own submodules.

---

## 4. AMD Developer Cloud Role

### Local Model Path (ROCm)

The AMD Developer Cloud provides MI300X-class GPUs with ROCm for local model
serving. Benefits:

- **Data locality**: Sanitized evidence stays on-premises. No third-party API
  call for medium-complexity tasks.
- **Cost efficiency**: Local inference has zero per-token cost after provisioning.
- **Latency**: Sub-second classification on local hardware vs. network round-trip.

### Planned model: Gemma 3 4B (ROCm-optimized)

- Fits in single MI300X GPU memory.
- Sufficient for security finding classification and severity assessment.
- Quantized (INT8) for throughput.

### Integration plan (Step 2+)

1. Serve Gemma 3 4B via vLLM on ROCm.
2. Expose local HTTP endpoint behind internal network.
3. Provider implementation calls local endpoint, not external API.
4. Failover to Fireworks Gemma if local GPU is unavailable.

---

## 5. Fireworks / Gemma Reasoning Path

### Remote Model: Gemma 3 27B-IT via Fireworks API

For complex tasks requiring multi-step reasoning:

- Attack chain analysis across multiple findings.
- Business impact assessment with contextual reasoning.
- Proof-of-risk report generation with remediation prioritization.

### Integration plan (Step 2+)

1. Call Fireworks API with sanitized evidence only.
2. Structured output via Pydantic schema enforcement.
3. Response caching for identical evidence inputs.
4. Token budget enforcement per request.

---

## 6. Safe Real-Domain Boundary

### What touches the real authorized domain

- **Passive validation checks**: HTTP header presence, cookie flag inspection,
  CORS policy evaluation. Non-destructive, read-only.
- **Evidence collection**: Response headers and status codes only. No raw
  request/response bodies forwarded to AI.

### What never touches the real domain

- Exploit payloads.
- Authentication attempts.
- State-modifying requests.
- Brute force or enumeration.
- Any AI-generated action.

---

## 7. Digital Twin Sandbox Exploit Boundary

### Sandbox architecture (Step 2+)

The digital twin replicates the target's security posture in an isolated
container:

- **Mock web server**: Serves pages with the same missing controls.
- **Headless browser**: Renders pages and evaluates proof-of-concept scripts.
- **Proof collector**: Captures safe proof tokens demonstrating exploitability.

### What the sandbox does

- Demonstrates that a safe proof token can be captured when controls are absent.
- Records the exploit path for the proof-of-risk report.
- Time-bounded execution with automatic termination.

### What the sandbox never does

- Contact the real target.
- Execute arbitrary payloads.
- Persist state between runs.
- Access production credentials.

---

## 8. Redaction Policy

### Deterministic redaction guarantees

All evidence passes through `redaction.redact_evidence()` before reaching any
AI provider, prompt template, or non-sensitive storage. The following are
removed or masked:

| Category | Action |
|---|---|
| `Authorization` header | Removed entirely |
| `Cookie` header | Removed entirely |
| `Set-Cookie` header | Removed entirely |
| API keys (`X-Api-Key`, `Api-Key`) | Removed entirely |
| Bearer tokens | Pattern-masked |
| JWT values (`eyJ...`) | Pattern-masked |
| Private keys (PEM blocks) | Pattern-masked |
| Raw request body | Removed entirely |
| Raw response body | Removed entirely |
| Worker credential token | Removed entirely |
| Broker URL | Removed entirely |
| Database URL/DSN | Removed entirely |
| Kill-switch token | Removed entirely |
| Session IDs | Removed entirely |
| Long opaque secrets (≥32 chars) | Pattern-masked |

### Safety policy gate

After redaction, `safety_policy.assert_evidence_safe_for_ai()` performs a
second pass. If any forbidden pattern survives, the evidence is rejected with
`UnsafeEvidenceForAI` and never reaches an AI provider.

---

## 9. Step 1 Implementation Summary

### Created modules

| File | Purpose |
|---|---|
| `__init__.py` | Module docstring and boundary statement |
| `enums.py` | All domain enumerations |
| `schemas.py` | Pydantic v2 contracts (frozen, extra=forbid) |
| `errors.py` | Domain-specific exceptions |
| `redaction.py` | Deterministic evidence redaction |
| `evidence_normalizer.py` | Bridge from validation_executions evidence |
| `safety_policy.py` | Fail-closed safety checks |
| `security_router.py` | Token-efficient provider routing |
| `attack_surface_graph.py` | Deterministic graph generator |
| `digital_twin_scenario.py` | Scenario plan generator |
| `prompt_templates.py` | Template definitions and token estimation |
| `providers.py` | Provider protocol + fake implementations |

### Created tests

| File | Coverage |
|---|---|
| `test_ai_proof_of_risk_redaction.py` | Redaction of all sensitive categories |
| `test_ai_proof_of_risk_router.py` | Routing decisions for all complexity levels |
| `test_ai_proof_of_risk_attack_graph.py` | Graph generation for all finding types |
| `test_ai_proof_of_risk_digital_twin.py` | Scenario plans, safety constraints, import purity |

---

## 10. Next Steps

### Step 2: Sandbox Exploit Runner (Implemented)

The engine now safely simulates digital-twin scenarios using the **Sandbox Runner**.

#### Sandbox Runner Design
- **Safe Execution Environment**: Container-based digital-twin sandbox.
- **Approved Simulation Handlers**:
  - **Missing CSP**: `csp_sandbox_marker_execution`
  - **Clickjacking**: `clickjacking_frame_allowed`
  - **Insecure Cookie**: `insecure_cookie_attribute_confirmed`
  - **Permissive CORS**: `permissive_cors_policy_confirmed`
- **Proof Artifact Format**: Generates a `ProofOfRiskArtifact` containing:
  - `proof_id` and `proof_token`
  - Exploit confirmation details without raw secrets/payloads
  - `sandbox_only_safety_note` validating execution location
  - Safe sanitized metadata
- **Target Guard Policy**:
  - Rejects public internet targets (e.g., `https://google.com`).
  - Rejects production domains (prevents matching original asset).
  - Rejects metadata IPs (`169.254.169.254`) and `metadata.google.internal`.
  - Rejects arbitrary private IPs unless sandbox-owned.
  - Rejects localhost unless explicitly sandbox-owned.
  - Rejects URLs with embedded userinfo.
- **Sandbox-Only Real Exploit Simulation Boundary**:
  - The simulation **only** attacks the sandbox target (e.g. `sandbox.securescope.internal`).
  - Production targets are **never** used for active simulation.

#### What Step 2 Does Not Implement
- **No real network calls to production**.
- **No dynamic code execution of unverified arbitrary payloads**.
- **No persistence of exploit state**.

#### Why This is Safe for Hackathon Demo
This architecture ensures we can demonstrate "exploitability" by finding logical flaws and simulating their effects on a controlled replica, rather than aiming real attacks at live assets. The strict target guards and schema validation eliminate the risk of accidental production impact.

### Step 3: Service Orchestration and API Endpoint (Implemented)

The engine now supports full service orchestration and exposes a complete API endpoint for analyzing validation executions.

#### Service Orchestration
The `AIProofOfRiskService` serves as the primary entry point, orchestrating the end-to-end analysis workflow. It routes the analysis request based on the `analysis_mode` and orchestrates:
- **Redaction**: First-class safety pass before evidence reaches the router.
- **Evidence Retrieval**: Retrieves execution evidence via the provider boundary.
- **AI Router**: Decides between deterministic rules, local models, or remote API reasoning.
- **Digital Twin Execution**: Runs sandbox simulation only if requested and explicitly enabled in config.
- **Deterministic Generations**: Invokes sub-modules to generate risk tribunal, remediation plans, retest plans, and the final report.

#### Execution Evidence Provider Boundary
The service decouples from the execution domain using an `ExecutionEvidenceProvider` interface. This ensures that the engine only operates on well-defined `ExecutionEvidenceBundle`s. Currently, a `FakeExecutionEvidenceProvider` is used to mock evidence data, keeping the boundaries strict and testable while the real execution pipeline is integrated.

#### Sandbox Flag and Config Behavior
Sandbox exploitation is strictly opt-in and controlled via two flags:
1. `ServiceConfig.sandbox_enabled`: A global configuration defining whether sandbox simulations are permitted on the deployment.
2. `AIProofOfRiskAnalysisRequest.run_sandbox_simulation`: A per-request flag.

A simulation is only executed if **both** flags are true. By default, simulations are disabled. Under no circumstances is a production target used for sandbox simulations.

#### Deterministic Components
To minimize AI hallucinations, core engine outputs are generated deterministically where possible:
- **Risk Tribunal**: Generates varied stakeholder views (Attacker, Defender, Lab, Judge) without requiring an LLM call.
- **Remediation**: Maps common findings to standard, proven fixes (e.g., CSP, CORS, HSTS configurations).
- **Retest Plan**: Produces standardized before-and-after validation instructions without triggering any worker execution.
- **Report Generator**: Assembles all components (tribunal, remediation, retest, evidence, and proof artifacts) into a cohesive summary.

#### What is Fake
Currently, the following components are simulated ("fake"):
- `FakeExecutionEvidenceProvider`: Mocks the data coming from validation executions.
- Local AMD provider is mock-only.

### Step 4: AI Provider Integration (Fireworks Gemma) (Implemented)

The engine integrates Fireworks API for remote reasoning with Gemma 3 27B-IT.
- Implements `FireworksGemmaProvider` with strict schema validation.
- Validates prompt safety and injects strict json mode.
- Forces fallback if JSON decode fails or unsafe payloads are detected.

### Step 5: AMD/ROCm Local Model Integration (Next)

- [ ] Serve Gemma 3 4B via vLLM on ROCm.
- [ ] Implement `AMDLocalProvider` with health check and inference.
- [ ] Integration tests with local model endpoint.
- [ ] Failover to Fireworks when local GPU unavailable.

### Step 6: Persistence

- [ ] SQLAlchemy models for scenarios and proofs.
- [ ] Alembic migrations.
- [ ] Repository layer with async session.

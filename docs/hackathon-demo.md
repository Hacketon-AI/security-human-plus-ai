# SecureScope AI Proof-of-Risk Digital Twin - Hackathon Demo

## A. Product Pitch
SecureScope is an AI Proof-of-Risk Digital Twin platform for authorized security validation. We solve the problem of safely validating exploits in complex enterprise environments without causing production downtime. By utilizing digital twin technology, we ensure isolated, deterministic, and safe validation that never leaks secrets or executes arbitrary payloads in live systems.

## B. Track 3 Fit
SecureScope leverages AMD’s robust developer ecosystem:
- **Creativity**: Combining AI reasoning with isolated digital twin simulation.
- **Originality**: Safely bridging the gap between automated scanning and real-world exploit validation.
- **Completeness**: End-to-end containerized pipeline (routing, remote/local AI reasoning, deterministic fallback).
- **Use of AMD platforms**: Seamless integration with local AMD Developer Cloud infrastructure.
- **Product/Market Potential**: Designed for enterprise zero-trust security ecosystems.

## C. AMD Stack Usage
- **Fireworks AI / Gemma**: For deep reasoning and complex finding analysis.
- **AMD Developer Cloud + ROCm**: A local model endpoint for token-efficient local classification and hybrid routing.
- **Open-source Python/FastAPI framework**: For performant, asynchronous API orchestration.
- **Containerized deployment**: Ready-to-deploy Docker compose stack.

## D. Architecture
- **Safe real-domain validation**: All evidence is routed through an AI redaction layer.
- **AI redaction layer**: Removes secrets, tokens, and PII before any model sees it.
- **Hybrid AI router**: Routes based on complexity (Rule-only -> Local AMD -> Fireworks AI).
- **Local AMD model provider**: Acts as a token-efficient pre-processor and simple analyzer.
- **Fireworks provider**: Deeply analyzes complex vectors via Gemma models.
- **Digital twin sandbox proof**: Executes exploits securely outside the production boundary.
- **Risk tribunal / Remediation**: Provides structured output on exploitability and required fixes.

## E. Demo Modes
1. **Fully deterministic local demo**: Set `AI_ROUTER_MODE=deterministic`. No external model calls are made.
2. **Local AMD mock provider demo**: Included in the docker-compose stack. Use it to simulate the local endpoint when hardware isn't available.
3. **Fireworks-enabled demo**: Set `SECURESCOPE_FIREWORKS_API_KEY` in your `.env`.
4. **AMD Developer Cloud ROCm endpoint demo**: Start the optional ROCm container using the `amd-rocm` docker profile and configure `SECURESCOPE_AI_LOCAL_AMD_BASE_URL`.

## F. Run Commands
```bash
# 1. Prepare environment
cp .env.example .env

# 2. Build and start services
docker compose -f docker-compose.hackathon.yml up --build -d

# 3. Check health
curl http://localhost:8000/healthz

# 4. Run deterministic proof-of-risk (sandbox disabled)
curl -X POST http://localhost:8000/ai-proof-of-risk/executions/00000000-0000-0000-0000-000000000000/analyze \
  -H "Content-Type: application/json" \
  -d '{"analysis_mode": "quick_summary", "audience": "executive"}'

# 5. Enable Sandbox Simulation (requires SECURESCOPE_AI_SANDBOX_SIMULATION_ENABLED=true in .env)
curl -X POST http://localhost:8000/ai-proof-of-risk/executions/00000000-0000-0000-0000-000000000000/analyze \
  -H "Content-Type: application/json" \
  -d '{"allow_sandbox_simulation": true, "analysis_mode": "quick_summary", "audience": "executive"}'

# 6. Run Authorized Domain Safe Scan
curl -X POST http://localhost:8000/domain-safe-scan/analyze \
  -H "Content-Type: application/json" \
  -d '{"domain": "example.com", "scheme": "https", "confirm_authorized": true, "scan_type": "http_security_headers", "run_ai_proof_of_risk": true}'
```

To enable Fireworks:
Edit `.env`, add your `SECURESCOPE_FIREWORKS_API_KEY`. The router will utilize it for complex tasks. Note that Fireworks is strictly optional; if unavailable, the engine gracefully reverts to a safe deterministic fallback.

# 6. Optional Fireworks Live Smoke Test
If you have configured `SECURESCOPE_FIREWORKS_API_KEY` and want to verify the remote reasoning path safely:
```bash
./scripts/smoke_fireworks_ai.sh
```

To point to AMD Developer Cloud local model endpoint:
Start the compose stack with the AMD profile: `docker compose -f docker-compose.hackathon.yml --profile amd-rocm up -d`. Update `.env` `SECURESCOPE_AI_LOCAL_AMD_BASE_URL` to point to the real endpoint (e.g., `http://local-amd-model-rocm:8000/v1`).

## G. Safety Statement
Real exploit validation is performed only inside controlled SecureScope digital twin sandbox. Production or authorized domains receive safe, non-destructive validation only. No payloads are executed on the host system.

## H. What is Mocked
- **local-amd-model-mock**: Only intended for local demonstration. 
- **Real AMD ROCm endpoint**: Should be deployed on AMD Developer Cloud for the final production demo.
- **Tests**: Validation runs do not strictly require a GPU to pass.

## I. Frontend UI Demo Walkthrough
You can run the full end-to-end demo using Docker Compose:

1. Copy the environment template: `cp .env.example .env`
2. Start the full stack: `docker compose -f docker-compose.hackathon.yml up --build`
3. Open the frontend: `http://localhost:3000` (Backend API available at `http://localhost:8000`, health endpoint at `/healthz`)
4. **Observe the Dashboard**: The main dashboard immediately showcases SecureScope as an AI Proof-of-Risk platform. Note the top **AI Proof-of-Risk Command Strip** indicating the hybrid router mode, local AMD ROCm status, and Fireworks AI availability.
5. **Create Organization & Project**: Navigate to the Organizations page to create a new tenant using the "New Organization" button, then create a new project under the Projects page using the "New Project" button. This demonstrates the UI's multi-tenant capabilities.
6. **Explore Dashboard Panels**: Notice the **AI Proof-of-Risk Workflow Pipeline**, **AI Routing Pipeline**, **Attack Surface Preview**, **Digital Twin Proofs**, and **Risk Tribunal** panels on the dashboard.
7. **Launch Demo**: Click the **Run AI Proof-of-Risk Demo** button on the dashboard Workflow Rail or Quick Actions panel. This will navigate you to the detailed **AI Proof-of-Risk** view.
8. **Configure the analysis** (e.g. Mode: `full_report`, Audience: `security_engineer`) and click **Run Analysis**.
9. **Review Trace**: Explain the AI Routing Trace. The trace visually demonstrates how tokens are saved by checking local models (e.g. AMD ROCm) before routing to remote models (Fireworks).
10. **Review Attack Graph**: The attack surface graph visualizes how assets and findings relate, derived securely from backend intelligence.
11. **Review Digital Twin & Tribunal**: Explain the Digital Twin Scenario and Multi-Agent Risk Tribunal. Notice that `production_exploit_allowed: false` is strictly enforced.
12. **Review Safety Statement**: Point out the Safety Statement banner ensuring all simulated validation happened offline in the sandbox.
13. Return to the **Dashboard** and observe the panels update with the latest analysis data from the store.
14. **Scan My Authorized Domain**: On the dashboard, find the "Scan My Authorized Domain" panel. Enter your own domain, verify the strict HTTPS and "HTTP Security Headers only" constraint, check the authorization checkbox, and run the scan. This demonstrates safe real-world validation without active payloads, and safely feeds into the AI Proof-of-Risk system.

Note: 
- The `scripts/demo_ai_proof_of_risk.sh` demo script is still available if you want to bypass the UI and test the API directly.
- The UI mock mode is controlled via `NEXT_PUBLIC_USE_MOCK_API`.
- Fireworks API Key (`SECURESCOPE_FIREWORKS_API_KEY`) is optional.
- AMD Endpoint (`SECURESCOPE_AI_LOCAL_AMD_BASE_URL`) is optional for the local mock demo.
- API Networking: The frontend uses `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` for client-side browser requests and `API_INTERNAL_BASE_URL=http://securescope-api:8000` for Docker internal server-side requests.

## J. What Judges Should Evaluate
- Product workflow and clarity of vision.
- Intelligent AI routing design that balances cost, tokens, and logic.
- Secure digital twin proof-of-risk guarantees.
- Seamless AMD/Fireworks integration via standardized APIs.
- Container reproducibility and configuration-driven design.

## K. Track 3 Submission Materials
- [Pitch Deck Outline](./pitch-deck-outline.md)
- [3-Minute Demo Script](./demo-script-3-min.md)
- [Judging Alignment](./judging-alignment.md)
- [Submission Checklist](./submission-checklist.md)

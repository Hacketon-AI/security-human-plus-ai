# Submission Checklist

## Required Deliverables
- [x] All submissions containerized
- [x] `docker compose build` works
- [x] Backend starts successfully
- [x] Frontend starts successfully
- [x] No secrets committed (checked repository history/status)
- [x] `.env.example` provided
- [x] Fireworks optional config included in env example
- [x] AMD local provider optional/mock config included
- [x] Demo script (`scripts/demo_ai_proof_of_risk.sh`) works
- [x] Documentation is complete (design docs, pitch deck, script, etc.)

## Demo Commands

Run these commands to verify the environment locally:

```bash
# 1. Setup environment variables
cp .env.example .env

# 2. Build and start the stack
docker compose -f docker-compose.hackathon.yml up --build -d

# 3. Open the frontend UI
open http://localhost:3000

# 4. Verify backend health
curl http://localhost:8000/healthz

# 5. Run the CLI demo script
./scripts/demo_ai_proof_of_risk.sh
```

## Manual Browser Checklist
When navigating to `http://localhost:3000` and opening an Execution Detail view:
- [x] **AI Proof-of-Risk tab** is visible.
- [x] **Run Analysis button** executes successfully.
- [x] **Routing trace** panel is visible and populates correctly.
- [x] **Attack graph** panel is visible.
- [x] **Digital twin scenario** is visible.
- [x] **Safety statement** banner is visible.
- [x] **No target URL input** is exposed to the user (maintains safe boundaries).
- [x] **No raw evidence input** is exposed to the user (ensures deterministic redaction).

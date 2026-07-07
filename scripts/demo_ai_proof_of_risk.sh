#!/usr/bin/env bash
set -e

API_URL=${API_URL:-"http://localhost:8000"}
EXECUTION_ID="00000000-0000-0000-0000-000000000000"

echo "=== SecureScope AI Proof-of-Risk Hackathon Demo ==="
echo ""

echo "[1/2] Checking health endpoint..."
if curl -s -f "$API_URL/healthz" > /dev/null; then
    echo "✅ API is healthy."
else
    echo "❌ API health check failed! Is docker compose running?"
    exit 1
fi
echo ""

echo "[2/2] Running AI Proof-of-Risk Analysis..."
echo "Target Execution: $EXECUTION_ID (Mock Execution Evidence)"

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/ai-proof-of-risk/executions/$EXECUTION_ID/analyze" \
  -H "Content-Type: application/json" \
  -d '{"analysis_mode": "full_report", "audience": "executive", "allow_sandbox_simulation": false}')

HTTP_STATUS=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_STATUS" != "200" ]; then
    echo "❌ Analysis failed with status: $HTTP_STATUS"
    echo "$BODY"
    exit 1
fi

echo "✅ Analysis complete!"
echo ""
echo "--- Report Summary ---"

if command -v jq &> /dev/null; then
    ANALYSIS_ID=$(echo "$BODY" | jq -r '.analysis_id')
    ROUTING=$(echo "$BODY" | jq -r '.model_routing_trace | join(" -> ")')
    NODE_COUNT=$(echo "$BODY" | jq -r '.attack_surface_graph.nodes | length')
    SCENARIO_COUNT=$(echo "$BODY" | jq -r '.digital_twin_scenarios | length')
    PROOF_COUNT=$(echo "$BODY" | jq -r '.sandbox_proof_artifacts | length')
    
    echo "Analysis ID        : $ANALYSIS_ID"
    echo "Routing Path       : $ROUTING"
    echo "Attack Graph Nodes : $NODE_COUNT"
    echo "Scenarios Found    : $SCENARIO_COUNT"
    echo "Proof Artifacts    : $PROOF_COUNT"
    echo ""
    echo "Tribunal Verdict:"
    echo "$BODY" | jq -r '.tribunal_verdict.final_verdict // "No verdict available"'
else
    echo "(jq not installed, displaying raw response snippet)"
    echo "$BODY" | grep -o '"analysis_id":"[^"]*"' || true
    echo "$BODY" | grep -o '"model_routing_trace":\[[^]]*\]' || true
fi

echo ""
echo "--- Safety Statement ---"
echo "This proof-of-risk was generated safely against a digital twin sandbox. No production systems were exploited."

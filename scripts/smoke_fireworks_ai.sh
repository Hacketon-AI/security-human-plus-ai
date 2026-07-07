#!/usr/bin/env bash
set -e

API_URL=${API_URL:-"http://localhost:8000"}
EXECUTION_ID="00000000-0000-0000-0000-000000000000"

echo "=== SecureScope Fireworks AI Smoke Test ==="
echo ""

echo "Checking Fireworks API Key configuration..."
KEY_CHECK=$(docker compose -f docker-compose.hackathon.yml exec -T securescope-api sh -lc 'test -n "$SECURESCOPE_FIREWORKS_API_KEY" && echo "set" || echo "missing"' || echo "missing")
if [ "$KEY_CHECK" != "set" ]; then
    echo "❌ SECURESCOPE_FIREWORKS_API_KEY is not set in the container."
    echo "Please set it in .env to run this smoke test."
    exit 1
fi
echo "✅ SECURESCOPE_FIREWORKS_API_KEY is set."

echo "Checking Fireworks Model configuration..."
MODEL_NAME=$(docker compose -f docker-compose.hackathon.yml exec -T securescope-api sh -lc 'echo "${SECURESCOPE_FIREWORKS_MODEL_NAME:-missing}"' || echo "missing")
if [ "$MODEL_NAME" == "missing" ]; then
    echo "❌ SECURESCOPE_FIREWORKS_MODEL_NAME is not set in the container."
    exit 1
fi
echo "✅ SECURESCOPE_FIREWORKS_MODEL_NAME is set to: $MODEL_NAME"
echo ""

echo "Running AI Proof-of-Risk Analysis (force_remote_reasoning=true)..."

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/ai-proof-of-risk/executions/$EXECUTION_ID/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "analysis_mode": "full_report",
    "audience": "security_engineer",
    "include_sanitized_evidence": true,
    "allow_sandbox_simulation": false,
    "force_remote_reasoning": true
  }')

HTTP_STATUS=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_STATUS" != "200" ]; then
    echo "❌ Analysis failed with status: $HTTP_STATUS"
    exit 1
fi

echo "✅ Analysis complete!"
echo ""
echo "--- Routing Summary ---"

if command -v jq &> /dev/null; then
    ANALYSIS_ID=$(echo "$BODY" | jq -r '.analysis_id // "N/A"')
    SELECTED_ROUTE=$(echo "$BODY" | jq -r '.routing_details.selected_route // "N/A"')
    PROVIDER_NAME=$(echo "$BODY" | jq -r '.routing_details.provider_name // "N/A"')
    MODEL_NAME_USED=$(echo "$BODY" | jq -r '.routing_details.model_name // "N/A"')
    ATTEMPTED_REMOTE=$(echo "$BODY" | jq -r '.routing_details.attempted_remote_call // "N/A"')
    FALLBACK_USED=$(echo "$BODY" | jq -r '.routing_details.fallback_used // "N/A"')
    SAFETY_STATEMENT=$(echo "$BODY" | jq -r '.safety_notes[0] // "N/A"')

    echo "Analysis ID             : $ANALYSIS_ID"
    echo "Selected Route          : $SELECTED_ROUTE"
    echo "Provider Name           : $PROVIDER_NAME"
    echo "Model Name              : $MODEL_NAME_USED"
    echo "Attempted Remote Call   : $ATTEMPTED_REMOTE"
    echo "Fallback Used           : $FALLBACK_USED"
    echo ""
    echo "Safety Statement        : $SAFETY_STATEMENT"
    echo ""

    if [ "$FALLBACK_USED" == "true" ] || [ "$FALLBACK_USED" == "True" ]; then
        echo "⚠️ Fireworks live call was not used; deterministic fallback remained active."
    else
        echo "✅ Fireworks live call successful!"
    fi
else
    echo "(jq not installed, displaying raw safe snippet)"
    echo "$BODY" | grep -o '"analysis_id":"[^"]*"' || true
    echo "$BODY" | grep -o '"routing_details":{[^}]*}' || true
    echo "$BODY" | grep -o '"safety_notes":\[[^]]*\]' || true
fi

echo ""

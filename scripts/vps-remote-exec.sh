#!/usr/bin/env bash
set -e

VPS_USER="${1:-root}"
VPS_HOST="${2:-srv1691160.hstgr.cloud}"
VPS_PORT="${3:-22}"
TARGET_PATH="${4:-/opt/security-human-plus-ai}"

echo "===================================================="
echo "🚀 Connecting via SSH to $VPS_USER@$VPS_HOST:$VPS_PORT"
echo "===================================================="

ssh -o StrictHostKeyChecking=no -p "$VPS_PORT" -i ~/.ssh/id_ed25519 "$VPS_USER@$VPS_HOST" "
  set -e
  echo '==> Arrived at VPS. Navigating to $TARGET_PATH...'
  mkdir -p $TARGET_PATH
  cd $TARGET_PATH

  if [ ! -d '.git' ]; then
    echo '==> Initializing Git Repository at $TARGET_PATH...'
    git clone https://github.com/Hacketon-AI/security-human-plus-ai.git .
  else
    echo '==> Fetching & Pulling Latest Code...'
    git pull origin main || true
  fi

  chmod +x scripts/deploy-vps.sh
  ./scripts/deploy-vps.sh
"

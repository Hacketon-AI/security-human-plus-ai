#!/usr/bin/env bash
# ==============================================================================
# SecureScope — 1-Click VPS Initial Environment Provisioning Script
# Supported OS: Ubuntu 22.04 / 24.04 LTS, Debian 11/12
# ==============================================================================

set -eo pipefail

echo "===================================================="
echo "🛡️ SecureScope VPS Initial Setup Script"
echo "===================================================="

# Must be run as root or with sudo
if [ "$EUID" -ne 0 ]; then
  echo "⚠️ Please run this script with sudo or as root:"
  echo "   sudo bash scripts/setup-vps-environment.sh"
  exit 1
fi

# 1. System Package Updates
echo "🔄 Updating Apt Packages..."
apt-get update -y && apt-get upgrade -y
apt-get install -y curl wget git ufw htop ca-certificates gnupg lsb-release

# 2. Add 2GB Swap Space if memory is under 4GB
RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
if [ "$RAM_KB" -lt 4000000 ] && [ ! -f "/swapfile" ]; then
    echo "💾 Creating 2GB Swapfile for low-RAM VPS..."
    fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "✅ 2GB Swap created successfully."
fi

# 3. Install Official Docker & Docker Compose Plugin
if ! command -v docker &> /dev/null; then
    echo "🐳 Installing Docker Engine & Docker Compose Plugin..."
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    echo "✅ Docker installed successfully."
fi

# 4. Configure UFW Firewall
echo "🔒 Configuring UFW Firewall..."
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw allow 3000/tcp  # Frontend App
ufw allow 8000/tcp  # API Backend
ufw --force enable
echo "✅ UFW Firewall enabled."

# 5. Create Deploy Directory
DEPLOY_PATH="/opt/securescope"
echo "📁 Creating deployment directory at $DEPLOY_PATH..."
mkdir -p "$DEPLOY_PATH"
chown -R $SUDO_USER:$SUDO_USER "$DEPLOY_PATH" 2>/dev/null || true

echo "===================================================="
echo "✅ VPS Initial Environment Ready!"
echo "Next step: Clone your repository into $DEPLOY_PATH"
echo "  git clone <YOUR_GITHUB_REPO_URL> $DEPLOY_PATH"
echo "===================================================="

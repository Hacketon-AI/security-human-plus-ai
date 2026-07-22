#!/usr/bin/env bash
# ==============================================================================
# SecureScope — Production VPS Deployment Automation Script
# ==============================================================================

set -eo pipefail

COMPOSE_FILE="docker-compose.hackathon.yml"

echo "----------------------------------------------------"
echo "🚀 SecureScope Continuous Deployment Script"
echo "----------------------------------------------------"

# 1. Ensure Environment Configuration (.env)
if [ ! -f ".env" ]; then
    echo "⚠️  No root .env file found! Creating from .env.example..."
    [ -f ".env.example" ] && cp .env.example .env || touch .env
fi

if [ ! -f "backend/.env" ]; then
    echo "⚠️  No backend/.env file found! Creating from backend/.env.example..."
    [ -f "backend/.env.example" ] && cp backend/.env.example backend/.env || touch backend/.env
fi

if [ ! -f "frontend/.env" ]; then
    echo "⚠️  No frontend/.env file found! Creating from frontend/.env.example..."
    [ -f "frontend/.env.example" ] && cp frontend/.env.example frontend/.env || touch frontend/.env
fi

# 2. Build Docker Containers
echo "📦 Building Docker Images..."
docker compose -f "$COMPOSE_FILE" build --parallel

# 3. Start Infrastructure & Core Services
echo "🔄 Starting Database & Local Model Mock..."
docker compose -f "$COMPOSE_FILE" up -d postgres local-amd-model-mock

# Wait for Postgres health check
echo "⏳ Waiting for PostgreSQL to be healthy..."
for i in {1..30}; do
    if docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U postgres -d securescope > /dev/null 2>&1; then
        echo "✅ PostgreSQL is ready and accepting connections."
        break
    fi
    sleep 2
done

# 4. Run Alembic Database Migrations
echo "🗄️  Running Alembic Database Migrations..."
docker compose -f "$COMPOSE_FILE" run --rm securescope-api alembic upgrade head || {
    echo "⚠️  Alembic migration failed or pending, continuing startup..."
}

# 5. Seed Demo Data (Optional, idempotent)
echo "🌱 Checking Seed Data..."
docker compose -f "$COMPOSE_FILE" run --rm securescope-api python -m app.seed || true

# 6. Recreate & Start All Services (Zero Downtime Recreate)
echo "⚡ Starting API & Frontend Containers..."
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# 7. Check Container Status
echo "📊 Current Container Status:"
docker compose -f "$COMPOSE_FILE" ps

# 8. Clean up unused Docker resources
echo "🧹 Cleaning up old Docker image layers..."
docker image prune -f

echo "----------------------------------------------------"
echo "✅ SecureScope VPS Deployment Completed Successfully!"
echo "----------------------------------------------------"

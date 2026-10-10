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

# Never sign tokens with the development JWT secret published in the repository.
# Generate a per-server secret on first deploy; it persists in the untracked .env.
if ! grep -q '^SECURESCOPE_JWT_SECRET=' .env; then
    echo "🔐 Generating SECURESCOPE_JWT_SECRET in .env (existing sessions must sign in again)..."
    printf '\nSECURESCOPE_JWT_SECRET=%s\n' "$(openssl rand -hex 32)" >> .env
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
# Fail the deploy on migration errors: starting the API against a stale schema
# breaks at request time instead of here.
docker compose -f "$COMPOSE_FILE" run --rm securescope-api alembic upgrade head

# 5. Seed Demo Data — opt-in only. app.seed DELETES all orgs, projects, assets,
# authorizations, and executions before inserting demo rows.
if [ "${SEED_DEMO_DATA:-0}" = "1" ]; then
    echo "🌱 SEED_DEMO_DATA=1: resetting database to demo data..."
    docker compose -f "$COMPOSE_FILE" run --rm securescope-api python -m app.seed
fi

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

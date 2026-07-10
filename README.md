# SecureScope — Authorized Security Validation Control

SecureScope is a security-focused human+AI platform for orchestrating authorized security validation against verified assets within enforceable scope, time windows, and safety controls.

---

## Quick Start (Development)

### Prerequisites

- Python 3.12+
- Node.js 18+ / Bun
- PostgreSQL
- Docker (optional, for full stack via docker-compose)

### Backend

```bash
cd backend
cp .env.example .env   # adjust DATABASE_DSN
pip install -e ".[dev]"
alembic upgrade head
python -m app.seed     # seed demo data (see Dev Login below)
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

---

## Dev Login

The application uses a **development auth adapter** — no real OIDC/SSO is required in development. Login is done by supplying an **Organization ID (UUID)**.

A quick **"⚡ Dev Login (bypass)"** button is   available on the login page when `NEXT_PUBLIC_DEFAULT_ORG_ID` is set in `frontend/.env`.

---

## Demo Users / Organizations

After running `python -m app.seed` from the `backend/` directory, the following organizations are available. Use the **Organization ID** to log in.

| Organization | Slug | Organization ID (login) | Status |
|---|---|---|---|
| **BRI Ventures Digital** | `bri-ventures` | `a3f7c2d1-8b4e-4f9a-b6c3-2e1d5f8a9b0c` | active |
| **Telkom Sigma Cloud** | `telkom-sigma` | `b8e4d6f2-1c7a-4e2b-9d5f-3a0c8e7b4d1f` | active |
| **Mandiri Sekuritas** | `mandiri-sek` | `c1d9e5a3-4f2b-4c8d-a7e1-6b3d0f9c2e5a` | active |

### Recommended dev login

The default dev bypass button uses **BRI Ventures Digital**:

```
Organization ID : a3f7c2d1-8b4e-4f9a-b6c3-2e1d5f8a9b0c
```

This org has the most complete seed data:
- 4 assets across 2 projects (3 verified, 1 pending)
- 2 active authorizations (Q3 pentest + OJK compliance scan)
- 2 active engagements running right now
- 4 validation executions (2 completed with full evidence, 1 executing, 1 queued)

### How to log in manually

1. Open the frontend (default: `http://localhost:3000`)
2. In the **Organization ID** field, paste one of the UUIDs above
3. Click **Authenticate** — email, password, and MFA are not validated in development mode

Or click **⚡ Dev Login (bypass)** to skip the form entirely (uses `a3f7c2d1-8b4e-4f9a-b6c3-2e1d5f8a9b0c`).

---

## Seed Data Reference

### Organizations → Projects → Assets

```
BRI Ventures Digital (a3f7c2d1-8b4e-4f9a-b6c3-2e1d5f8a9b0c)
├── Pinjamanku Lending API (project)
│   ├── Pinjamanku Partner API (Production)  — api / production  / verified  (2c9f5a8e-…)
│   ├── Pinjamanku Staging Gateway           — api / staging     / verified  (3d0e6b9f-…)
│   └── OAuth 2.0 Token Service              — api / production  / pending   (4e1f7c0a-…)
└── OJK Compliance Portal (project)
    └── OJK Reporting Portal (Web)           — web / production  / verified  (5f2a8d1b-…)

Telkom Sigma Cloud (b8e4d6f2-1c7a-4e2b-9d5f-3a0c8e7b4d1f)
├── SigmaCloud Management Console (project)
│   ├── SigmaCloud Control Plane API         — api / production  / verified  (6a3b9e2c-…)
│   └── SigmaCloud Web Console               — web / production  / verified  (7b4c0f3d-…)
└── SIEM Event Ingest API (project)
    ├── SIEM Collector Ingest Endpoint       — api / production  / verified  (8c5d1a4e-…)
    └── SIEM Ingest (Preproduction)          — api / preprod     / draft     (9d6e2b5f-…)

Mandiri Sekuritas (c1d9e5a3-4f2b-4c8d-a7e1-6b3d0f9c2e5a)
└── MOST Trading Platform (project)
    ├── MOST Order Routing API               — api / production  / verified  (0e7f3c6a-…)
    └── MOST Web Trading App                 — web / production  / verified  (1f8a4d7b-…)
```

### Active Engagements

| Engagement | Organization | Status | Window | Contact |
|---|---|---|---|---|
| Pinjamanku API — TLS & Auth Header Sweep | BRI Ventures Digital | `active` | −90 min … +6.5 hr | Reza Firmansyah |
| OJK Portal — Mandatory Compliance Scan | BRI Ventures Digital | `active` | −2 hr … +14 hr | Dewi Anggraini |
| SigmaCloud API — Auth & Rate-Limit Validation | Telkom Sigma Cloud | `active` | −30 min … +5 hr | Hendra Kusuma |
| MOST v4.2.0 — Pre-Release Security Gate | Mandiri Sekuritas | `scheduled` | tomorrow | Agus Priyanto |

### Validation Executions

| # | Asset | Template | Status | Outcome |
|---|---|---|---|---|
| 1 | Pinjamanku Partner API (prod) | HTTP_SECURITY_HEADER_VALIDATION | `succeeded` | validated |
| 2 | Pinjamanku Staging Gateway | TLS_VERSION_VALIDATION | `succeeded` | validated |
| 3 | SigmaCloud Control Plane API | HTTP_SECURITY_HEADER_VALIDATION | `executing` | — |
| 4 | OJK Reporting Portal | TLS_VERSION_VALIDATION | `queued` | — |

---

## Environment Variables

### `frontend/.env`

| Variable | Description | Default |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Backend API URL | `http://localhost:8000` |
| `NEXT_PUBLIC_DEFAULT_ORG_ID` | UUID used by Dev Login bypass button | `a3f7c2d1-8b4e-4f9a-b6c3-2e1d5f8a9b0c` |

### `backend/.env`

| Variable | Description |
|---|---|
| `SECURESCOPE_DATABASE_DSN` | PostgreSQL DSN (`postgresql+asyncpg://...`) |
| `SECURESCOPE_ENVIRONMENT` | `development` / `staging` / `production` |
| `SECURESCOPE_DEVELOPMENT_AUTH_ENABLED` | Set `false` to disable dev header auth |

---

## Security Notes

- The `X-Organization-Id` header adapter is **development only** — it must not be used in staging or production.
- The **⚡ Dev Login** button only renders when `NEXT_PUBLIC_DEFAULT_ORG_ID` is set. Remove or empty it in any deployed environment.
- See `.claude/rules/` for security boundary rules enforced in this codebase.

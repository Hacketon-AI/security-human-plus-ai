# Stack Decision: Python-First

## Decision

Use Python for the backend control plane, scanner adapters, result
normalization, security policy evaluation, and asynchronous orchestration.
Use TypeScript and React/Next.js for the browser interface.

## Initial Stack

| Area | Choice |
|---|---|
| Runtime | Python 3.12+ |
| API | FastAPI |
| Validation | Pydantic v2 |
| ORM | SQLAlchemy 2.x |
| Migration | Alembic |
| Database | PostgreSQL |
| Task queue | Celery |
| Broker | RabbitMQ |
| Cache/rate limit | Redis |
| Scanner execution | Ephemeral Docker containers; Kubernetes Jobs later |
| Object storage | S3-compatible encrypted storage |
| Frontend | Next.js, React, TypeScript |
| Testing | pytest, pytest-asyncio, Testcontainers |
| Quality | Ruff, mypy, pre-commit |
| Observability | OpenTelemetry and structured logging |

## Why Python

- Most security automation and scanner integrations are already Python-friendly.
- FastAPI and Pydantic provide typed request and response boundaries.
- Python is suitable for parsing JSON, XML, SARIF, reports, and process output.
- The same language can support the control plane, adapters, workers, and
  normalization pipeline without forcing the UI into Python.

## Important Boundary

Python does not mean scanners run inside the web API.

The API records intent and authorization. The orchestrator dispatches an
immutable execution specification. An isolated worker launches a dedicated
scanner container with restricted network access and short-lived credentials.

## Why Not Python for Everything

The operational web console benefits from the React and TypeScript ecosystem.
Forcing a Python-rendered frontend would not improve scanner integration and
would reduce flexibility for dense interactive workflows.

## Evolution

Start with a modular monolith for the control plane. Keep worker execution
separate from day one. Move from Celery-launched containers to Kubernetes Jobs
when workload isolation, autoscaling, or multi-cluster execution requires it.


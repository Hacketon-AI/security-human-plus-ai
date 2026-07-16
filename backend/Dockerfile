FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN addgroup --system appgroup && adduser --system --group appuser

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir --timeout=120 --retries=3 . uvicorn[standard] httpx

COPY ./app ./app
COPY ./alembic.ini ./
COPY ./migrations ./migrations

RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/healthz || exit 1

# Run migrations then start the API server
CMD alembic upgrade head && uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000

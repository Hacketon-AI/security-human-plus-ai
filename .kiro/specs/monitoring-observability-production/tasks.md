# Implementation Plan: Monitoring & Observability (Production)

## Overview

Expand `app.platform.observability` and `app.platform.health` to production-grade observability: structured JSON logging, Prometheus RED metrics, enhanced health checks, OTLP distributed tracing, and an alerting contract YAML.

## Tasks

- [x] 1. Structured JSON logging
  - [x] 1.1 Implement `StructuredJsonFormatter` and `TraceContextFilter` in `app/platform/observability.py`
    - `StructuredJsonFormatter` serialises each `LogRecord` to a single-line JSON string with fields: `timestamp`, `level`, `logger`, `message`, `trace_id`, `span_id`, `environment`
    - `TraceContextFilter` reads the active OTel span via `opentelemetry.trace.get_current_span()` and injects `trace_id`/`span_id`; falls back to zero-value strings when no span is active
    - Serialise `exc_info` as nested `exception: {type, message, traceback}` when present
    - `_configure_logging(settings)` removes the plain-text `StreamHandler` in `staging`/`production`; keeps both in `development`/`test`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 1.2 Write property test — structured log round-trip (Property 1)
    - **Property 1: Structured log serialisation round-trip**
    - **Validates: Requirements 1.7, 1.1**
    - Use `@given(log_record_strategy())` with `hypothesis`; assert `json.loads(formatted)` fields match source record
    - File: `backend/tests/platform/test_observability_properties.py`

  - [ ]* 1.3 Write property test — trace context injection (Property 2)
    - **Property 2: Trace context injection**
    - **Validates: Requirements 1.2, 1.4**
    - Use `@given(trace_id=..., span_id=...)` with a mocked active span

  - [ ]* 1.4 Write property test — required fields always present (Property 3)
    - **Property 3: Required fields always present**
    - **Validates: Requirements 1.1, 1.4**
    - Assert `timestamp`, `level`, `logger`, `message`, `trace_id`, `span_id`, `environment` exist for any log record

  - [ ]* 1.5 Write property test — exception serialisation completeness (Property 4)
    - **Property 4: Exception serialisation completeness**
    - **Validates: Requirements 1.5**
    - Use `@given(exception_strategy())`; assert nested `exception` object with non-empty `type`, `message`, `traceback`

- [x] 2. Prometheus metrics collection
  - [x] 2.1 Implement `PrometheusMiddleware` and `_configure_metrics` in `app/platform/observability.py`
    - `PrometheusMiddleware` records `http_requests_total` (counter, labels: `method`, `path_template`, `status_code`) and `http_request_duration_seconds` (histogram, labels: `method`, `path_template`)
    - Resolve `path_template` from `request.scope["route"].path` to avoid cardinality explosion
    - `_configure_metrics(app, settings)` adds the middleware, mounts `prometheus_client.make_asgi_app()` at `/metrics` with `include_in_schema=False`, and wires up `DBPoolGauge` reading `app.state.db_engine.pool.checkedout()`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6_

  - [ ]* 2.2 Write property test — HTTP request counter strict monotonicity (Property 5)
    - **Property 5: HTTP request counter strict monotonicity**
    - **Validates: Requirements 2.2, 2.7**
    - Use `@given(label_sequence_strategy())`; assert counter value strictly increases after each increment

- [x] 3. Enhanced health checks
  - [x] 3.1 Implement `/healthz` and `/readyz` routes in `app/platform/health.py`
    - `/healthz` returns `200 {"status":"ok"}` unconditionally, no DB/broker queries
    - `/readyz` runs `_check_database(engine)` (`SELECT 1`, 2-second timeout) and `_check_broker(settings)` (celery backend only)
    - Returns `200 {"status":"ok","checks":{...}}` when all pass; `503 {"status":"degraded","checks":{...}}` on any failure
    - Uses `asyncio.wait_for(..., timeout=2.0)` per check; timed-out checks marked `failed` with `"error":"timeout"`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 3.2 Write property test — liveness independence from dependency state (Property 9)
    - **Property 9: Liveness independence from dependency state**
    - **Validates: Requirements 3.1, 3.5**
    - Use `@given(dependency_state_strategy())`; assert `/healthz` always returns 200 and issues no queries

  - [ ]* 3.3 Write unit tests for `/readyz`
    - Healthy deps → 200; DB failure → 503 with `checks.database.status=="failed"`; broker failure (celery) → 503; hanging dep mock resolves within 2 s
    - _Requirements: 3.2, 3.3, 3.4, 3.6_

- [x] 4. Distributed tracing with OTLP export
  - [x] 4.1 Expand `_configure_tracing(settings)` in `app/platform/observability.py`
    - Reads `OTEL_EXPORTER_OTLP_ENDPOINT`; if set and env is `production`/`staging`: configure `OTLPSpanExporterGRPC` + `BatchSpanProcessor` wrapped in `SpanExportErrorHandler`
    - Otherwise uses `NoOpSpanExporter`
    - Set propagator to `TraceContextPropagator` (W3C `traceparent`/`tracestate`)
    - `SQLAlchemyInstrumentor().instrument(engine=engine)` called from lifespan after engine construction
    - Export failures emit `WARNING` structured log, never raise into request path
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 4.2 Write property test — HTTP span attribute completeness (Property 6)
    - **Property 6: HTTP span attribute completeness**
    - **Validates: Requirements 4.2**
    - Use `@given(http_request_strategy())`; assert span has non-empty `http.method`, `http.target`, `http.status_code`, `http.route`

  - [ ]* 4.3 Write property test — DB span sanitisation (Property 7)
    - **Property 7: DB span sanitisation**
    - **Validates: Requirements 4.3**
    - Use `@given(query_with_literals_strategy())`; assert `db.statement` does not contain literal parameter values

  - [ ]* 4.4 Write property test — span export failure isolation (Property 8)
    - **Property 8: Span export failure isolation**
    - **Validates: Requirements 4.5**
    - Use `@given(export_error_strategy())`; assert exactly one WARNING log and no raised exception per failure

- [x] 5. Wire `instrument_app` and create alerting contract
  - [x] 5.1 Update `instrument_app(app, settings)` in `app/platform/observability.py` to call `_configure_logging`, `_configure_tracing`, `_configure_metrics` in order
    - Signature unchanged; verify callers in `app.main` need no updates
    - _Requirements: 2.1, 4.1, 4.4_

  - [x] 5.2 Create `backend/alerts/securescope_alerts.yaml`
    - Include `# schema_version: 1` header
    - Define `HighErrorRate`, `HighLatencyP99`, `ServiceDown`, `DatabaseUnhealthy` rules
    - Every rule carries labels: `severity`, `service: securescope`, `environment`
    - No Alertmanager routing or receiver keys
    - _Requirements: 5.1, 5.2, 5.3, 5.5_

  - [ ]* 5.3 Write property test — alert rules label completeness (Property 10)
    - **Property 10: Alert rules label completeness**
    - **Validates: Requirements 5.2**
    - Parse `securescope_alerts.yaml` with `yaml`; iterate all rules and assert `severity`, `service`, `environment` labels present

- [x] 6. Final checkpoint — Ensure all tests pass
  - Run the full test suite; ensure all property and unit tests pass. Ask the user if any questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Property tests use `hypothesis` (add to `backend` dev dependencies if not present)
- All observability logic stays in `app.platform.*`; no domain module imports it directly
- `instrument_app` signature is unchanged — no caller updates needed

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "2.1", "3.1", "4.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "3.3", "4.2", "4.3", "4.4", "5.1"] },
    { "id": 3, "tasks": ["5.2"] },
    { "id": 4, "tasks": ["5.3"] }
  ]
}
```
